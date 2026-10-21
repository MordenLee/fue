from uuid import uuid4

from sqlalchemy import Boolean, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


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
