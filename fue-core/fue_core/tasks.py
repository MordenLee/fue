"""Durable FUE research tasks; hosts submit goals, never their conversation store."""
import asyncio
import hashlib
import json
import time
from dataclasses import replace
from uuid import uuid4

from fastapi import APIRouter, Request, HTTPException, Query
from pydantic import BaseModel, Field, ConfigDict
from sqlalchemy import Column, String, JSON, Integer
from database import Base, SessionLocal
from fue_core.dataset.service import scope, evidence_id


class ResearchTask(Base):
    __tablename__ = "research_tasks"
    id = Column(String, primary_key=True)
    request_key = Column(String, unique=True, nullable=False)
    fingerprint = Column(String, nullable=False)
    state = Column(String, nullable=False)
    payload = Column(JSON, nullable=False)
    events = Column(JSON, nullable=False, default=list)
    result = Column(JSON)
    error = Column(String)
    created_at = Column(Integer, nullable=False)


class TaskInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_key: str = Field(min_length=1, max_length=100)
    goal: str = Field(min_length=1, max_length=20000)
    model_id: int
    kb_ids: list[int] = Field(default_factory=list, max_length=20)
    max_tool_calls: int = Field(default=5, ge=1, le=20)
    max_model_calls: int = Field(default=5, ge=1, le=10)
    timeout_seconds: int = Field(default=180, ge=10, le=600)
    input_tokens: int = Field(default=48000, ge=1000, le=200000)
    output_tokens: int = Field(default=8192, ge=256, le=32000)


class TaskManager:
    def __init__(self, lifecycle, factory=SessionLocal):
        self.lifecycle, self.factory = lifecycle, factory
        self.running = {}

    def recover(self):
        with self.factory() as db:
            db.query(ResearchTask).filter(ResearchTask.state.in_(["queued", "running"])).update(
                {ResearchTask.state: "interrupted", ResearchTask.error: "Core restarted; explicit new request required"},
                synchronize_session=False)
            db.commit()

    def submit(self, payload):
        values = payload.model_dump()
        fingerprint = hashlib.sha256(json.dumps(values, sort_keys=True).encode()).hexdigest()
        with self.factory() as db:
            scope(db, payload.kb_ids, self.lifecycle.allowed_libraries)
            from providers.chat import load_chat_model
            if load_chat_model(payload.model_id, db) is None:
                raise HTTPException(400, "Research model is unavailable")
            old = db.query(ResearchTask).filter_by(request_key=payload.request_key).first()
            if old:
                if old.fingerprint != fingerprint:
                    raise HTTPException(409, "request_key already belongs to a different task")
                return old.id
            task_id = str(uuid4())
            db.add(ResearchTask(id=task_id, request_key=payload.request_key, fingerprint=fingerprint,
                                state="queued", payload=values, events=[], created_at=int(time.time())))
            db.commit()
        self.lifecycle.active += 1
        task = asyncio.create_task(self.execute(task_id, payload))
        self.running[task_id] = task
        def done(_):
            self.running.pop(task_id, None)
            self.lifecycle.active -= 1
            self.lifecycle.touch()
        task.add_done_callback(done)
        return task_id

    def event(self, task_id, kind, data):
        with self.factory() as db:
            row = db.get(ResearchTask, task_id)
            if row.state not in {"queued", "running"}:
                return
            events = list(row.events)
            events.append({"sequence": len(events)+1, "type": kind, "data": data, "timestamp": int(time.time())})
            row.events = events
            db.commit()

    async def execute(self, task_id, payload):
        try:
            with self.factory() as db:
                row = db.get(ResearchTask, task_id)
                if row.state != "queued":
                    return
                row.state = "running"
                db.commit()
            result = await asyncio.wait_for(self.research(task_id, payload), payload.timeout_seconds)
            with self.factory() as db:
                row = db.get(ResearchTask, task_id)
                if row.state == "running":
                    row.state, row.result = "succeeded", result
                    db.commit()
        except asyncio.CancelledError:
            self.finish_error(task_id, "cancelled", "Cancelled")
            raise
        except Exception as exc:
            # Provider exception bodies can contain private request/config details.
            self.finish_error(task_id, "failed", type(exc).__name__)

    def finish_error(self, task_id, state, message):
        with self.factory() as db:
            row = db.get(ResearchTask, task_id)
            if row and row.state in {"queued", "running"}:
                row.state, row.error = state, message
                db.commit()

    async def research(self, task_id, payload):
        from agents.runner import AgentRunner
        from agents.runtime import get_registry
        from agents.tools import make_knowledge_binding, make_source_bindings
        from agents.usage import UsageLedger
        from fue_core.platform.tokens import estimate
        from providers.chat import load_chat_model, build_llm
        from langchain_core.messages import HumanMessage, SystemMessage
        from knowledge.documents.models import DocumentFile
        from chat.citations import build_rag_response
        with self.factory() as db:
            model = load_chat_model(payload.model_id, db)
            llm, context_length = build_llm(model), model.context_length
        agent = get_registry().resolve(has_knowledge_bases=bool(payload.kb_ids), history_enabled=False)
        limits = agent.definition.limits.model_copy(update={"max_model_calls": payload.max_model_calls,
                    "max_tool_calls": payload.max_tool_calls, "run_timeout_seconds": payload.timeout_seconds})
        agent = replace(agent, definition=agent.definition.model_copy(update={"limits": limits}))
        retrieved = []
        bindings = [make_knowledge_binding(payload.kb_ids, retrieved, self.factory)] if payload.kb_ids else []
        bindings += [b for b in make_source_bindings(payload.kb_ids, self.factory, retrieved) if b.id in agent.tool_ids]
        # Independent research has only the explicit document scope. The Studio
        # history setting must not grant this task additional chat sources.
        for binding in bindings:
            if binding.id == "sources.read":
                original = binding.execute
                async def read_document(args, execute=original):
                    if args.get("source") != "knowledge":
                        raise PermissionError("This research task has no chat-history grant")
                    return await execute(args)
                binding.execute = read_document
        runner = AgentRunner(agent, llm, bindings, context_length=context_length)
        runner.model_id = payload.model_id
        runner.ledger = UsageLedger(input_limit=payload.input_tokens, output_limit=payload.output_tokens,
            per_input=12000, per_output=min(2048, payload.output_tokens),
            schema_tokens=sum(estimate(b.schema.args_schema.model_json_schema())+estimate(b.schema.description) for b in bindings),
            sink=lambda category, model, info: self.event(task_id, "usage", {"category": category, "model_id": model, **info}))
        runner.activity_sink = lambda kind, data: self.event(task_id, kind, data)
        answer = None
        async for event in runner.events([SystemMessage(content=agent.instructions), HumanMessage(content=payload.goal)], streaming=False):
            if event.type in {"tool_call", "tool_result"}:
                self.event(task_id, event.type, event.data)
            if event.type == "final":
                answer = event.data
        if answer is None:
            raise ValueError("Research did not produce a final answer")
        with self.factory() as db:
            if payload.kb_ids:
                content, references, _ = build_rag_response(answer, retrieved, db, "apa", existing_references=[])
            else:
                content, references = answer, []
            evidence = []
            for chunk in retrieved:
                doc = db.get(DocumentFile, chunk.document_file_id)
                if doc:
                    evidence.append({"evidence_id": evidence_id(doc, chunk.chunk_index, chunk.content),
                                     "document_id": doc.id, "chunk_index": chunk.chunk_index})
        return {"content": content, "references": references, "retrieved_evidence": evidence,
                "usage": runner.ledger.records, "termination_reason": "completed"}

    def cancel(self, task_id):
        self.finish_error(task_id, "cancelled", "Cancelled by caller")
        task = self.running.get(task_id)
        if task:
            task.cancel()

    async def close(self):
        tasks = list(self.running.items())
        for task_id, task in tasks:
            self.finish_error(task_id, "interrupted", "Core stopped")
            task.cancel()
        await asyncio.gather(*(task for _, task in tasks), return_exceptions=True)


router = APIRouter(prefix="/api/v1/tasks")


@router.post("")
async def submit(payload: TaskInput, request: Request):
    task_id = request.app.state.tasks.submit(payload)
    return {"task_id": task_id}


def task_row(task_id, request, db):
    row = db.get(ResearchTask, task_id)
    if row is None:
        raise HTTPException(404, "Task not found")
    scope(db, row.payload["kb_ids"], request.app.state.core.allowed_libraries)
    return row


@router.get("/{task_id}")
def get(task_id: str, request: Request, after: int = Query(0, ge=0)):
    with SessionLocal() as db:
        row = task_row(task_id, request, db)
        events = [e for e in row.events if e["sequence"] > after][:50]
        return {"task_id": row.id, "state": row.state, "result": row.result, "error": row.error,
                "events": events, "last_sequence": events[-1]["sequence"] if events else after,
                "more_events": bool(events and events[-1]["sequence"] < len(row.events))}


@router.post("/{task_id}/cancel")
async def cancel(task_id: str, request: Request):
    with SessionLocal() as db:
        task_row(task_id, request, db)
    request.app.state.tasks.cancel(task_id)
    return {"task_id": task_id, "cancel_requested": True}
