"""ORM models and Pydantic schemas for DocumentFile and Citation."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field
from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


# ---------------------------------------------------------------------------
# ORM Models
# ---------------------------------------------------------------------------

class DocumentFile(Base):
    """A file uploaded to a knowledge base."""

    __tablename__ = "document_files"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    knowledge_base_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("knowledge_bases.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    original_filename: Mapped[str] = mapped_column(
        String(256), nullable=False, comment="Original filename / 原始文件名"
    )
    file_path: Mapped[str] = mapped_column(
        String(512), nullable=False, comment="Storage path on disk / 磁盘存储路径"
    )
    file_type: Mapped[str] = mapped_column(
        String(32), nullable=False, comment="File extension: pdf / txt / md / docx"
    )
    file_size: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="File size in bytes / 文件大小（字节）"
    )
    # pending → processing → indexed / failed
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="pending",
        comment="Processing status: pending / processing / indexed / failed",
    )
    error_message: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, comment="Error message if processing failed / 处理失败时的错误信息"
    )
    chunk_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="Number of chunks indexed / 已索引切片数"
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    indexed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="When indexing finished / 索引完成时间"
    )
    abstract: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True,
        comment="Auto-extracted or manually provided abstract / 文档摘要（信息抽取模型自动填充）"
    )

    knowledge_base: Mapped["knowledge.models.KnowledgeBase"] = relationship(  # type: ignore[name-defined]
        "KnowledgeBase", back_populates="documents"
    )
    citation: Mapped[Optional["Citation"]] = relationship(
        "Citation", back_populates="document", uselist=False, cascade="all, delete-orphan"
    )


class Citation(Base):
    """Bibliographic citation metadata attached to a DocumentFile.

    Stores structured reference information that is used when formatting
    in-text citations or reference lists during RAG-backed conversations.
    """

    __tablename__ = "citations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    document_file_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("document_files.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,   # 1 citation per document
        index=True,
        comment="Linked document file / 关联文档",
    )

    # Reference type
    citation_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="other",
        comment="Reference type: article / book / chapter / thesis / conference / website / other",
    )

    # Core bibliographic fields
    title: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="Work title / 标题")
    authors: Mapped[Optional[list]] = mapped_column(
        JSON, nullable=True, comment="Author list — ordered array of full name strings / 作者列表"
    )
    year: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, comment="Publication year / 发表年份")

    # Publication details
    source: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True,
        comment="Journal / book / conference / website name / 期刊、书名、会议或网站名称"
    )
    volume: Mapped[Optional[str]] = mapped_column(String(32), nullable=True, comment="Volume / 卷")
    issue: Mapped[Optional[str]] = mapped_column(String(32), nullable=True, comment="Issue / 期")
    pages: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, comment="Page range, e.g. 12-25 / 页码")
    publisher: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="Publisher / 出版社")
    edition: Mapped[Optional[str]] = mapped_column(String(32), nullable=True, comment="Edition / 版次")

    # Identifiers
    doi: Mapped[Optional[str]] = mapped_column(String(256), nullable=True, comment="DOI")
    isbn: Mapped[Optional[str]] = mapped_column(String(32), nullable=True, comment="ISBN")
    url: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="URL")
    accessed_date: Mapped[Optional[str]] = mapped_column(
        String(32), nullable=True, comment="URL access date (for websites) / 网页访问日期"
    )

    # Raw / unparsed citation text (pasted by user, for future auto-parsing)
    raw_citation: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True,
        comment="Raw citation string pasted by user — reserved for future auto-parsing / 用户粘贴的原始引用文本"
    )

    # Escape hatch for uncommon fields
    extra: Mapped[Optional[dict]] = mapped_column(
        JSON, nullable=True, comment="Extra fields not covered above / 其他补充字段"
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    document: Mapped[DocumentFile] = relationship("DocumentFile", back_populates="citation")


# ---------------------------------------------------------------------------
# Pydantic Schemas
# ---------------------------------------------------------------------------

class DocumentFileOut(BaseModel):
    id: int
    knowledge_base_id: int
    original_filename: str
    file_type: str
    file_size: int
    status: str
    error_message: Optional[str]
    chunk_count: int
    created_at: datetime
    indexed_at: Optional[datetime]
    has_citation: bool = False
    abstract: Optional[str] = None

    model_config = {"from_attributes": True}


class CitationCreate(BaseModel):
    citation_type: str = Field(
        default="other",
        pattern=r"^(article|book|chapter|thesis|conference|website|other)$",
        description="Reference type",
        examples=["article"],
    )
    title: Optional[str] = Field(default=None, examples=["Attention Is All You Need"])
    authors: Optional[list[str]] = Field(
        default=None,
        description="Ordered list of author full names",
        examples=[["Vaswani, Ashish", "Shazeer, Noam"]],
    )
    year: Optional[int] = Field(default=None, ge=1000, le=9999, examples=[2017])
    source: Optional[str] = Field(default=None, examples=["Advances in Neural Information Processing Systems"])
    volume: Optional[str] = Field(default=None, examples=["30"])
    issue: Optional[str] = Field(default=None, examples=["4"])
    pages: Optional[str] = Field(default=None, examples=["5998-6008"])
    publisher: Optional[str] = Field(default=None, examples=["MIT Press"])
    edition: Optional[str] = Field(default=None, examples=["2nd"])
    doi: Optional[str] = Field(default=None, examples=["10.48550/arXiv.1706.03762"])
    isbn: Optional[str] = Field(default=None, examples=["978-3-16-148410-0"])
    url: Optional[str] = Field(default=None, examples=["https://arxiv.org/abs/1706.03762"])
    accessed_date: Optional[str] = Field(default=None, examples=["2024-01-15"])
    raw_citation: Optional[str] = Field(
        default=None,
        description="Paste the raw citation text here. Auto-parsing will be available in a future version.",
    )
    extra: Optional[dict] = Field(default=None)


class CitationUpdate(CitationCreate):
    """All fields optional for partial updates."""
    citation_type: Optional[str] = Field(  # type: ignore[assignment]
        default=None,
        pattern=r"^(article|book|chapter|thesis|conference|website|other)$",
    )


class CitationOut(CitationCreate):
    id: int
    document_file_id: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class CitationFormatted(BaseModel):
    style: str
    text: str
