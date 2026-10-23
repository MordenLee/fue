"""Durable chat identity and shared event envelopes. No automatic model replay."""
import asyncio
import hashlib
import json
import time
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Depends, Query
from sqlalchemy import Column, String, Integer, JSON
from sqlalchemy.exc import IntegrityError
from fue_core.database import Base, get_db

router = APIRouter(prefix='/api/executions', tags=['executions'])
running = {}
cancel_requests = set()
TERMINAL = {'succeeded', 'failed', 'cancelled', 'interrupted'}


def envelope(run_id, sequence, kind, data):
    return dict(run_id=run_id, sequence=sequence, type=kind, data=data, timestamp=int(time.time()))


class Execution(Base):
    __tablename__ = 'executions'
    id = Column(String, primary_key=True)
    fingerprint = Column(String, nullable=False)
    conversation_id = Column(Integer)
    state = Column(String, nullable=False)
    result = Column(JSON)
    error = Column(String)
    created_at = Column(Integer, nullable=False)


class ExecutionEvent(Base):
    __tablename__ = 'execution_events'
    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(String, nullable=False, index=True)
    kind = Column(String, nullable=False)
    data = Column(JSON, nullable=False)
    timestamp = Column(Integer, nullable=False)


def append_event(db, key, kind, data):
    db.add(ExecutionEvent(run_id=key, kind=kind, data=data, timestamp=int(time.time())))
    db.commit()


def read_events(db, key, after=0, limit=100):
    rows = db.query(ExecutionEvent).filter(ExecutionEvent.run_id == key, ExecutionEvent.id > after).order_by(ExecutionEvent.id).limit(limit).all()
    return [dict(run_id=key, sequence=r.id, type=r.kind, data=r.data, timestamp=r.timestamp) for r in rows]


@router.get('')
def recent(conversation_id: int, db=Depends(get_db)):
    rows = db.query(Execution).filter_by(conversation_id=conversation_id).order_by(Execution.created_at.desc(), Execution.id.desc()).limit(20).all()
    return [dict(run_id=r.id, state=r.state, created_at=r.created_at) for r in rows]


def reserve(db, model_id, payload, rag):
    key = payload.request_id or str(uuid4())
    values = payload.model_dump(exclude={'request_id'})
    fingerprint = hashlib.sha256(json.dumps([model_id, rag, values], sort_keys=True).encode()).hexdigest()
    def replay(row):
        if row.fingerprint != fingerprint:
            raise HTTPException(409, 'Request ID belongs to different input')
        if row.state == 'succeeded':
            return key, row.result
        raise HTTPException(409, detail={'run_id': key, 'state': row.state,
                                        'message': 'Query the original execution; it will not be executed twice'})
    existing = db.get(Execution, key)
    if existing is not None:
        return replay(existing)
    row = Execution(id=key, fingerprint=fingerprint, conversation_id=payload.conversation_id,
                    state='running', created_at=int(time.time()))
    try:
        db.add(row)
        db.commit()
        return key, None
    except IntegrityError:
        db.rollback()
        row = db.get(Execution, key)
        if row is None:
            raise
        return replay(row)


def finish(db, key, state, result=None, error=None):
    db.rollback()
    row = db.get(Execution, key)
    if row and row.state not in TERMINAL:
        row.state, row.result, row.error = state, result, error
        db.commit()


def recover(db):
    db.query(Execution).filter(Execution.state == 'running').update(
        {'state': 'interrupted', 'error': 'Core restarted; no automatic retry'})
    db.commit()


@router.get('/{run_id}')
def status(run_id: str, after: int = Query(0, ge=0), db=Depends(get_db)):
    row = db.get(Execution, run_id)
    if not row:
        raise HTTPException(404, 'Execution not found')
    return dict(run_id=row.id, state=row.state, result=row.result, error=row.error,
                created_at=row.created_at, conversation_id=row.conversation_id,
                events=read_events(db, run_id, after))


@router.post('/{run_id}/cancel')
def cancel(run_id: str, db=Depends(get_db)):
    row = db.get(Execution, run_id)
    if not row:
        raise HTTPException(404, 'Execution not found')
    task = running.get(run_id)
    if row.state == 'running':
        cancel_requests.add(run_id)
    elif row.state == 'interrupted':
        row.state = 'cancelled'
        db.commit()
    if task:
        task.get_loop().call_soon_threadsafe(task.cancel)
    return dict(run_id=run_id, state=row.state, cancellation_requested=task is not None)


async def respond(model_id, payload, db, rag, execute):
    key, cached = reserve(db, model_id, payload, rag)
    if cached is not None:
        return cached
    payload.request_id = key
    running[key] = asyncio.current_task()
    try:
        result = await execute(model_id, payload, db, rag=rag)
        finish(db, key, 'succeeded', result.model_dump())
        return result
    except asyncio.CancelledError:
        finish(db, key, 'cancelled' if key in cancel_requests else 'interrupted')
        raise
    except Exception as exc:
        finish(db, key, 'failed', error=type(exc).__name__)
        raise
    finally:
        running.pop(key, None)
        cancel_requests.discard(key)
