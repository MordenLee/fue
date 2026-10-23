"""Memory indexing controls. Reading is available through the shared MCP tools."""

import asyncio
from fastapi import APIRouter, Depends
from sqlalchemy import func
from fue_core.database import get_db
from fue_core.memory.models import QAPair, ChatEvent
from fue_core.memory.service import embedding_model

router = APIRouter(prefix="/api/memory", tags=["memory"])


@router.get("/status")
def status(db=Depends(get_db)):
    model = embedding_model(db)
    return {"pairs": db.query(QAPair).count(), "events": db.query(ChatEvent).count(),
            "keyword_indexed": db.query(QAPair).filter_by(lexical_indexed=True).count(),
            "vector_indexed": db.query(QAPair).filter_by(vector_model_id=model.id).count() if model else 0,
            "vector_errors": db.query(QAPair).filter(QAPair.index_error.is_not(None)).count(),
            "embedding_model_id": model.id if model else None}


@router.post("/retry")
def retry(db=Depends(get_db)):
    db.query(QAPair).update({QAPair.index_error: None}, synchronize_session=False)
    db.commit()
    return {"queued": True}


@router.post("/reindex")
def reindex(db=Depends(get_db)):
    """Rebuild derived projections without modifying or deleting the raw log."""
    from fue_core.memory.service import INDEX_LOCK
    with INDEX_LOCK:
        db.query(QAPair).update({QAPair.lexical_indexed: False, QAPair.vector_model_id: None,
                                QAPair.index_error: None}, synchronize_session=False)
        db.commit()
    return {"queued": True}


async def worker(session_factory, lifecycle=None):
    from fue_core.memory.service import backfill, process_pending
    import logging
    logger = logging.getLogger(__name__)
    while True:
        try:
            if lifecycle:
                lifecycle.active += 1
            try:
                await asyncio.to_thread(backfill, session_factory)
            finally:
                if lifecycle:
                    lifecycle.active -= 1
                    lifecycle.touch()
            break
        except Exception as exc:
            logger.warning("Memory backfill retry (%s)", type(exc).__name__)
            await asyncio.sleep(3)
    while True:
        try:
            if lifecycle:
                lifecycle.active += 1
            processed = 0
            try:
                processed = await asyncio.to_thread(process_pending, session_factory)
            finally:
                if lifecycle:
                    lifecycle.active -= 1
                    if processed:
                        lifecycle.touch()
        except Exception as exc:
            logger.warning("Memory worker retry (%s)", type(exc).__name__)
        await asyncio.sleep(3)
