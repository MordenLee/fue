"""ORM models and Pydantic schemas for Conversation and Message."""

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

class Conversation(Base):
    """A named chat session, optionally linked to knowledge bases."""

    __tablename__ = "conversations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    title: Mapped[str] = mapped_column(
        String(256), nullable=False, default="New Conversation",
        comment="Conversation title (auto-generated or user-edited)",
    )
    summary: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True,
        comment="Auto-generated or user-edited summary of the conversation",
    )
    # Which AI model was used (nullable — may change mid-conversation in future)
    model_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("ai_models.id", ondelete="SET NULL"),
        nullable=True, index=True,
    )
    # Linked knowledge bases (stored as JSON array of kb IDs)
    kb_ids: Mapped[Optional[list]] = mapped_column(
        JSON, nullable=True,
        comment="Knowledge base IDs associated with this conversation",
    )
    # Citation style used for RAG responses
    citation_style: Mapped[Optional[str]] = mapped_column(
        String(32), nullable=True, default="apa",
        comment="Citation style: apa / mla / chicago / gb_t7714",
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

    messages: Mapped[list["Message"]] = relationship(
        "Message", back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="Message.position",
    )


class Message(Base):
    """A single message within a conversation."""

    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    conversation_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    # "system" | "user" | "assistant"
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # Position in conversation (0-based, monotonically increasing)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # For assistant messages from RAG: store the reference list as JSON
    references: Mapped[Optional[list]] = mapped_column(
        JSON, nullable=True,
        comment="Citation references for RAG assistant messages",
    )

    # Model used to generate this assistant message
    model_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("ai_models.id", ondelete="SET NULL"),
        nullable=True, index=True,
        comment="AI model used to generate this message (assistant only)",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    conversation: Mapped["Conversation"] = relationship("Conversation", back_populates="messages")


# ---------------------------------------------------------------------------
# Pydantic Schemas
# ---------------------------------------------------------------------------

class MessageOut(BaseModel):
    id: int
    conversation_id: int
    role: str
    content: str
    position: int
    references: Optional[list] = None
    model_id: Optional[int] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ConversationOut(BaseModel):
    id: int
    title: str
    summary: Optional[str]
    model_id: Optional[int]
    kb_ids: Optional[list]
    citation_style: Optional[str]
    folder_id: Optional[int] = None
    created_at: datetime
    updated_at: datetime
    message_count: int = 0

    model_config = {"from_attributes": True}


class ConversationDetail(ConversationOut):
    """Full conversation with all messages."""
    messages: list[MessageOut] = []


class ConversationCreate(BaseModel):
    title: str = Field(default="New Conversation", max_length=256)
    model_id: Optional[int] = None
    kb_ids: Optional[list[int]] = None
    citation_style: Optional[str] = Field(
        default="apa",
        pattern=r"^(apa|mla|chicago|gb_t7714)$",
    )


class ConversationUpdate(BaseModel):
    title: Optional[str] = Field(default=None, max_length=256)
    summary: Optional[str] = None
    model_id: Optional[int] = None
    kb_ids: Optional[list[int]] = None
    citation_style: Optional[str] = Field(
        default=None,
        pattern=r"^(apa|mla|chicago|gb_t7714)$",
    )
    folder_id: Optional[int] = None


class MessageCreate(BaseModel):
    role: str = Field(..., pattern=r"^(system|user|assistant)$")
    content: str = Field(..., min_length=1)
    references: Optional[list] = None


class MessageAppend(BaseModel):
    """Append one or more messages to a conversation (e.g. user + assistant pair)."""
    messages: list[MessageCreate] = Field(..., min_length=1)


class MatchedMessage(BaseModel):
    message_id: int
    role: str
    snippet: str       # up to 200 chars surrounding the match
    position: int


class ConversationSearchResult(BaseModel):
    """A conversation that matched a search query, with the snippet(s) that matched."""
    conversation: ConversationOut
    matched_in_title: bool
    matched_in_summary: bool
    matched_messages: list[MatchedMessage]


# Fix forward reference
MessageAppend.model_rebuild()
