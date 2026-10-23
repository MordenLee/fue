"""Versioned, narrow external API. Host histories cannot be written here."""
import asyncio
from typing import Literal
from fastapi import APIRouter, Depends, Request, Query, HTTPException
from pydantic import BaseModel, Field
from fue_core.database import get_db, SessionLocal
from fue_core.dataset import service
from fue_core.knowledge.documents.models import DocumentFile

router = APIRouter(prefix="/api/v1")


def allowed(request):
    return request.app.state.core.allowed_libraries


def page(rows, offset, limit, convert):
    rows = rows.offset(offset).limit(limit+1).all()
    return {"items": [convert(row) for row in rows[:limit]],
            "next_offset": offset+limit if len(rows) > limit else None, "complete": len(rows) <= limit}


@router.get("/dataset/libraries")
def libraries(request: Request, offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100), db=Depends(get_db)):
    return page(service.libraries(db, allowed(request)), offset, limit,
                lambda row: {"id": row.id, "name": row.name, "description": row.description})


@router.get("/dataset/papers")
def papers(request: Request, library: int, offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100), db=Depends(get_db)):
    service.scope(db, [library], allowed(request))
    return page(db.query(DocumentFile).filter_by(knowledge_base_id=library).order_by(DocumentFile.id), offset, limit,
                lambda row: {"id": row.id, "filename": row.original_filename, "status": row.status, "chunks": row.chunk_count})


class Search(BaseModel):
    query: str = Field(min_length=1, max_length=4000)
    kb_ids: list[int] | None = Field(default=None, max_length=20)
    mode: Literal["keyword", "vector", "hybrid"] = "keyword"
    limit: int = Field(default=5, ge=1, le=20)


@router.post("/dataset/search")
def search(payload: Search, request: Request, db=Depends(get_db)):
    return service.search(db, **payload.model_dump(), allowed=allowed(request))


@router.get("/dataset/read")
def read(request: Request, ref: str, before: int = Query(0, ge=0, le=3), after: int = Query(0, ge=0, le=3),
         offset: int = Query(0, ge=0), length: int = Query(2000, ge=100, le=4000), db=Depends(get_db)):
    return service.read(db, ref, before, after, offset, length, allowed(request))


@router.get("/dataset/cite")
def cite(request: Request, document_id: int, style: Literal["apa", "mla", "chicago", "gb_t7714"] = "apa", db=Depends(get_db)):
    from fue_core.knowledge.documents.citations import format_citation
    doc = service.document(db, document_id, allowed(request))
    if doc.citation is None:
        raise HTTPException(404, "Bibliographic metadata is unavailable")
    return {"document_id": doc.id, "style": style, "text": format_citation(doc.citation, style)}


@router.post("/memory/search")
async def memory_search(payload: dict):
    from fue_core.agents.tools import HistoryArguments
    from fue_core.memory.service import search
    from pydantic import ValidationError
    try:
        values = HistoryArguments.model_validate(payload).model_dump()
    except ValidationError as exc:
        raise HTTPException(422, str(exc)) from exc
    def run():
        with SessionLocal() as db:
            return search(db, **values)
    try:
        return await asyncio.to_thread(run)
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from exc


@router.get("/memory/read")
def memory_read(ref: str, offset: int = Query(0, ge=0), length: int = Query(2000, ge=100, le=4000), db=Depends(get_db)):
    from fue_core.memory.working import read_memory
    try:
        return read_memory(db, ref, offset, length)
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from exc
    except (ValueError, KeyError) as exc:
        raise HTTPException(404, str(exc)) from exc
