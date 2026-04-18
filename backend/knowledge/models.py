"""SQLAlchemy models & Pydantic schemas for KnowledgeBase.

DocumentFile and Citation live in knowledge/documents/models.py.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from pydantic import BaseModel, Field
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base

if TYPE_CHECKING:
    from knowledge.documents.models import DocumentFile


class KnowledgeBase(Base):
    """知识库，对应 ChromaDB 中的一个 collection。"""

    __tablename__ = "knowledge_bases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(
        String(128), nullable=False, comment="Knowledge base name / 知识库名称"
    )
    description: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, comment="Description / 描述"
    )
    # ChromaDB collection name — 自动生成，格式: kb_{id}
    collection_name: Mapped[Optional[str]] = mapped_column(
        String(128), nullable=True, unique=True, comment="ChromaDB collection name"
    )
    # 使用哪个 embedding 模型
    embed_model_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("ai_models.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
        comment="Embedding model ID / 向量化模型 ID",
    )
    # 切片参数
    chunk_size: Mapped[int] = mapped_column(
        Integer, nullable=False, default=500, comment="Chunk size in characters / 切片大小（字符数）"
    )
    chunk_overlap: Mapped[int] = mapped_column(
        Integer, nullable=False, default=50, comment="Chunk overlap in characters / 切片重叠（字符数）"
    )
    use_delimiter_split: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True,
        comment="Use semantic delimiter-aware splitting / 使用分割符优化切割"
    )
    # Rerank 模型（可选）
    rerank_model_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("ai_models.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="Reranking model ID (optional) / Rerank 模型 ID（可空）",
    )

    folder_id: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True, index=True,
        comment="FK to folders.id (soft, no constraint)",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    documents: Mapped[list["DocumentFile"]] = relationship(
        "DocumentFile", back_populates="knowledge_base", cascade="all, delete-orphan"
    )


# ---------------------------------------------------------------------------
# Pydantic Schemas
# ---------------------------------------------------------------------------

class KnowledgeBaseCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=128, examples=["项目文档库"])
    description: Optional[str] = Field(default=None, examples=["存储项目相关文档"])
    embed_model_id: int = Field(..., description="Embedding 模型 ID")
    chunk_size: int = Field(default=500, ge=100, le=4000, description="切片大小（字符数）")
    chunk_overlap: int = Field(default=50, ge=0, le=1000, description="切片重叠（字符数）")
    use_delimiter_split: bool = Field(default=True, description="使用分割符优化切割（默认开启）")
    rerank_model_id: Optional[int] = Field(default=None, description="Rerank 模型 ID（可空）")


class KnowledgeBaseUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=128)
    description: Optional[str] = None
    embed_model_id: Optional[int] = None
    chunk_size: Optional[int] = Field(default=None, ge=100, le=4000)
    chunk_overlap: Optional[int] = Field(default=None, ge=0, le=1000)
    use_delimiter_split: Optional[bool] = None
    rerank_model_id: Optional[int] = None
    folder_id: Optional[int] = None


class KnowledgeBaseOut(BaseModel):
    id: int
    name: str
    description: Optional[str]
    collection_name: Optional[str]
    embed_model_id: int
    chunk_size: int
    chunk_overlap: int
    use_delimiter_split: bool = True
    rerank_model_id: Optional[int]
    folder_id: Optional[int] = None
    created_at: datetime
    updated_at: datetime
    document_count: int = 0

    model_config = {"from_attributes": True}


class SearchResult(BaseModel):
    document_id: int
    original_filename: str
    chunk_index: int
    content: str
    score: float


# ---------------------------------------------------------------------------
# Export / Import schemas
# ---------------------------------------------------------------------------

class KBImportResult(BaseModel):
    """Response returned after a successful knowledge-base import."""
    knowledge_base: KnowledgeBaseOut
    chunks_imported: int
    documents_created: int
    warnings: list[str]
