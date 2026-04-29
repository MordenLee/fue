"""SQLAlchemy model & Pydantic schemas for application settings."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field
from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class Setting(Base):
    """Key-value store for application settings / 应用设置键值存储。"""

    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(
        String(128), primary_key=True, comment="Setting key / 设置键名"
    )
    value: Mapped[str] = mapped_column(
        Text, nullable=False, comment="Setting value (JSON string) / 设置值（JSON 字符串）"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


# ---------------------------------------------------------------------------
# Default settings / 默认设置
# ---------------------------------------------------------------------------

DEFAULTS: dict[str, str] = {
    "language": "zh",              # "zh" | "en"
    "embed_max_concurrency": "4",  # max parallel embedding API calls during indexing
    "embed_use_model_qps": "false",  # whether to derive embedding concurrency from embedding model qps
    "kb_index_max_workers": "4",  # max document-level indexing workers for batch add/reindex
    "default_embed_model_id": "",  # empty string = no default; store as numeric string when set
    "pdf_parser": "pdfplumber",    # "pdfplumber" | "pymupdf" | "pypdf"
    "docx_parser": "python-docx",  # "python-docx" | "markitdown"
    "rag_top_k": "5",              # default number of chunks retrieved per RAG query
    "hybrid_keyword_floor_top_k": "10",  # hybrid mode: guaranteed keyword chunk budget
    # --- Auxiliary models (empty = disabled) ---
    "doc_clean_model_id": "",      # chat model ID for document text cleaning
    "chat_summary_model_id": "",   # chat model ID for conversation summarization
    "info_extract_model_id": "",   # chat model ID for citation + abstract extraction
    "chat_citation_mode": "document",  # citation granularity in chat: document | chunk
    "chat_citation_style": "apa",  # default citation style for chat: apa | mla | chicago | gb_t7714
    # --- Chat context control ---
    "chat_history_turns": "5",     # number of recent turns to pass to the LLM (0 = unlimited)
    "chat_max_tool_rounds": "5",   # max tool-calling rounds per RAG turn
    "chat_compress_model_id": "",  # chat model ID for compressing old history (empty = disabled)
    # --- Cleaner behaviour ---
    "doc_clean_keep_references": "false",  # whether to keep reference/bibliography sections during cleaning
    "doc_clean_keep_annotations": "false",  # whether to keep annotation/footnote/endnote sections during cleaning
}


# ---------------------------------------------------------------------------
# Pydantic Schemas
# ---------------------------------------------------------------------------

class SettingsOut(BaseModel):
    """Full settings object returned to clients / 完整设置对象。"""
    language: str = Field(examples=["zh"], description="UI language: zh / en")
    embed_max_concurrency: int = Field(
        default=4,
        ge=1,
        le=32,
        description="Max parallel embedding API calls during file indexing (controls QPS)",
        examples=[4],
    )
    embed_use_model_qps: bool = Field(
        default=False,
        description="Whether embedding concurrency should follow the embedding model's QPS (true = auto, false = manual embed_max_concurrency)",
        examples=[False],
    )
    kb_index_max_workers: int = Field(
        default=4,
        ge=1,
        le=16,
        description="Max parallel document indexing workers for batch add/reindex (document-level concurrency)",
        examples=[4],
    )
    default_embed_model_id: int | None = Field(
        default=None,
        description="Default embedding model ID pre-filled when creating a new knowledge base",
        examples=[1],
    )
    pdf_parser: str = Field(
        default="pdfplumber",
        pattern=r"^(pdfplumber|pymupdf|pypdf)$",
        description="PDF parsing engine: pdfplumber (default) | pymupdf | pypdf",
        examples=["pdfplumber"],
    )
    docx_parser: str = Field(
        default="python-docx",
        pattern=r"^(python-docx|markitdown)$",
        description="DOCX parsing engine: python-docx (default) | markitdown",
        examples=["python-docx"],
    )
    # --- Auxiliary models ---
    rag_top_k: int = Field(
        default=5,
        ge=1,
        le=100,
        description="Default number of chunks retrieved per RAG query (1–100)",
        examples=[5],
    )
    hybrid_keyword_floor_top_k: int = Field(
        default=10,
        ge=1,
        le=100,
        description="Hybrid retrieval: minimum keyword chunks to keep (1–100)",
        examples=[10],
    )
    doc_clean_model_id: int | None = Field(
        default=None,
        description="Chat model ID used to clean parsed document text (null = disabled)",
        examples=[2],
    )
    chat_summary_model_id: int | None = Field(
        default=None,
        description="Chat model ID used to summarize each conversation turn (null = disabled)",
        examples=[2],
    )
    info_extract_model_id: int | None = Field(
        default=None,
        description="Chat model ID used to extract citation metadata + abstract from documents (null = disabled)",
        examples=[2],
    )
    doc_clean_keep_references: bool = Field(
        default=False,
        description="When cleaning documents, whether to preserve reference/bibliography sections (default: False = strip them)",
        examples=[False],
    )
    doc_clean_keep_annotations: bool = Field(
        default=False,
        description="When cleaning documents, whether to preserve annotation/footnote/endnote sections (default: False = strip them)",
        examples=[False],
    )
    chat_citation_mode: str = Field(
        default="document",
        pattern=r"^(document|chunk)$",
        description="Citation granularity in chat: document (group by paper) | chunk (each chunk cited separately)",
        examples=["document"],
    )
    chat_citation_style: str = Field(
        default="apa",
        pattern=r"^(apa|mla|chicago|gb_t7714)$",
        description="Default citation style used in chat responses",
        examples=["apa"],
    )
    # --- Chat context control ---
    chat_history_turns: int = Field(
        default=5,
        ge=0,
        le=50,
        description="Number of recent conversation turns passed to the LLM (0 = unlimited)",
        examples=[5],
    )
    chat_max_tool_rounds: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Max tool-calling rounds per RAG turn (1–20)",
        examples=[5],
    )
    chat_compress_model_id: int | None = Field(
        default=None,
        description="Chat model ID used to compress old history when context nears 80% capacity (null = disabled)",
        examples=[2],
    )

    model_config = {"from_attributes": True}


class SettingsUpdate(BaseModel):
    """Partial update — only provided fields are changed / 仅更新传入的字段。"""
    language: str | None = Field(
        default=None,
        pattern=r"^(zh|en)$",
        description="UI language: zh / en",
        examples=["en"],
    )
    embed_max_concurrency: int | None = Field(
        default=None,
        ge=1,
        le=32,
        description="Max parallel embedding API calls (1–32)",
        examples=[4],
    )
    embed_use_model_qps: bool | None = Field(
        default=None,
        description="Whether to auto-set embedding concurrency from embedding model QPS",
        examples=[False],
    )
    kb_index_max_workers: int | None = Field(
        default=None,
        ge=1,
        le=16,
        description="Max parallel document indexing workers for batch jobs (1–16)",
        examples=[4],
    )
    rag_top_k: int | None = Field(
        default=None,
        ge=1,
        le=100,
        description="Default number of chunks retrieved per RAG query (1–100)",
        examples=[5],
    )
    hybrid_keyword_floor_top_k: int | None = Field(
        default=None,
        ge=1,
        le=100,
        description="Hybrid retrieval: minimum keyword chunks to keep (1–100)",
        examples=[10],
    )
    default_embed_model_id: int | None = Field(
        default=None,
        description="Default embedding model ID (pass null to clear)",
        examples=[1],
    )
    pdf_parser: str | None = Field(
        default=None,
        pattern=r"^(pdfplumber|pymupdf|pypdf)$",
        description="PDF parsing engine: pdfplumber | pymupdf | pypdf",
        examples=["pymupdf"],
    )
    docx_parser: str | None = Field(
        default=None,
        pattern=r"^(python-docx|markitdown)$",
        description="DOCX parsing engine: python-docx | markitdown",
        examples=["markitdown"],
    )
    # --- Auxiliary models ---
    doc_clean_model_id: int | None = Field(
        default=None,
        description="Chat model ID for document cleaning (null = disabled)",
        examples=[2],
    )
    chat_summary_model_id: int | None = Field(
        default=None,
        description="Chat model ID for conversation summarization (null = disabled)",
        examples=[2],
    )
    info_extract_model_id: int | None = Field(
        default=None,
        description="Chat model ID for citation + abstract extraction (null = disabled)",
        examples=[2],
    )
    doc_clean_keep_references: bool | None = Field(
        default=None,
        description="Whether to preserve reference/bibliography sections when cleaning documents (false = strip them)",
        examples=[False],
    )
    doc_clean_keep_annotations: bool | None = Field(
        default=None,
        description="Whether to preserve annotation/footnote/endnote sections when cleaning documents (false = strip them)",
        examples=[False],
    )
    chat_citation_mode: str | None = Field(
        default=None,
        pattern=r"^(document|chunk)$",
        description="Citation granularity in chat: document | chunk",
        examples=["document"],
    )
    chat_citation_style: str | None = Field(
        default=None,
        pattern=r"^(apa|mla|chicago|gb_t7714)$",
        description="Default citation style used in chat responses",
        examples=["apa"],
    )
    # --- Chat context control ---
    chat_history_turns: int | None = Field(
        default=None,
        ge=0,
        le=50,
        description="Number of recent conversation turns passed to the LLM (0 = unlimited)",
        examples=[5],
    )
    chat_max_tool_rounds: int | None = Field(
        default=None,
        ge=1,
        le=20,
        description="Max tool-calling rounds per RAG turn (1–20)",
        examples=[5],
    )
    chat_compress_model_id: int | None = Field(
        default=None,
        description="Chat model ID for compressing old history (pass null to disable)",
        examples=[2],
    )
