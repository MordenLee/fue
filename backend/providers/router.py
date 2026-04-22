"""API routes for Provider and AIModel CRUD."""

import time
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import Text, cast, func
from sqlalchemy.orm import Session

from database import get_db
from providers.models import (
    AIModel,
    AIModelCreate,
    AIModelOut,
    AIModelUpdate,
    DeletedProvider,
    Provider,
    ProviderCreate,
    ProviderOut,
    ProviderUpdate,
)

router = APIRouter(prefix="/api", tags=["providers"])


# ============================= Providers =============================

@router.get("/providers", response_model=list[ProviderOut])
def list_providers(db: Session = Depends(get_db)):
    """List all providers / 列出所有供应商。"""
    return db.query(Provider).order_by(Provider.sort_order.asc(), Provider.created_at.desc()).all()


@router.post("/providers", response_model=ProviderOut, status_code=status.HTTP_201_CREATED)
def create_provider(
    payload: ProviderCreate,
    db: Session = Depends(get_db),
):
    """Create a new provider / 新增供应商。"""
    max_order = db.query(func.max(Provider.sort_order)).scalar() or 0
    record = Provider(**payload.model_dump(), sort_order=max_order + 1)
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


@router.get("/providers/{provider_id}", response_model=ProviderOut)
def get_provider(
    provider_id: int,
    db: Session = Depends(get_db),
):
    """Get a single provider / 获取单个供应商。"""
    record = db.get(Provider, provider_id)
    if not record:
        raise HTTPException(status_code=404, detail="Provider not found")
    return record


@router.put("/providers/{provider_id}", response_model=ProviderOut)
def update_provider(
    provider_id: int,
    payload: ProviderUpdate,
    db: Session = Depends(get_db),
):
    """Update provider config (partial update) / 更新供应商配置（仅更新传入字段）。"""
    record = db.get(Provider, provider_id)
    if not record:
        raise HTTPException(status_code=404, detail="Provider not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(record, field, value)
    db.commit()
    db.refresh(record)
    return record


@router.patch("/providers/{provider_id}/enabled", response_model=ProviderOut)
def set_provider_enabled(
    provider_id: int,
    enabled: bool,
    db: Session = Depends(get_db),
):
    """Enable or disable a provider / 启用或禁用供应商。"""
    record = db.get(Provider, provider_id)
    if not record:
        raise HTTPException(status_code=404, detail="Provider not found")
    record.is_enabled = enabled
    db.commit()
    db.refresh(record)
    return record


@router.delete("/providers/{provider_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_provider(
    provider_id: int,
    db: Session = Depends(get_db),
):
    """Delete a provider (cascades to all its models) / 删除供应商（级联删除旗下模型）。"""
    record = db.get(Provider, provider_id)
    if not record:
        raise HTTPException(status_code=404, detail="Provider not found")
    # Remember the name so auto-seed won't recreate it
    if not db.query(DeletedProvider).filter(DeletedProvider.name == record.name).first():
        db.add(DeletedProvider(name=record.name))
    db.delete(record)
    db.commit()


class ReorderItem(BaseModel):
    id: int
    sort_order: int


@router.put("/providers/reorder", status_code=status.HTTP_204_NO_CONTENT)
def reorder_providers(
    items: list[ReorderItem],
    db: Session = Depends(get_db),
):
    """Batch update provider sort orders / 批量更新供应商排序。"""
    for item in items:
        record = db.get(Provider, item.id)
        if record:
            record.sort_order = item.sort_order
    db.commit()


class TestResponse(BaseModel):
    success: bool
    message: str
    latency_ms: Optional[float] = None


@router.post("/providers/{provider_id}/test", response_model=TestResponse)
async def test_provider(
    provider_id: int,
    model_id: Optional[int] = Query(
        default=None,
        description="用于测试的模型 ID，不传则自动选取该供应商第一个可用 chat 模型 / Model ID for testing; auto-selects the first available chat model if omitted",
    ),
    db: Session = Depends(get_db),
):
    """Send a minimal test request to verify API key and connectivity.
    向 AI 供应商发送最小测试请求，验证 API Key 与网络连通性。"""
    provider = db.get(Provider, provider_id)
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")
    if not provider.is_enabled:
        raise HTTPException(status_code=403, detail="Provider is disabled")

    if model_id is not None:
        ai_model = db.get(AIModel, model_id)
        if not ai_model or ai_model.provider_id != provider_id:
            raise HTTPException(status_code=404, detail="Model not found")
    else:
        ai_model = (
            db.query(AIModel)
            .filter(
                AIModel.provider_id == provider_id,
                AIModel.model_type == "chat",
                AIModel.is_enabled == True,  # noqa: E712
            )
            .first()
        )
        if ai_model is None:
            raise HTTPException(status_code=400, detail="No available chat model for this provider")

    interface = provider.interface_type
    kwargs: dict = {"model": ai_model.api_name}
    if provider.api_key:
        kwargs["api_key"] = provider.api_key
    if provider.api_base_url:
        kwargs["base_url"] = provider.api_base_url
    if ai_model.temperature is not None:
        kwargs["temperature"] = ai_model.temperature

    try:
        t0 = time.monotonic()

        if interface in ("openai", "openai_compatible"):
            # Use raw openai client directly — more robust with third-party proxies
            from openai import AsyncOpenAI
            client = AsyncOpenAI(
                api_key=provider.api_key or "placeholder-api-key",
                base_url=provider.api_base_url or "https://api.openai.com/v1",
            )
            await client.chat.completions.create(
                model=ai_model.api_name,
                messages=[{"role": "user", "content": "Hi"}],
                max_tokens=10,
            )
        elif interface == "anthropic":
            from langchain_anthropic import ChatAnthropic
            llm = ChatAnthropic(**kwargs)
            from langchain_core.messages import HumanMessage
            await llm.ainvoke([HumanMessage(content="Hi")])
        elif interface == "google":
            from langchain_google_genai import ChatGoogleGenerativeAI
            google_kwargs: dict = {"model": ai_model.api_name}
            if provider.api_key:
                google_kwargs["google_api_key"] = provider.api_key
            if ai_model.temperature is not None:
                google_kwargs["temperature"] = ai_model.temperature
            llm = ChatGoogleGenerativeAI(**google_kwargs)
            from langchain_core.messages import HumanMessage
            await llm.ainvoke([HumanMessage(content="Hi")])
        elif interface == "ollama":
            from langchain_ollama import ChatOllama
            ollama_kwargs: dict = {"model": ai_model.api_name}
            if provider.api_base_url:
                ollama_kwargs["base_url"] = provider.api_base_url
            llm = ChatOllama(**ollama_kwargs)
            from langchain_core.messages import HumanMessage
            await llm.ainvoke([HumanMessage(content="Hi")])
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported interface type: {interface}")

        latency_ms = round((time.monotonic() - t0) * 1000, 1)
        return TestResponse(
            success=True,
            message="Connectivity test passed",
            latency_ms=latency_ms,
        )
    except Exception as exc:
        return TestResponse(
            success=False,
            message=f"Connectivity test failed: {exc}",
        )


# ============================= AI Models =============================

@router.get("/models/defaults", response_model=dict[str, AIModelOut])
def get_default_models(db: Session = Depends(get_db)):
    """返回每种模型类型当前设置的默认模型（chat / embedding / reranking）。
    Get the default model for each model type."""
    result: dict[str, AIModelOut] = {}
    for model_type in ("chat", "embedding", "reranking"):
        record = db.query(AIModel).filter(
            AIModel.model_type == model_type,
            AIModel.is_default == True,  # noqa: E712
        ).first()
        if record:
            result[model_type] = record
    return result


@router.get("/models", response_model=list[AIModelOut])
def list_models(
    provider_id: Optional[int] = Query(default=None, description="按供应商 ID 过滤 / Filter by provider ID"),
    model_type: Optional[str] = Query(default=None, description="按类型过滤 / Filter by type: chat / embedding / reranking"),
    capability: Optional[str] = Query(default=None, description="按能力过滤 / Filter by capability: vision / reasoning / function_calling"),
    enabled_only: bool = Query(default=False, description="仅返回已启用的模型 / Return enabled models only"),
    db: Session = Depends(get_db),
):
    """列出所有模型，支持按供应商、类型、能力和启用状态过滤。"""
    from sqlalchemy.orm import joinedload
    query = db.query(AIModel).options(joinedload(AIModel.provider))
    if provider_id is not None:
        query = query.filter(AIModel.provider_id == provider_id)
    if model_type is not None:
        query = query.filter(AIModel.model_type == model_type)
    if capability is not None:
        query = query.filter(cast(AIModel.capabilities, Text).like(f'"%{capability}%"'))
    if enabled_only:
        query = query.filter(AIModel.is_enabled == True)  # noqa: E712
    return query.order_by(AIModel.created_at.desc()).all()


@router.post("/models", response_model=AIModelOut, status_code=status.HTTP_201_CREATED)
def create_model(
    payload: AIModelCreate,
    db: Session = Depends(get_db),
):
    """Create a new model (provider_id must exist) / 新增模型（provider_id 必须存在）。"""
    if not db.get(Provider, payload.provider_id):
        raise HTTPException(status_code=404, detail="Provider not found")
    if payload.is_default:
        db.query(AIModel).filter(
            AIModel.model_type == payload.model_type,
            AIModel.is_default == True,  # noqa: E712
        ).update({"is_default": False})
    record = AIModel(**payload.model_dump())
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


@router.get("/models/{model_id}", response_model=AIModelOut)
def get_model(
    model_id: int,
    db: Session = Depends(get_db),
):
    """Get a single model / 获取单个模型详情。"""
    record = db.get(AIModel, model_id)
    if not record:
        raise HTTPException(status_code=404, detail="Model not found")
    return record


@router.put("/models/{model_id}", response_model=AIModelOut)
def update_model(
    model_id: int,
    payload: AIModelUpdate,
    db: Session = Depends(get_db),
):
    """Update a model (partial update) / 更新模型（仅更新传入字段）。"""
    record = db.get(AIModel, model_id)
    if not record:
        raise HTTPException(status_code=404, detail="Model not found")
    if payload.provider_id is not None and not db.get(Provider, payload.provider_id):
        raise HTTPException(status_code=404, detail="Provider not found")
    if payload.is_default:
        final_model_type = payload.model_type if payload.model_type is not None else record.model_type
        db.query(AIModel).filter(
            AIModel.model_type == final_model_type,
            AIModel.id != model_id,
        ).update({"is_default": False})
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(record, field, value)
    db.commit()
    db.refresh(record)
    return record


@router.patch("/models/{model_id}/enabled", response_model=AIModelOut)
def set_model_enabled(
    model_id: int,
    enabled: bool,
    db: Session = Depends(get_db),
):
    """Enable or disable a model / 启用或禁用模型。"""
    record = db.get(AIModel, model_id)
    if not record:
        raise HTTPException(status_code=404, detail="Model not found")
    record.is_enabled = enabled
    db.commit()
    db.refresh(record)
    return record


@router.delete("/models/{model_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_model(
    model_id: int,
    db: Session = Depends(get_db),
):
    """Delete a model / 删除模型。"""
    record = db.get(AIModel, model_id)
    if not record:
        raise HTTPException(status_code=404, detail="Model not found")
    db.delete(record)
    db.commit()
