"""API routes for application settings."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from database import get_db
from settings.models import DEFAULTS, Setting, SettingsOut, SettingsUpdate

router = APIRouter(prefix="/api/settings", tags=["settings"])


def _get_all(db: Session) -> dict[str, str]:
    """Load all settings from DB, filling missing keys with defaults."""
    rows = {r.key: r.value for r in db.query(Setting).all()}
    return {k: rows.get(k, v) for k, v in DEFAULTS.items()}


def _to_out(data: dict[str, str]) -> SettingsOut:
    raw_embed_id = data.get("default_embed_model_id", "")

    def _to_int_or_none(key: str) -> int | None:
        v = data.get(key, "")
        return int(v) if v else None

    return SettingsOut(
        language=data["language"],
        embed_max_concurrency=int(data["embed_max_concurrency"]),
        embed_use_model_qps=data.get("embed_use_model_qps", "false") == "true",
        kb_index_max_workers=int(data.get("kb_index_max_workers", DEFAULTS["kb_index_max_workers"])),
        rag_top_k=int(data["rag_top_k"]),
        hybrid_keyword_floor_top_k=int(data.get("hybrid_keyword_floor_top_k", DEFAULTS["hybrid_keyword_floor_top_k"])),
        default_embed_model_id=int(raw_embed_id) if raw_embed_id else None,
        pdf_parser=data["pdf_parser"],
        docx_parser=data["docx_parser"],
        doc_clean_model_id=_to_int_or_none("doc_clean_model_id"),
        chat_summary_model_id=_to_int_or_none("chat_summary_model_id"),
        info_extract_model_id=_to_int_or_none("info_extract_model_id"),
        doc_clean_keep_references=data.get("doc_clean_keep_references", "false") == "true",
        doc_clean_keep_annotations=data.get("doc_clean_keep_annotations", "false") == "true",
        chat_citation_mode=data.get("chat_citation_mode", DEFAULTS["chat_citation_mode"]),
        chat_citation_style=data.get("chat_citation_style", DEFAULTS["chat_citation_style"]),
        chat_history_turns=int(data.get("chat_history_turns", DEFAULTS["chat_history_turns"])),
        chat_max_tool_rounds=int(data.get("chat_max_tool_rounds", DEFAULTS["chat_max_tool_rounds"])),
        chat_compress_model_id=_to_int_or_none("chat_compress_model_id"),
    )


@router.get("", response_model=SettingsOut)
def get_settings(db: Session = Depends(get_db)):
    """Return current application settings. Missing keys fall back to defaults.
    返回当前应用设置，缺失的键使用默认值。"""
    return _to_out(_get_all(db))


@router.put("", response_model=SettingsOut)
def update_settings(payload: SettingsUpdate, db: Session = Depends(get_db)):
    """Update one or more settings. Only provided fields are persisted.
    更新设置，仅持久化传入的字段。"""
    # exclude_unset so passing null explicitly can clear optional settings
    updates = payload.model_dump(exclude_unset=True)

    for key, value in updates.items():
        # settings table stores everything as plain strings
        if isinstance(value, bool):
            str_value = "true" if value else "false"
        else:
            str_value = str(value) if value is not None else ""
        row = db.get(Setting, key)
        if row:
            row.value = str_value
        else:
            db.add(Setting(key=key, value=str_value))

    db.commit()
    return _to_out(_get_all(db))


@router.post("/reset", response_model=SettingsOut)
def reset_settings(db: Session = Depends(get_db)):
    """Reset all settings to factory defaults.
    将所有设置恢复为出厂默认值。"""
    db.query(Setting).delete()
    db.commit()
    return _to_out(DEFAULTS)
