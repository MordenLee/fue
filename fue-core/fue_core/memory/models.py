from uuid import uuid4

from sqlalchemy import Boolean, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from fue_core.database import Base


class ChatEvent(Base):
    __tablename__ = "chat_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    conversation_id: Mapped[int] = mapped_column(Integer, index=True)
    message_id: Mapped[int] = mapped_column(Integer, index=True)
    sequence: Mapped[int] = mapped_column(Integer)
    action: Mapped[str] = mapped_column(String(32))
    content_hash: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict] = mapped_column(JSON)
    timestamp: Mapped[int] = mapped_column(Integer)


class QAPair(Base):
    __tablename__ = "chat_qa_pairs"
    __table_args__ = (UniqueConstraint("conversation_id", "signature"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    conversation_id: Mapped[int] = mapped_column(Integer, index=True)
    user_message_id: Mapped[int] = mapped_column(Integer, index=True)
    assistant_message_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    user_event_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    assistant_event_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    state: Mapped[str] = mapped_column(String(24), default="complete")
    position: Mapped[int] = mapped_column(Integer)
    timestamp: Mapped[int] = mapped_column(Integer, index=True)
    signature: Mapped[str] = mapped_column(String(64))
    question: Mapped[str] = mapped_column(Text)
    answer: Mapped[str] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    lexical_indexed: Mapped[bool] = mapped_column(Boolean, default=False)
    vector_model_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    index_error: Mapped[str | None] = mapped_column(Text, nullable=True)


class ContextEvent(Base):
    __tablename__ = "context_events"
    __table_args__ = (UniqueConstraint("conversation_id", "sequence"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    conversation_id: Mapped[int] = mapped_column(Integer, index=True)
    sequence: Mapped[int] = mapped_column(Integer)
    run_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    type: Mapped[str] = mapped_column(String(48))
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    timestamp: Mapped[int] = mapped_column(Integer)


class ContextSummary(Base):
    __tablename__ = "context_summaries"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    conversation_id: Mapped[int] = mapped_column(Integer, index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    items: Mapped[list] = mapped_column(JSON)
    dependencies: Mapped[list] = mapped_column(JSON)
    markdown: Mapped[str] = mapped_column(Text)
    file_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    projection_state: Mapped[str] = mapped_column(String(24), default="pending")
    timestamp: Mapped[int] = mapped_column(Integer)


class ConversationMaterial(Base):
    __tablename__ = "conversation_materials"
    __table_args__ = (UniqueConstraint("pair_id"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    conversation_id: Mapped[int] = mapped_column(Integer, index=True)
    pair_id: Mapped[str] = mapped_column(String(36), index=True)
    signature: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(24), default="pending")
    decision: Mapped[str] = mapped_column(String(24), default="undecided")
    result: Mapped[str] = mapped_column(Text, default="")
    timestamp: Mapped[int] = mapped_column(Integer)


class ModelUsage(Base):
    __tablename__ = "model_usage"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    conversation_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    run_id: Mapped[str] = mapped_column(String(36), index=True)
    category: Mapped[str] = mapped_column(String(24))
    model_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(24))
    input_estimated: Mapped[int] = mapped_column(Integer)
    output_estimated: Mapped[int] = mapped_column(Integer)
    usage: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    elapsed_ms: Mapped[int] = mapped_column(Integer)
    timestamp: Mapped[int] = mapped_column(Integer)
