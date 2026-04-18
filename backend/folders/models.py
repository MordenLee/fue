"""ORM models and Pydantic schemas for Folder."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field
from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


# ---------------------------------------------------------------------------
# ORM Model
# ---------------------------------------------------------------------------

class Folder(Base):
    """A named group for organizing conversations or knowledge bases."""

    __tablename__ = "folders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    # 'conversations' | 'knowledge'
    scope: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


# ---------------------------------------------------------------------------
# Pydantic Schemas
# ---------------------------------------------------------------------------

class FolderCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    scope: str = Field(..., pattern=r"^(conversations|knowledge)$")


class FolderUpdate(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)


class FolderOut(BaseModel):
    id: int
    name: str
    scope: str
    created_at: datetime

    model_config = {"from_attributes": True}
