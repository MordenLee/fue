"""Compatibility chat API: delegate all model/tool execution to AgentRunner."""

import asyncio
import json
import logging
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func as sa_func
from sqlalchemy.orm import Session, joinedload
from sqlalchemy.orm import sessionmaker
from uuid import uuid4

from agents.context import ContextLimitError, build_context, check_context
from agents.runner import AgentRunner, AgentEvent
from agents.runtime import get_registry
from agents.tools import make_knowledge_binding, make_source_bindings
from auxmodels.rate_limiter import try_acquire
from auxmodels.summarizer import asummarize
from chat.citations import build_rag_response
from conversations.models import Conversation, Message
from database import get_db, SessionLocal
from providers.chat import build_llm, load_chat_model
from providers.models import AIModel
from settings.models import Setting
from memory.service import commit_chat, record_interruption, setting as memory_setting

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/chat", tags=["chat"])
_background_tasks: set[asyncio.Task] = set()


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"] = Field(..., examples=["user"])
    content: str = Field(..., min_length=1)


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(..., min_length=1)
    conversation_id: int | None = Field(
        default=None,
        description="If provided, the user+assistant messages of this turn are appended to the conversation.",
    )


class ChatResponse(BaseModel):
    content: str
    model: str
    provider: str
    run_id: str | None = None
    activity: list[dict] = Field(default_factory=list)
    summary: str | None = None
    """Optional summary of this conversation turn, populated when chat_summary_model_id is configured."""


# ---------------------------------------------------------------------------
# RAG Schemas
# ---------------------------------------------------------------------------

class RAGChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(..., min_length=1)
    kb_ids: list[int] = Field(..., min_length=1, description="Knowledge base IDs to search")
    conversation_id: int | None = Field(
        default=None,
        description="If provided, the user+assistant messages of this turn are appended to the conversation.",
    )
    citation_style: str = Field(
        default="apa",
        pattern=r"^(apa|mla|chicago|gb_t7714)$",
        description="Citation style: apa (default) | mla | chicago | gb_t7714",
    )
    max_tool_rounds: int | None = Field(
        default=None,
        ge=1,
        le=20,
        description="Optional lower per-request cap on search and reading tool calls",
    )
    existing_references: list[dict] = Field(
        default_factory=list,
        description="References from previous turns, each with ref_num, document_file_id, original_filename, formatted_citation",
    )


class CitationRef(BaseModel):
    model_config = {"extra": "allow"}
    ref_num: int
    document_file_id: int
    original_filename: str
    formatted_citation: str
    chunk_content: str = ""


class RAGChatResponse(BaseModel):
    content: str
    references: list[CitationRef]
    model: str
    provider: str
    run_id: str | None = None
    activity: list[dict] = Field(default_factory=list)
    summary: str | None = None




def _save_turn(
    db: Session,
    conversation_id: int,
    user_messages: list[ChatMessage],
    assistant_content: str,
    summary: str | None = None,
    references: list | None = None,
    model_id: int | None = None,
    source_user_message_id: int | None = None,
) -> None:
    """Append the last user message(s) + assistant reply to *conversation_id*.

    Also writes *summary* to the conversation record when provided.
    Raise if the conversation disappeared before persistence.
    """
    conv = db.get(Conversation, conversation_id)
    if not conv:
        raise ValueError(f"Conversation {conversation_id} no longer exists")
    if source_user_message_id is not None:
        source = db.get(Message, source_user_message_id)
        expected = next((m.content for m in reversed(user_messages) if m.role == "user"), None)
        if source is None or source.conversation_id != conversation_id or source.role != "user" or source.content != expected:
            raise ValueError("Source question changed or was deleted while generating")

    max_pos = (
        db.query(sa_func.max(Message.position))
        .filter(Message.conversation_id == conversation_id)
        .scalar()
    )
    next_pos = (max_pos + 1) if max_pos is not None else 0

    # Append only the LAST user message to avoid duplicating history
    last_user = next((m for m in reversed(user_messages) if m.role == "user"), None)
    persisted_last = db.query(Message).filter_by(conversation_id=conversation_id).order_by(Message.position.desc(), Message.id.desc()).first()
    if last_user and not (persisted_last and persisted_last.role == "user" and persisted_last.content == last_user.content):
        db.add(Message(
            conversation_id=conversation_id,
            role="user",
            content=last_user.content,
            position=next_pos,
        ))
        next_pos += 1

    db.add(Message(
        conversation_id=conversation_id,
        role="assistant",
        content=assistant_content,
        references=references,
        model_id=model_id,
        position=next_pos,
    ))

    if summary:
        conv.summary = summary
    conv.updated_at = sa_func.now()
    commit_chat(db, conversation_id, action="complete")


def _update_conv_summary(db: Session, conversation_id: int, summary: str) -> None:
    """Update only the summary field of a conversation (used after background summarization)."""
    conv = db.get(Conversation, conversation_id)
    if conv:
        conv.summary = summary
        db.commit()


def _fmt_conversation(messages: list[ChatMessage], assistant_content: str) -> str:
    """Format a conversation turn into a single string for summarization."""
    lines = [f"{m.role}: {m.content}" for m in messages]
    lines.append(f"assistant: {assistant_content}")
    return "\n".join(lines)


def _get_chat_model(model_id: int, db: Session) -> AIModel:
    """Load model with provider, validate type and enabled status."""
    record = (
        db.query(AIModel)
        .options(joinedload(AIModel.provider))
        .filter(AIModel.id == model_id)
        .first()
    )
    if not record:
        raise HTTPException(status_code=404, detail="Model not found")
    if not record.is_enabled:
        raise HTTPException(status_code=403, detail="Model is disabled")
    if not record.provider.is_enabled:
        raise HTTPException(status_code=403, detail="Provider is disabled")
    if record.model_type != "chat":
        raise HTTPException(status_code=400, detail=f"Model type is '{record.model_type}', chat is not supported")
    return record


def _setting_int(db, key, default):
    row = db.get(Setting, key)
    try:
        return int(row.value) if row and row.value else default
    except (ValueError, TypeError):
        return default


def _language(db):
    row = db.get(Setting, "language")
    return row.value if row and row.value else "zh"


def _prepare(model_id, payload, db, *, rag):
    model = _get_chat_model(model_id, db)
    if model.qps and not try_acquire(model_id, model.qps):
        raise HTTPException(status_code=429, detail="Request exceeds model QPS limit")
    if payload.conversation_id and not db.get(Conversation, payload.conversation_id):
        raise HTTPException(status_code=404, detail="Conversation not found")
    kb_ids = payload.kb_ids if rag else []
    if kb_ids:
        from knowledge.models import KnowledgeBase
        for kb_id in set(kb_ids):
            if not db.get(KnowledgeBase, kb_id):
                raise HTTPException(status_code=404, detail=f"Knowledge base not found: {kb_id}")
    history_enabled = memory_setting(db, "memory_query_scope") != "disabled"
    working_mode = memory_setting(db, "chat_context_mode") == "working"
    if working_mode and not payload.conversation_id:
        raise HTTPException(status_code=400, detail="Working context requires a saved conversation")
    agent = get_registry().resolve(has_knowledge_bases=bool(kb_ids), history_enabled=history_enabled)
    messages = build_context(agent, payload.messages, max(0, _setting_int(db, "chat_history_turns", 5)))
    try:
        if not working_mode:
            check_context(messages, model.context_length)
        llm = build_llm(model)
    except (ContextLimitError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Model initialization failed: {exc}") from exc
    retrieved = []
    existing = payload.existing_references if rag else []
    initial = max((int(ref.get("ref_num", 0)) for ref in existing), default=0) + 1
    bindings = [make_knowledge_binding(kb_ids, retrieved, SessionLocal, initial)] if "knowledge.search" in agent.tool_ids else []
    bindings += [b for b in make_source_bindings(kb_ids, SessionLocal, retrieved) if b.id in agent.tool_ids]
    runner = AgentRunner(
        agent, llm, bindings, context_length=model.context_length,
        max_tool_calls=min(max(1, _setting_int(db, "chat_max_tool_rounds", 5)),
                           payload.max_tool_rounds if rag and payload.max_tool_rounds is not None
                           else agent.definition.limits.max_tool_calls),
    )
    logger.info("Agent %s skills=%s protocol=%s", agent.definition.id, agent.skills, agent.definition.tool_protocol)
    runner.source_message_id = None
    if payload.conversation_id:
        user = next((m for m in reversed(payload.messages) if m.role == "user"), None)
        last = db.query(Message).filter_by(conversation_id=payload.conversation_id).order_by(Message.position.desc()).first()
        if user and not (last and last.role == "user" and last.content == user.content):
            last = Message(conversation_id=payload.conversation_id, role="user", content=user.content,
                           position=(last.position + 1) if last else 0)
            db.add(last)
            commit_chat(db, payload.conversation_id, action="prompt")
        if last is not None and isinstance(last.id, int):
            runner.source_message_id = last.id
    runner.run_id = str(uuid4())
    runner.activity = []
    runner.model_id = model_id
    if isinstance(db, Session):
        from agents.usage import UsageLedger
        from memory.working import save_usage, estimate, prepare
        factory = sessionmaker(bind=db.get_bind(), expire_on_commit=False)
        def sink(category, used_model, info):
            save_usage(factory, payload.conversation_id, runner.run_id, category, used_model, info)
        limits = dict(input_limit=_setting_int(db, "chat_run_input_tokens", 48000),
                      output_limit=_setting_int(db, "chat_run_output_tokens", 8192),
                      per_input=_setting_int(db, "chat_input_tokens", 12000),
                      per_output=_setting_int(db, "chat_output_tokens", 2048)) if working_mode else {}
        schema_tokens = sum(estimate(t.schema.args_schema.model_json_schema()) + estimate(t.schema.description) for t in bindings)
        runner.ledger = UsageLedger(sink=sink, schema_tokens=schema_tokens, **limits)
        def activity_sink(kind, data):
            if payload.conversation_id:
                from memory.working import event
                from memory.service import INDEX_LOCK
                with INDEX_LOCK, factory() as event_db:
                    if event_db.get(Conversation, payload.conversation_id):
                        event(event_db, payload.conversation_id, kind, data, runner.run_id)
                        event_db.commit()
        runner.activity_sink = activity_sink
        if working_mode:
            runner.context_preparer = lambda: prepare(factory, payload.conversation_id, agent, model.context_length,
                                                       kb_ids, runner.run_id, runner.ledger)
            from memory.working import fingerprint
            expected_context = fingerprint(db, payload.conversation_id)
            expected_scope = memory_setting(db, "memory_query_scope")
            def validate_context():
                with factory() as check_db:
                    if (fingerprint(check_db, payload.conversation_id) != expected_context or
                            memory_setting(check_db, "memory_query_scope") != expected_scope):
                        raise ContextLimitError("Conversation or history access changed; start a new turn")
            runner.context_validator = validate_context
    return model, runner, messages, retrieved


def _finalize(text, retrieved, payload, db, *, rag):
    if not rag:
        return text, [], {}
    return build_rag_response(text, retrieved, db, payload.citation_style,
                              existing_references=payload.existing_references)


async def _summarize(summary_model_id, language, messages, text, ledger=None):
    if not summary_model_id:
        return None
    # Every background job owns its Session, including loading its provider.
    with SessionLocal() as db:
        model = load_chat_model(summary_model_id, db)
        if not model:
            return None
        # Titles do not need the entire conversation on every turn.
        last_user = next((m for m in reversed(messages) if m.role == "user"), None)
        title_input = (last_user.content[:600] if last_user else "") + "\n" + text[:600]
        return await asummarize(title_input, model, language=language, ledger=ledger) or None


async def _summarize_background(summary_model_id, language, messages, text, conversation_id, expected_epoch, ledger=None):
    try:
        summary = await _summarize(summary_model_id, language, messages, text, ledger)
        if summary and conversation_id:
            from memory import service as memory_service
            with SessionLocal() as db:
                with memory_service.INDEX_LOCK:
                    if memory_service.DELETION_EPOCH == expected_epoch:
                        _update_conv_summary(db, conversation_id, summary)
    except Exception:
        logger.exception("Agent background summarization failed")


async def _respond(model_id, payload, db, *, rag):
    model, runner, messages, retrieved = _prepare(model_id, payload, db, rag=rag)
    text = None
    try:
        async for event in runner.events(messages, streaming=False):
            if event.type == "activity":
                runner.activity.append(event.data)
            if event.type == "final":
                text = event.data
    except Exception as exc:
        if payload.conversation_id:
            db.rollback()
            record_interruption(db, payload.conversation_id, "", "failed", runner.source_message_id,
                                next((m.content for m in reversed(payload.messages) if m.role == "user"), None))
        raise HTTPException(status_code=502, detail=f"Agent execution failed: {exc}") from exc
    if text is None:
        raise HTTPException(status_code=502, detail="Agent did not produce a final answer")
    content, references, _ = _finalize(text, retrieved, payload, db, rag=rag)
    summary = None
    try:
        summary = await _summarize(_setting_int(db, "chat_summary_model_id", None),
                                   _language(db), payload.messages, content, runner.ledger)
    except Exception:
        logger.exception("Agent summarization failed; keeping generated answer")
    if payload.conversation_id:
        _save_turn(db, payload.conversation_id, payload.messages, content, summary,
                   references if rag else None, model_id=model_id, source_user_message_id=runner.source_message_id)
    data = dict(content=content, model=model.display_name, provider=model.provider.name, summary=summary,
                run_id=runner.run_id, activity=runner.activity)
    if rag:
        data["references"] = references
        return RAGChatResponse(**data)
    return ChatResponse(**data)


def _sse(kind, value=None):
    if value is None:
        return f"data: [{kind}]\n\n"
    return f"data: [{kind}] {json.dumps(value, ensure_ascii=False)}\n\n"


async def _runner_events(runner, messages):
    """Keep the stream visibly alive without cancelling an in-flight provider call."""
    iterator, pending = runner.events(messages), None
    try:
        while True:
            if pending is None:
                pending = asyncio.create_task(anext(iterator))
            done, _ = await asyncio.wait({pending}, timeout=10)
            if not done:
                yield AgentEvent("activity", {"type": "waiting"})
                continue
            task, pending = pending, None
            try:
                yield task.result()
            except StopAsyncIteration:
                return
    finally:
        if pending:
            pending.cancel()
            await asyncio.gather(pending, return_exceptions=True)
        await iterator.aclose()


def _stream_response(model_id, payload, db, *, rag):
    _, runner, messages, retrieved = _prepare(model_id, payload, db, rag=rag)
    summary_model_id = _setting_int(db, "chat_summary_model_id", None)
    language = _language(db)
    from memory import service as memory_service
    summary_epoch = memory_service.DELETION_EPOCH

    async def generate():
        text = None
        partial = []
        try:
            yield _sse("ACTIVITY", {"type": "run_started", "run_id": runner.run_id})
            async for event in _runner_events(runner, messages):
                if event.type == "token":
                    partial.append(event.data)
                    # Legacy clients receive provisional tokens, then a JSON final replacement.
                    yield f"data: {event.data}\n\n"
                elif event.type == "clear":
                    partial.clear()
                    yield _sse("CLEAR")
                elif event.type == "tool_call":
                    yield _sse("TOOL_CALL", event.data)
                    yield _sse("ACTIVITY", {"type": "tool_started", **event.data})
                    if event.data["name"].startswith("search_"):
                        yield _sse("SEARCHING", {"query": event.data["args"].get("query", "")})
                elif event.type == "tool_result":
                    yield _sse("ACTIVITY", {"type": "tool_completed", "name": event.data.get("name", event.data["tool"]),
                                           "status": event.data["status"], "cached": event.data.get("cached", False)})
                elif event.type == "activity":
                    runner.activity.append(event.data)
                    yield _sse("ACTIVITY", event.data)
                elif event.type == "final":
                    text = event.data
            if text is None:
                raise ValueError("Agent did not produce a final answer")
            content, references, cite_map = _finalize(text, retrieved, payload, db, rag=rag)
            # A save failure must reach the client instead of pretending completion succeeded.
            if payload.conversation_id:
                _save_turn(db, payload.conversation_id, payload.messages, content, None,
                           references if rag else None, model_id=model_id, source_user_message_id=runner.source_message_id)
            if references:
                yield _sse("CITATIONS", {"references": references, "cite_map": cite_map})
            yield _sse("REPLACE", content)
            yield _sse("DONE")
            if summary_model_id and payload.conversation_id:
                task = asyncio.create_task(_summarize_background(
                    summary_model_id, language, payload.messages, content, payload.conversation_id,
                    summary_epoch, runner.ledger))
                _background_tasks.add(task)
                task.add_done_callback(_background_tasks.discard)
        except asyncio.CancelledError:
            db.rollback()
            if payload.conversation_id:
                record_interruption(db, payload.conversation_id, "".join(partial), "cancelled", runner.source_message_id,
                                    next((m.content for m in reversed(payload.messages) if m.role == "user"), None))
            raise
        except Exception as exc:
            db.rollback()
            if payload.conversation_id:
                try:
                    record_interruption(db, payload.conversation_id, "".join(partial), "failed", runner.source_message_id,
                                        next((m.content for m in reversed(payload.messages) if m.role == "user"), None))
                except Exception:
                    logger.warning("Could not persist interrupted response")
            logger.exception("Agent streaming execution failed")
            detail = str(exc).replace("\n", " ").replace("\r", " ") or type(exc).__name__
            yield f"data: [ERROR] {detail}\n\n"
            yield _sse("DONE")

    return StreamingResponse(generate(), media_type="text/event-stream")


@router.post("/{model_id}", response_model=ChatResponse)
async def chat(model_id: int, payload: ChatRequest, db: Session = Depends(get_db)):
    return await _respond(model_id, payload, db, rag=False)


@router.post("/{model_id}/stream")
async def chat_stream(model_id: int, payload: ChatRequest, db: Session = Depends(get_db)):
    return _stream_response(model_id, payload, db, rag=False)


@router.post("/{model_id}/rag", response_model=RAGChatResponse)
async def chat_rag(model_id: int, payload: RAGChatRequest, db: Session = Depends(get_db)):
    return await _respond(model_id, payload, db, rag=True)


@router.post("/{model_id}/rag/stream")
async def chat_rag_stream(model_id: int, payload: RAGChatRequest, db: Session = Depends(get_db)):
    return _stream_response(model_id, payload, db, rag=True)
