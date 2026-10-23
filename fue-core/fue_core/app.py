import hashlib
import json
import logging
import os
import asyncio
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

from fue_core.database import Base, engine, SessionLocal
from fue_core import providers  # noqa: F401 — 确保 Provider / AIModel 注册到 Base.metadata
from fue_core import settings  # noqa: F401 — 确保 Setting 注册到 Base.metadata
from fue_core import knowledge  # noqa: F401 — 确保 KnowledgeBase / DocumentFile / Citation 注册到 Base.metadata
from fue_core import conversations  # noqa: F401 — 确保 Conversation / Message 注册到 Base.metadata
from fue_core import folders  # noqa: F401 — 确保 Folder 注册到 Base.metadata
from fue_core.providers.models import AIModel, DeletedProvider, Provider
from sqlalchemy import func
from fue_core.providers.router import router as providers_router
from fue_core.settings.router import router as settings_router
from fue_core.knowledge.router import router as knowledge_router
from fue_core.knowledge.documents.router import router as documents_router
from fue_core.chat.router import router as chat_router
from fue_core.admin.router import router as admin_router
from fue_core.auxmodels.router import router as aux_router
from fue_core.conversations.router import router as conversations_router
from fue_core.folders.router import router as folders_router
from fue_core.agents.runtime import get_registry
from fue_core.memory.router import router as memory_router, worker as memory_worker
from fue_core.memory.mcp import router as mcp_router
from fue_core.memory.workspace import router as workspace_router

# Fail before serving chat requests if packaged agent/skill resources are invalid.
get_registry()

# 启动时自动建表（首次运行创建 app.db）
from fue_core.tasks import TaskManager, router as tasks_router
from fue_core.execution import router as execution_router
from fue_core.platform.migrations import migrate

# ---------------------------------------------------------------------------
# 首次启动自动写入预置供应商（仅当数据库中还没有任何 Provider 时执行）
# ---------------------------------------------------------------------------
from fue_core.platform.paths import resources_dir

_PROVIDERS_JSON = resources_dir() / "providers.json"

_KNOWN_COMPROMISED_PRESET_KEY_HASHES = frozenset({
    "ae962de732c4cb6c080da194df1eb29d9b6bb77bc99097d80775d8b03a57a0fc",
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

    return hashlib.sha256(existing.api_key.encode()).hexdigest() in _KNOWN_COMPROMISED_PRESET_KEY_HASHES

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



@asynccontextmanager
async def lifespan(app_instance: FastAPI):
    migrate(engine, Base.metadata)
    _auto_seed()
    manifest = getattr(app_instance.state, 'workspace_manifest', None)
    if manifest is not None:
        from fue_core.platform.installation import write_json
        from fue_core.platform.paths import data_dir
        write_json(data_dir() / 'workspace.json', manifest)
    from fue_core.execution import recover
    with SessionLocal() as db:
        recover(db)
    # Announce the backend port to Electron after the server is ready.
    port = getattr(app_instance.state, '_backend_port', None)
    if port is not None:
        print(f"BACKEND_PORT:{port}", flush=True)
    core = getattr(app_instance.state, "core", None)
    if core:
        app_instance.state.tasks = TaskManager(core)
        app_instance.state.tasks.recover()
        from fue_core.chat.service import _background_tasks
        core.busy_probe = lambda: bool(_background_tasks)
        core.publish(port)
    supervisor = asyncio.create_task(core.supervise()) if core else None
    task = asyncio.create_task(memory_worker(SessionLocal, core))
    try:
        yield
    finally:
        if core:
            await app_instance.state.tasks.close()
        if supervisor:
            supervisor.cancel()
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


app = FastAPI(title="FUE Core", version="2.0.0", lifespan=lifespan)

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

from fue_core.system import router as system_router
app.include_router(system_router)
from fue_core.external import router as external_router
app.include_router(external_router)
app.include_router(tasks_router)
app.include_router(execution_router)

app.include_router(providers_router)
app.include_router(settings_router)
app.include_router(knowledge_router)
app.include_router(documents_router)
app.include_router(chat_router)
app.include_router(admin_router)
app.include_router(aux_router)
app.include_router(conversations_router)
app.include_router(folders_router)
app.include_router(memory_router)
app.include_router(mcp_router)
app.include_router(workspace_router)


class MessageResponse(BaseModel):
    message: str


@app.get("/api/ping", response_model=MessageResponse)
async def ping():
    """健康检查接口"""
    return {"message": "pong"}


