"""CRUD endpoints for auxiliary model role assignments.

Auxiliary models are optional chat-type models assigned to specific pipeline roles:

  • doc_clean     — cleans parsed document text (PDF column mis-order, headers/footers)
  • chat_summary  — summarizes each conversation turn after the response
  • info_extract  — extracts citation metadata + abstract from new documents (first 2 pages)

Assignments are stored in the ``settings`` table as ``{role}_model_id`` key-value pairs.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session, joinedload

from database import get_db
from providers.models import AIModel
from settings.models import Setting

router = APIRouter(prefix="/api/aux-models", tags=["aux-models"])

# ---------------------------------------------------------------------------
# Role registry
# ---------------------------------------------------------------------------

_ROLES: dict[str, str] = {
    "doc_clean":    "doc_clean_model_id",
    "chat_summary": "chat_summary_model_id",
    "info_extract": "info_extract_model_id",
}

_DESCRIPTIONS: dict[str, str] = {
    "doc_clean":    "文档清洗模型：修复 PDF 解析文本的排版错位、分栏混排等问题，提升嵌入质量",
    "chat_summary": "对话总结模型：在每轮对话结束后生成本轮主要内容摘要",
    "info_extract": "信息抽取模型：从文档前两页自动提取引用信息（标题、作者、年份、DOI 等）与摘要",
}


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class AuxModelOut(BaseModel):
    role: str
    description: str
    model_id: int | None = None
    model_display_name: str | None = None
    model_api_name: str | None = None
    provider_name: str | None = None
    model_qps: int | None = None


class AuxModelAssign(BaseModel):
    model_id: int


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_assignment(role: str, db: Session) -> AuxModelOut:
    """Read the current assignment for *role* from DB and return an AuxModelOut."""
    setting_key = _ROLES[role]
    row = db.get(Setting, setting_key)
    value = row.value if row else ""

    try:
        model_id = int(value) if value else None
    except (ValueError, TypeError):
        model_id = None

    if model_id is None:
        return AuxModelOut(role=role, description=_DESCRIPTIONS[role])

    model = (
        db.query(AIModel)
        .options(joinedload(AIModel.provider))
        .filter(AIModel.id == model_id)
        .first()
    )
    if not model:
        # Stale reference — setting points to a deleted model; report id but no details
        return AuxModelOut(role=role, description=_DESCRIPTIONS[role], model_id=model_id)

    return AuxModelOut(
        role=role,
        description=_DESCRIPTIONS[role],
        model_id=model.id,
        model_display_name=model.display_name,
        model_api_name=model.api_name,
        provider_name=model.provider.name,
        model_qps=model.qps,
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("", response_model=list[AuxModelOut])
def list_aux_models(db: Session = Depends(get_db)):
    """List all auxiliary model role assignments / 列出所有副模型角色的当前配置。"""
    return [_load_assignment(role, db) for role in _ROLES]


@router.put("/{role}", response_model=AuxModelOut)
def assign_aux_model(
    role: str,
    payload: AuxModelAssign,
    db: Session = Depends(get_db),
):
    """Assign a chat model to an auxiliary role / 为副模型角色指定模型。

    The model must be of type **chat** and both the model and its provider must be enabled.
    """
    if role not in _ROLES:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown role '{role}'. Valid roles: {list(_ROLES)}",
        )

    model = (
        db.query(AIModel)
        .options(joinedload(AIModel.provider))
        .filter(AIModel.id == payload.model_id)
        .first()
    )
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")
    if model.model_type != "chat":
        raise HTTPException(
            status_code=400,
            detail=f"Model type is '{model.model_type}'; auxiliary models must be of type 'chat'",
        )
    if not model.is_enabled:
        raise HTTPException(status_code=400, detail="Model is disabled")
    if not model.provider.is_enabled:
        raise HTTPException(status_code=400, detail="Model's provider is disabled")

    setting_key = _ROLES[role]
    row = db.get(Setting, setting_key)
    if row:
        row.value = str(payload.model_id)
    else:
        db.add(Setting(key=setting_key, value=str(payload.model_id)))
    db.commit()

    return AuxModelOut(
        role=role,
        description=_DESCRIPTIONS[role],
        model_id=model.id,
        model_display_name=model.display_name,
        model_api_name=model.api_name,
        provider_name=model.provider.name,
        model_qps=model.qps,
    )


@router.delete("/{role}", status_code=status.HTTP_204_NO_CONTENT)
def unassign_aux_model(role: str, db: Session = Depends(get_db)):
    """Unassign (disable) an auxiliary model role / 取消副模型角色配置。"""
    if role not in _ROLES:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown role '{role}'. Valid roles: {list(_ROLES)}",
        )
    setting_key = _ROLES[role]
    row = db.get(Setting, setting_key)
    if row:
        row.value = ""
        db.commit()
