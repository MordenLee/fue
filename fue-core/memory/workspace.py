"""User-facing working-memory inspector. Model recall remains permission checked."""
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Literal

from database import get_db
from conversations.models import Conversation
from memory.models import QAPair, ContextSummary, ConversationMaterial, ContextEvent, ModelUsage
from memory.service import INDEX_LOCK
from memory.working import event, invalidate, project, read_memory
import time

router = APIRouter(prefix="/api/memory/conversations", tags=["working-memory"])


def require(db, cid):
    if db.get(Conversation, cid) is None:
        raise HTTPException(status_code=404, detail="Conversation not found")


@router.get("/{cid}/context")
def inspect_context(cid: int, offset: int = Query(0, ge=0), db=Depends(get_db)):
    require(db, cid)
    head = db.query(ContextSummary).filter_by(conversation_id=cid, active=True).first()
    if head:
        # Repair only from a valid authoritative head; no model call.
        with INDEX_LOCK:
            project(db, head); db.commit()
    pairs = db.query(QAPair).filter_by(conversation_id=cid, active=True, state="complete").order_by(QAPair.position.desc()).offset(offset).limit(20).all()
    materials = {m.pair_id: m for m in db.query(ConversationMaterial).filter_by(conversation_id=cid)}
    events = db.query(ContextEvent).filter_by(conversation_id=cid).order_by(ContextEvent.sequence.desc()).limit(30).all()
    usage = db.query(ModelUsage).filter_by(conversation_id=cid).order_by(ModelUsage.timestamp.desc(), ModelUsage.id.desc()).limit(100).all()
    return {"summary": {"id": head.id, "markdown": head.markdown, "projection_state": head.projection_state} if head else None,
            "pairs": [{"id": p.id, "question": p.question[:160], "position": p.position,
                       "material": {"id": materials[p.id].id, "status": materials[p.id].status,
                                    "decision": materials[p.id].decision, "result": materials[p.id].result} if p.id in materials else None} for p in pairs],
            "next_offset": offset + 20 if len(pairs) == 20 else None,
            "events": [{"id": e.id, "sequence": e.sequence, "type": e.type, "timestamp": e.timestamp,
                        "data": {k:v for k,v in e.payload.items() if k not in {"dependencies", "selected_pairs", "material_refs"}}} for e in events],
            "usage": [{"run_id": u.run_id, "category": u.category, "status": u.status,
                       "input_estimated": u.input_estimated, "output_estimated": u.output_estimated,
                       "usage": u.usage, "elapsed_ms": u.elapsed_ms} for u in usage]}


class MaterialUpdate(BaseModel):
    pair_id: str
    status: Literal["pending", "completed"]
    decision: Literal["undecided", "selected", "not_selected"] = "undecided"
    result: str = Field(default="", max_length=800)


@router.put("/{cid}/material")
def update_material(cid: int, payload: MaterialUpdate, db=Depends(get_db)):
    with INDEX_LOCK:
        require(db, cid)
        pair = db.query(QAPair).filter_by(id=payload.pair_id, conversation_id=cid, active=True, state="complete").first()
        if pair is None:
            raise HTTPException(status_code=404, detail="Current QA pair not found")
        if payload.status == "completed" and not payload.result.strip():
            raise HTTPException(status_code=400, detail="A completed material needs a result or reason")
        row = db.query(ConversationMaterial).filter_by(pair_id=pair.id).first()
        if row is None:
            row = ConversationMaterial(conversation_id=cid, pair_id=pair.id, signature=pair.signature)
            db.add(row)
        row.status, row.decision, row.result = payload.status, payload.decision, payload.result.strip()
        row.timestamp = int(time.time())
        invalidate(db, cid)
        db.flush()
        event(db, cid, "material_updated", {"material_id": row.id, "status": row.status, "decision": row.decision})
        db.commit()
        return {"id": row.id, "status": row.status}


@router.get("/{cid}/read")
def read(cid: int, ref: str, offset: int = Query(0, ge=0), length: int = Query(2000, ge=100, le=4000), db=Depends(get_db)):
    require(db, cid)
    # Prevent a reference in this conversation inspector from opening another conversation.
    kind, _, key = ref.partition(":")
    cls = {"chat": QAPair, "material": ConversationMaterial, "compaction": ContextEvent}.get(kind)
    row = db.get(cls, key) if cls else None
    if row is None or row.conversation_id != cid:
        raise HTTPException(status_code=404, detail="Reference not found in this conversation")
    try:
        return read_memory(db, ref, offset, length)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
