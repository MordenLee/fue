"""CRUD API for Folders."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from database import get_db
from folders.models import Folder, FolderCreate, FolderOut, FolderUpdate

router = APIRouter(prefix="/api/folders", tags=["folders"])


@router.get("", response_model=list[FolderOut])
def list_folders(
    scope: str = Query(..., description="conversations | knowledge"),
    db: Session = Depends(get_db),
):
    """List all folders for the given scope, ordered by creation time."""
    return (
        db.query(Folder)
        .filter(Folder.scope == scope)
        .order_by(Folder.created_at)
        .all()
    )


@router.post("", response_model=FolderOut, status_code=status.HTTP_201_CREATED)
def create_folder(payload: FolderCreate, db: Session = Depends(get_db)):
    """Create a new folder."""
    folder = Folder(name=payload.name, scope=payload.scope)
    db.add(folder)
    db.commit()
    db.refresh(folder)
    return folder


@router.patch("/{folder_id}", response_model=FolderOut)
def rename_folder(
    folder_id: int,
    payload: FolderUpdate,
    db: Session = Depends(get_db),
):
    """Rename a folder."""
    folder = db.get(Folder, folder_id)
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")
    folder.name = payload.name
    db.commit()
    db.refresh(folder)
    return folder


@router.delete("/{folder_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_folder(folder_id: int, db: Session = Depends(get_db)):
    """Delete a folder and unlink all items that were inside it."""
    folder = db.get(Folder, folder_id)
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")
    # Cascade: clear folder_id from affected rows (SQLite FKs are off by default)
    db.execute(
        text("UPDATE conversations SET folder_id = NULL WHERE folder_id = :fid"),
        {"fid": folder_id},
    )
    db.execute(
        text("UPDATE knowledge_bases SET folder_id = NULL WHERE folder_id = :fid"),
        {"fid": folder_id},
    )
    db.delete(folder)
    db.commit()
