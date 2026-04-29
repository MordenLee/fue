import json
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# ---------------------------------------------------------------------------
# Logging configuration
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

logger = logging.getLogger(__name__)

from database import Base, engine, SessionLocal
import providers  # noqa: F401 — 确保 Provider / AIModel 注册到 Base.metadata
import settings  # noqa: F401 — 确保 Setting 注册到 Base.metadata
import knowledge  # noqa: F401 — 确保 KnowledgeBase / DocumentFile / Citation 注册到 Base.metadata
import conversations  # noqa: F401 — 确保 Conversation / Message 注册到 Base.metadata
import folders  # noqa: F401 — 确保 Folder 注册到 Base.metadata
from providers.models import AIModel, DeletedProvider, Provider
from sqlalchemy import func
from providers.router import router as providers_router
from settings.router import router as settings_router
from knowledge.router import router as knowledge_router
from knowledge.documents.router import router as documents_router
from chat.router import router as chat_router
from admin.router import router as admin_router
from auxmodels.router import router as aux_router
from conversations.router import router as conversations_router
from folders.router import router as folders_router

# 启动时自动建表（首次运行创建 app.db）
Base.metadata.create_all(bind=engine)

# ---------------------------------------------------------------------------
# 简易迁移：确保 providers 表有 sort_order 列（已有数据库可能缺少）
# ---------------------------------------------------------------------------
with engine.connect() as conn:
    from sqlalchemy import text, inspect as sa_inspect
    cols = [c["name"] for c in sa_inspect(engine).get_columns("providers")]
    if "sort_order" not in cols:
        conn.execute(text("ALTER TABLE providers ADD COLUMN sort_order INTEGER NOT NULL DEFAULT 0"))
        conn.commit()

# ---------------------------------------------------------------------------
# 简易迁移：为 conversations 和 knowledge_bases 补充 folder_id 列
# ---------------------------------------------------------------------------
with engine.connect() as conn:
    from sqlalchemy import text, inspect as sa_inspect
    conv_cols = [c["name"] for c in sa_inspect(engine).get_columns("conversations")]
    if "folder_id" not in conv_cols:
        conn.execute(text("ALTER TABLE conversations ADD COLUMN folder_id INTEGER"))
        conn.commit()
    kb_cols = [c["name"] for c in sa_inspect(engine).get_columns("knowledge_bases")]
    if "folder_id" not in kb_cols:
        conn.execute(text("ALTER TABLE knowledge_bases ADD COLUMN folder_id INTEGER"))
        conn.commit()
    if "use_delimiter_split" not in kb_cols:
        conn.execute(text("ALTER TABLE knowledge_bases ADD COLUMN use_delimiter_split INTEGER NOT NULL DEFAULT 1"))
        conn.commit()

# ---------------------------------------------------------------------------
# 简易迁移：为 messages 表补充 model_id 列（记录每条消息使用的模型）
# ---------------------------------------------------------------------------
with engine.connect() as conn:
    from sqlalchemy import text, inspect as sa_inspect
    msg_cols = [c["name"] for c in sa_inspect(engine).get_columns("messages")]
    if "model_id" not in msg_cols:
        conn.execute(text("ALTER TABLE messages ADD COLUMN model_id INTEGER REFERENCES ai_models(id) ON DELETE SET NULL"))
        conn.commit()

# ---------------------------------------------------------------------------
# 首次启动自动写入预置供应商（仅当数据库中还没有任何 Provider 时执行）
# ---------------------------------------------------------------------------
_PROVIDERS_JSON = Path(__file__).resolve().parent.parent / "shared" / "providers.json"

_KNOWN_COMPROMISED_PRESET_KEYS = frozenset({
    "sk-bisxyxtfvgwdddldvhoevzxqasahghfkekkujchpifewzycn",
})

# Safety switch:
# - Default: DO NOT auto-clear any existing provider api_key on startup.
# - Set APP_CLEAR_COMPROMISED_PRESET_KEYS=1 to explicitly enable one-time cleanup.
_CLEAR_COMPROMISED_PRESET_KEYS = os.environ.get("APP_CLEAR_COMPROMISED_PRESET_KEYS", "0") == "1"


def _should_clear_seeded_api_key(existing: Provider, preset_api_key: str) -> bool:
    """Clear stale preset keys that were seeded by an older leaked preset file.

    We only auto-clear when the current preset intentionally leaves api_key blank
    and the stored key exactly matches a known compromised preset key.

    Do not rely on timestamps here: in dev, quick user edits plus SQLite's coarse
    timestamp precision can make legitimate user-entered keys look indistinguishable
    from untouched seed rows.
    """
    if not _CLEAR_COMPROMISED_PRESET_KEYS:
        return False

    if preset_api_key or not existing.api_key:
        return False

    return existing.api_key in _KNOWN_COMPROMISED_PRESET_KEYS

def _auto_seed() -> None:
    if not _PROVIDERS_JSON.exists():
        logger.warning("shared/providers.json not found, skipping auto-seed.")
        return
    db = SessionLocal()
    try:
        data: list[dict] = json.loads(_PROVIDERS_JSON.read_text(encoding="utf-8"))
        # Names the user explicitly deleted — never recreate these
        deleted_names = {r.name for r in db.query(DeletedProvider).all()}
        created_p = created_m = updated_keys = cleared_keys = 0
        max_order = db.query(func.max(Provider.sort_order)).scalar() or 0
        for entry in data:
            models_data: list[dict] = entry.pop("models", [])
            api_key: str = entry.get("api_key") or ""
            if entry["name"] in deleted_names:
                continue
            existing = db.query(Provider).filter(Provider.name == entry["name"]).first()
            if existing:
                if _should_clear_seeded_api_key(existing, api_key):
                    existing.api_key = ""
                    cleared_keys += 1
                # 已存在：仅当 JSON 里的 api_key 非空时更新它
                if api_key and existing.api_key != api_key:
                    existing.api_key = api_key
                    updated_keys += 1
                continue
            # 新增供应商
            max_order += 1
            provider = Provider(**entry, sort_order=max_order)
            db.add(provider)
            db.flush()
            for m in models_data:
                db.add(AIModel(provider_id=provider.id, **m))
                created_m += 1
            created_p += 1
        db.commit()
        if created_p or updated_keys or cleared_keys:
            logger.info(
                "Auto-seed: %d providers created, %d models created, %d api_keys updated, %d stale preset keys cleared.",
                created_p, created_m, updated_keys, cleared_keys,
            )
    except Exception:
        db.rollback()
        logger.exception("Auto-seed failed.")
    finally:
        db.close()

_auto_seed()


@asynccontextmanager
async def lifespan(app_instance: FastAPI):
    # Announce the backend port to Electron after the server is ready.
    port = getattr(app_instance.state, '_backend_port', None)
    if port is not None:
        print(f"BACKEND_PORT:{port}", flush=True)
    yield


app = FastAPI(title="App Backend", version="0.1.0", lifespan=lifespan)

# 允许 Electron 渲染进程跨域访问：
# - 开发环境: http://127.0.0.1:<vite_port> / http://localhost:<vite_port>
# - 生产环境: file:// 页面发起请求时浏览器会发送 Origin: null
app.add_middleware(
    CORSMiddleware,
    allow_origins=["null"],
    allow_origin_regex=r"^https?://(127\.0\.0\.1|localhost)(:\d+)?$|^app://\.$",
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(providers_router)
app.include_router(settings_router)
app.include_router(knowledge_router)
app.include_router(documents_router)
app.include_router(chat_router)
app.include_router(admin_router)
app.include_router(aux_router)
app.include_router(conversations_router)
app.include_router(folders_router)


class MessageResponse(BaseModel):
    message: str


@app.get("/api/ping", response_model=MessageResponse)
async def ping():
    """健康检查接口"""
    return {"message": "pong"}


if __name__ == "__main__":
    import socket
    import uvicorn

    env_port = os.environ.get("APP_BACKEND_PORT", "").strip()
    if env_port:
        try:
            port = int(env_port)
        except ValueError:
            logger.warning("Invalid APP_BACKEND_PORT=%s, fallback to random port.", env_port)
            port = 0
    else:
        port = 0

    # Find an available port when not explicitly provided.
    if port == 0:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(('127.0.0.1', 0))
            port = s.getsockname()[1]

    # Store port on app state so the lifespan handler can announce it
    # after the server is truly ready to accept connections.
    app.state._backend_port = port
    uvicorn.run(app, host="127.0.0.1", port=port, reload=False)
