"""SQLAlchemy models & Pydantic schemas for Provider and AIModel."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


# ---------------------------------------------------------------------------
# ORM Models
# ---------------------------------------------------------------------------

class Provider(Base):
    """LLM 供应商配置。"""

    __tablename__ = "providers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False, comment="Provider display name / 供应商显示名称")
    interface_type: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment="Interface type: openai / anthropic / google / ollama / openai_compatible / cohere / jina / 接口类型",
    )
    api_base_url: Mapped[Optional[str]] = mapped_column(
        String(256), nullable=True, comment="API base URL, leave blank for provider default / API 地址，留空使用官方默认"
    )
    api_key: Mapped[Optional[str]] = mapped_column(
        String(256), nullable=True, comment="API key, leave blank for local models / API 密钥，本地模型可留空"
    )
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="Notes / 备注说明")
    is_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="1", comment="Enabled / 是否启用"
    )
    sort_order: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0", comment="Display order / 显示排序"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    ai_models: Mapped[list[AIModel]] = relationship(
        "AIModel", back_populates="provider", cascade="all, delete-orphan"
    )


class DeletedProvider(Base):
    """记录被用户手动删除的预置供应商名称，防止 auto-seed 重新创建。"""

    __tablename__ = "deleted_providers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)


class AIModel(Base):
    """LLM 模型配置，归属于某个 Provider。"""

    __tablename__ = "ai_models"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    provider_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("providers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # 名称
    api_name: Mapped[str] = mapped_column(
        String(128), nullable=False, comment="API identifier, e.g. gpt-4o / API 调用标识符，如 gpt-4o"
    )
    display_name: Mapped[str] = mapped_column(
        String(128), nullable=False, comment="Display name, e.g. GPT-4o / 界面展示名称，如 GPT-4o"
    )
    # 分类 / Classification
    series: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True, comment="Model series, e.g. GPT-4 / 模型系列，如 GPT-4"
    )
    model_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="chat",
        comment="Model type: chat / embedding / reranking / 模型类型",
    )
    # 能力与规格 / Capabilities & Specs
    capabilities: Mapped[Optional[list]] = mapped_column(
        JSON,
        nullable=True,
        comment="Capability list: vision / reasoning / function_calling / 能力列表",
    )
    context_length: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True, comment="Context length in k tokens / 上下文长度，单位 k"
    )
    # 状态 / Status
    is_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="1", comment="Enabled / 是否启用"
    )
    is_default: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0", comment="Default model for provider / 是否为该供应商默认模型"
    )
    # 推理参数预设 / Inference parameter presets
    temperature: Mapped[Optional[float]] = mapped_column(
        Float, nullable=True, comment="Temperature (0–2) / 温度参数"
    )
    top_p: Mapped[Optional[float]] = mapped_column(
        Float, nullable=True, comment="Top-p sampling (0–1) / top_p 采样参数"
    )
    qps: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True, comment="Max requests per second / 每秒最大请求数"
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    provider: Mapped[Provider] = relationship("Provider", back_populates="ai_models")

    @property
    def provider_name(self) -> str:
        """Return the parent provider's display name, used by AIModelOut."""
        return self.provider.name if self.provider else ""


# ---------------------------------------------------------------------------
# Pydantic Schemas — Provider
# ---------------------------------------------------------------------------

class ProviderCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=128, examples=["OpenAI"])
    interface_type: str = Field(
        ...,
        pattern=r"^(openai|anthropic|google|ollama|openai_compatible|cohere|jina)$",
        examples=["openai"],
    )
    api_base_url: Optional[str] = Field(
        default=None, examples=["https://api.openai.com/v1"]
    )
    api_key: Optional[str] = Field(default=None, examples=["sk-..."])
    description: Optional[str] = Field(default=None, examples=["官方 OpenAI 账号"])
    is_enabled: bool = Field(default=True)


class ProviderUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=128)
    interface_type: Optional[str] = Field(
        default=None,
        pattern=r"^(openai|anthropic|google|ollama|openai_compatible|cohere|jina)$",
    )
    api_base_url: Optional[str] = None
    api_key: Optional[str] = None
    description: Optional[str] = None
    is_enabled: Optional[bool] = None


class ProviderOut(BaseModel):
    id: int
    name: str
    interface_type: str
    api_base_url: Optional[str]
    api_key: Optional[str]
    description: Optional[str]
    is_enabled: bool
    sort_order: int = 0
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Pydantic Schemas — AIModel
# ---------------------------------------------------------------------------

_VALID_CAPABILITIES: frozenset[str] = frozenset({"vision", "reasoning", "function_calling"})


class AIModelCreate(BaseModel):
    provider_id: int
    api_name: str = Field(..., min_length=1, max_length=128, examples=["gpt-4o"])
    display_name: str = Field(..., min_length=1, max_length=128, examples=["GPT-4o"])
    series: Optional[str] = Field(default=None, max_length=64, examples=["GPT-4"])
    model_type: str = Field(
        default="chat",
        pattern=r"^(chat|embedding|reranking)$",
        examples=["chat"],
    )
    capabilities: Optional[list[str]] = Field(
        default=None,
        examples=[["vision", "function_calling"]],
        description="可选值 / Available values: vision / reasoning / function_calling",
    )
    context_length: Optional[int] = Field(
        default=None, ge=1, examples=[128], description="上下文长度，单位 k / Context length in k tokens"
    )
    is_enabled: bool = Field(default=True)
    is_default: bool = Field(default=False)
    temperature: Optional[float] = Field(default=None, ge=0, le=2, description="温度参数 / Temperature (0–2)")
    top_p: Optional[float] = Field(default=None, ge=0, le=1, description="top_p 采样参数 / Top-p sampling (0–1)")
    qps: Optional[int] = Field(default=None, ge=1, description="每秒最大请求数 / Max requests per second (QPS)")

    @field_validator("capabilities")
    @classmethod
    def validate_capabilities(cls, v: Optional[list[str]]) -> Optional[list[str]]:
        if v is not None:
            invalid = set(v) - _VALID_CAPABILITIES
            if invalid:
                raise ValueError(
                    f"不合法的 capability 值 / Invalid capability value: {invalid}，"
                    f"合法值 / valid values: {_VALID_CAPABILITIES}"
                )
        return v


class AIModelUpdate(BaseModel):
    provider_id: Optional[int] = None
    api_name: Optional[str] = Field(default=None, min_length=1, max_length=128)
    display_name: Optional[str] = Field(default=None, min_length=1, max_length=128)
    series: Optional[str] = Field(default=None, max_length=64)
    model_type: Optional[str] = Field(
        default=None, pattern=r"^(chat|embedding|reranking)$"
    )
    capabilities: Optional[list[str]] = None
    context_length: Optional[int] = Field(default=None, ge=1)
    is_enabled: Optional[bool] = None
    is_default: Optional[bool] = None
    temperature: Optional[float] = Field(default=None, ge=0, le=2)
    top_p: Optional[float] = Field(default=None, ge=0, le=1)
    qps: Optional[int] = Field(default=None, ge=1)

    @field_validator("capabilities")
    @classmethod
    def validate_capabilities(cls, v: Optional[list[str]]) -> Optional[list[str]]:
        if v is not None:
            invalid = set(v) - _VALID_CAPABILITIES
            if invalid:
                raise ValueError(
                    f"不合法的 capability 值 / Invalid capability value: {invalid}，"
                    f"合法值 / valid values: {_VALID_CAPABILITIES}"
                )
        return v


class AIModelOut(BaseModel):
    id: int
    provider_id: int
    provider_name: str
    api_name: str
    display_name: str
    series: Optional[str]
    model_type: str
    capabilities: Optional[list[str]]
    context_length: Optional[int]
    is_enabled: bool
    is_default: bool
    temperature: Optional[float]
    top_p: Optional[float]
    qps: Optional[int]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
