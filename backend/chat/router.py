"""API routes for chat (non-streaming and streaming)."""

import asyncio
import json as _json
import logging
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage, SystemMessage, ToolMessage
from pydantic import BaseModel, Field
from sqlalchemy import func as sa_func
from sqlalchemy.orm import Session, joinedload

from auxmodels.rate_limiter import try_acquire as _try_acquire
from auxmodels.summarizer import asummarize
from chat.citations import build_rag_response
from chat.tools import make_search_tool
from conversations.models import Conversation, Message
from database import get_db
from providers.chat import build_llm as _build_llm_base, load_chat_model
from providers.models import AIModel
from settings.models import Setting

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/chat", tags=["chat"])


def _content_to_text(content) -> str:
    """Normalize provider-specific content payloads into plain text."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for part in content:
            if isinstance(part, str):
                parts.append(part)
            elif isinstance(part, dict):
                text = part.get("text")
                if isinstance(text, str):
                    parts.append(text)
                else:
                    for key in ("content", "value"):
                        v = part.get(key)
                        if isinstance(v, str):
                            parts.append(v)
                            break
            elif part is not None:
                parts.append(str(part))
        return "".join(parts)
    if content is None:
        return ""
    return str(content)


# ---------------------------------------------------------------------------
# Request / Response Schemas
# ---------------------------------------------------------------------------

class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"] = Field(..., examples=["user"])
    content: str = Field(..., min_length=1, examples=["你好！"])


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
    max_tool_rounds: int = Field(
        default=5,
        ge=1,
        le=10,
        description="Max tool-calling rounds before forcing a final answer",
    )
    existing_references: list[dict] = Field(
        default_factory=list,
        description="References from previous turns, each with ref_num, document_file_id, original_filename, formatted_citation",
    )


class CitationRef(BaseModel):
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
    summary: str | None = None


# ---------------------------------------------------------------------------
# LangChain helpers
# ---------------------------------------------------------------------------


def _to_lc_messages(messages: list[ChatMessage]):
    mapping = {"system": SystemMessage, "user": HumanMessage, "assistant": AIMessage}
    return [mapping[m.role](content=m.content) for m in messages]


def _build_llm(ai_model: AIModel):
    """Wrap providers.chat.build_llm, converting any init error to HTTPException."""
    try:
        return _build_llm_base(ai_model)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _check_rate_limit(model_id: int, qps: int) -> None:
    """Raise 429 if the model's QPS budget is exhausted (non-blocking)."""
    if qps and not _try_acquire(model_id, qps):
        raise HTTPException(status_code=429, detail="Request exceeds model QPS limit, please retry later")


def _estimate_tokens(messages) -> int:
    """Rough token count estimate (~2 chars per token for mixed zh/en)."""
    total = 0
    for m in messages:
        content = m.content if hasattr(m, "content") else ""
        total += len(content) if isinstance(content, str) else 0
    return total // 2


def _check_context_length(messages, ai_model: AIModel) -> None:
    """Raise 400 if estimated tokens exceed 90% of the model's context window."""
    if not ai_model.context_length:
        return
    max_tokens = ai_model.context_length * 1000  # context_length is in k
    estimated = _estimate_tokens(messages)
    if estimated > int(max_tokens * 0.9):
        raise HTTPException(
            status_code=400,
            detail=(
                f"Estimated token count ({estimated}) approaches or exceeds "
                f"model context length ({max_tokens}). "
                "Please shorten the conversation history or use a model with a larger context window."
            ),
        )


def _get_summary_model_id(db) -> int | None:
    """Return chat_summary_model_id from settings, or None if not configured."""
    row = db.get(Setting, "chat_summary_model_id")
    value = row.value if row else ""
    try:
        return int(value) if value else None
    except (ValueError, TypeError):
        return None


def _get_language(db) -> str:
    """Return the UI language setting ('zh' or 'en'), defaulting to 'zh'."""
    row = db.get(Setting, "language")
    return (row.value or "zh") if row else "zh"


def _save_turn(
    db: Session,
    conversation_id: int,
    user_messages: list[ChatMessage],
    assistant_content: str,
    summary: str | None = None,
    references: list | None = None,
) -> None:
    """Append the last user message(s) + assistant reply to *conversation_id*.

    Also writes *summary* to the conversation record when provided.
    Silently skips if the conversation is not found.
    """
    conv = db.get(Conversation, conversation_id)
    if not conv:
        logger.warning("_save_turn: conversation %d not found — skipping", conversation_id)
        return

    max_pos = (
        db.query(sa_func.max(Message.position))
        .filter(Message.conversation_id == conversation_id)
        .scalar()
    )
    next_pos = (max_pos + 1) if max_pos is not None else 0

    # Append only the LAST user message to avoid duplicating history
    last_user = next((m for m in reversed(user_messages) if m.role == "user"), None)
    if last_user:
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
        position=next_pos,
    ))

    if summary:
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


# ---------------------------------------------------------------------------
# 路由
# ---------------------------------------------------------------------------

@router.post("/{model_id}", response_model=ChatResponse)
async def chat(
    model_id: int,
    payload: ChatRequest,
    db: Session = Depends(get_db),
):
    """Non-streaming chat with a specific model / 使用指定模型进行一次对话，返回完整回复。"""
    ai_model = _get_chat_model(model_id, db)
    _check_rate_limit(model_id, ai_model.qps)
    llm = _build_llm(ai_model)
    lc_messages = _to_lc_messages(payload.messages)
    _check_context_length(lc_messages, ai_model)

    try:
        response: AIMessage = await llm.ainvoke(lc_messages)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Model call failed: {exc}") from exc

    final_content = _content_to_text(response.content)

    # Optional: summarize conversation turn
    summary: str | None = None
    summary_model_id = _get_summary_model_id(db)
    if summary_model_id:
        summary_model = load_chat_model(summary_model_id, db)
        if summary_model:
            conv_text = _fmt_conversation(payload.messages, final_content)
            summary = await asummarize(conv_text, summary_model, language=_get_language(db)) or None

    if payload.conversation_id:
        _save_turn(db, payload.conversation_id, payload.messages, final_content, summary)

    return ChatResponse(
        content=final_content,
        model=ai_model.display_name,
        provider=ai_model.provider.name,
        summary=summary,
    )


@router.post("/{model_id}/stream")
async def chat_stream(
    model_id: int,
    payload: ChatRequest,
    db: Session = Depends(get_db),
):
    """Streaming chat via Server-Sent Events / 使用指定模型进行流式对话（Server-Sent Events）。"""
    ai_model = _get_chat_model(model_id, db)
    _check_rate_limit(model_id, ai_model.qps)
    llm = _build_llm(ai_model)
    lc_messages = _to_lc_messages(payload.messages)
    _check_context_length(lc_messages, ai_model)

    # Determine whether to summarize after streaming completes
    summary_model_id = _get_summary_model_id(db)
    summary_model = None
    if summary_model_id:
        summary_model = load_chat_model(summary_model_id, db)

    async def _bg_save_plain(full_response: str):
        """Summarize and save in background for non-RAG streaming."""
        summary: str | None = None
        if summary_model:
            conv_text = _fmt_conversation(payload.messages, full_response)
            summary = await asummarize(conv_text, summary_model, language=_get_language(db))
        if payload.conversation_id:
            _save_turn(db, payload.conversation_id, payload.messages, full_response, summary)

    async def token_generator():
        accumulated: list[str] = []
        try:
            async for chunk in llm.astream(lc_messages):
                token = _content_to_text(chunk.content)
                if token:
                    accumulated.append(token)
                    yield f"data: {token}\n\n"
        except Exception as exc:
            yield f"data: [ERROR] {exc}\n\n"
            yield "data: [DONE]\n\n"
            return

        full_response = "".join(accumulated)

        # End stream immediately — summarization and DB save happen in background
        yield "data: [DONE]\n\n"

        asyncio.ensure_future(_bg_save_plain(full_response))

    return StreamingResponse(token_generator(), media_type="text/event-stream")


# ---------------------------------------------------------------------------
# RAG helpers
# ---------------------------------------------------------------------------

_RAG_SYSTEM_PREFIX = (
    "You have access to a knowledge base search tool. "
    "For EVERY user question, you MUST call the search_knowledge_base tool "
    "to retrieve relevant information before answering — even if you think you "
    "already know the answer from previous conversation turns. "
    "When you cite information from the search results, place the citation marker "
    "(e.g. [CITE-1], [CITE-2]) immediately after the relevant statement. "
    "You MUST synthesize and answer based on the retrieved content. "
    "Even if the retrieved content does not perfectly match the question, "
    "use the relevant parts to construct a helpful answer.\n\n"
)


import re

def _to_rag_messages(messages: list[ChatMessage]):
    """Prepend RAG instructions to the system message (or insert one).

    Also strips leftover citation markers ([1], [2] …) from assistant history
    and injects a tool-call reminder before the final user message so that
    every turn triggers a fresh search.
    """
    lc_msgs: list = []
    prefix_added = False
    for msg in messages:
        # 移除历史对话中的已有角标（如 [1], [2]），避免大模型在后续 RAG 轮次中造成格式截断或拒答
        clean_content = msg.content
        if msg.role == "assistant":
            clean_content = re.sub(r"\[\d+\]", "", clean_content)

        if msg.role == "system" and not prefix_added:
            lc_msgs.append(SystemMessage(content=_RAG_SYSTEM_PREFIX + clean_content))
            prefix_added = True
        else:
            mapping = {"system": SystemMessage, "user": HumanMessage, "assistant": AIMessage}
            lc_msgs.append(mapping[msg.role](content=clean_content))
    if not prefix_added:
        lc_msgs.insert(0, SystemMessage(content=_RAG_SYSTEM_PREFIX.strip()))

    # 如果存在多轮对话历史（即有 assistant 消息），在最后一条 user 消息前
    # 插入系统提醒，强制模型为新问题调用搜索工具
    has_history = any(isinstance(m, AIMessage) for m in lc_msgs)
    if has_history and len(lc_msgs) >= 2:
        reminder = SystemMessage(
            content=(
                "The user is asking a NEW question. You MUST call the "
                "search_knowledge_base tool again to retrieve fresh information "
                "for this question. Do NOT reuse previous search results."
            )
        )
        # Insert just before the last message (the new user question)
        lc_msgs.insert(-1, reminder)

    return lc_msgs


# ---------------------------------------------------------------------------
# RAG routes
# ---------------------------------------------------------------------------

@router.post("/{model_id}/rag", response_model=RAGChatResponse)
async def chat_rag(
    model_id: int,
    payload: RAGChatRequest,
    db: Session = Depends(get_db),
):
    """RAG chat — the LLM automatically calls the knowledge-base search tool,
    then returns a response with inline [n] citations and a reference list.
    """
    ai_model = _get_chat_model(model_id, db)
    _check_rate_limit(model_id, ai_model.qps)

    llm = _build_llm(ai_model)

    search_tool, retrieved = make_search_tool(payload.kb_ids, db)
    llm_with_tools = llm.bind_tools([search_tool])

    working = _to_rag_messages(payload.messages)
    _check_context_length(working, ai_model)
    final_content = ""

    # Agentic tool-calling loop
    for _round in range(payload.max_tool_rounds):
        try:
            response: AIMessage = await llm_with_tools.ainvoke(working)
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"Model call failed: {exc}") from exc

        tool_calls = getattr(response, "tool_calls", None) or []
        if not tool_calls:
            final_content = _content_to_text(response.content)
            break

        working.append(response)
        for tc in tool_calls:
            try:
                result = await asyncio.to_thread(search_tool.invoke, tc["args"])
            except Exception as exc:
                result = f"Search error: {exc}"
            working.append(ToolMessage(content=str(result), tool_call_id=tc["id"]))
    else:
        # Max rounds reached — force a plain answer with no tools
        try:
            forced: AIMessage = await llm.ainvoke(working)
            final_content = _content_to_text(forced.content)
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"Model call failed: {exc}") from exc

    annotated, references, _ = build_rag_response(
        final_content, retrieved, db, payload.citation_style,
        existing_references=payload.existing_references,
    )

    # Optional summarization
    summary: str | None = None
    summary_model_id = _get_summary_model_id(db)
    if summary_model_id:
        summary_model = load_chat_model(summary_model_id, db)
        if summary_model:
            conv_text = _fmt_conversation(payload.messages, annotated)
            summary = await asummarize(conv_text, summary_model, language=_get_language(db)) or None

    if payload.conversation_id:
        _save_turn(
            db, payload.conversation_id, payload.messages, annotated,
            summary, references,
        )

    return RAGChatResponse(
        content=annotated,
        references=[CitationRef(**r) for r in references],
        model=ai_model.display_name,
        provider=ai_model.provider.name,
        summary=summary,
    )


@router.post("/{model_id}/rag/stream")
async def chat_rag_stream(
    model_id: int,
    payload: RAGChatRequest,
    db: Session = Depends(get_db),
):
    """Streaming RAG chat via Server-Sent Events.

    Event types emitted:
    - ``data: {token}``           — incremental text token from the final answer
    - ``data: [TOOL_CALL] {...}`` — JSON object with ``name`` and ``args`` of each tool invocation
    - ``data: [CITATIONS] {...}`` — JSON with ``references`` list and ``cite_map`` substitution table
    - ``data: [DONE]``            — stream end marker
    - ``data: [ERROR] {msg}``     — error description
    """
    ai_model = _get_chat_model(model_id, db)
    _check_rate_limit(model_id, ai_model.qps)

    llm = _build_llm(ai_model)

    search_tool, retrieved = make_search_tool(payload.kb_ids, db)
    llm_with_tools = llm.bind_tools([search_tool])

    working = _to_rag_messages(payload.messages)
    _check_context_length(working, ai_model)

    # Determine whether to summarize after streaming completes
    summary_model_id = _get_summary_model_id(db)
    summary_model = None
    if summary_model_id:
        summary_model = load_chat_model(summary_model_id, db)

    async def _background_save(annotated: str, references: list, summary_model_inst, payload_messages: list[ChatMessage], conversation_id: int | None, language: str):
        """Run summarization and save in background so the stream ends faster."""
        summary: str | None = None
        if summary_model_inst:
            conv_text = _fmt_conversation(payload_messages, annotated)
            summary = await asummarize(conv_text, summary_model_inst, language=language)
        if conversation_id:
            _save_turn(db, conversation_id, payload_messages, annotated, summary, references)

    async def token_generator():
        for _round in range(payload.max_tool_rounds):
            ai_chunk: AIMessageChunk | None = None
            text_tokens: list[str] = []

            try:
                async for chunk in llm_with_tools.astream(working):
                    ai_chunk = chunk if ai_chunk is None else ai_chunk + chunk
                    token = _content_to_text(chunk.content)
                    if token:
                        text_tokens.append(token)
                        yield f"data: {token}\n\n"
            except Exception as exc:
                yield f"data: [ERROR] {exc}\n\n"
                yield "data: [DONE]\n\n"
                return

            if ai_chunk is None:
                break

            tool_calls = getattr(ai_chunk, "tool_calls", None) or []
            if not tool_calls:
                # Final answer round — tokens already streamed in real-time.
                final_text = "".join(text_tokens)

                # Fallback: some models aggregate content in the final chunk
                # without emitting per-chunk content events.
                if not final_text:
                    final_text = _content_to_text(ai_chunk.content)

                # Last-resort fallback for providers that return empty streamed
                # content in the final round.
                if not final_text.strip():
                    try:
                        # Keep tool binding so providers that enforce tool-message
                        # role constraints can still return a valid final answer.
                        forced_final: AIMessage = await llm_with_tools.ainvoke(working)
                        final_text = _content_to_text(forced_final.content)
                    except Exception as exc:
                        logger.warning("RAG stream final fallback failed: %s", exc)
                
                # 如果所有 fallback 后仍然为空，强制设置内容避免空白气泡
                if not final_text.strip():
                    final_text = "从知识库中检索了信息，但模型没有生成文本回答。"

                # Post-process citations
                annotated, references, cite_map = build_rag_response(
                    final_text, retrieved, db, payload.citation_style,
                    existing_references=payload.existing_references,
                )
                if references:
                    payload_json = _json.dumps(
                        {"references": references, "cite_map": cite_map},
                        ensure_ascii=False,
                    )
                    yield f"data: [CITATIONS] {payload_json}\n\n"

                # Send the final annotated text so the frontend can fix any
                # newlines lost in SSE framing and apply citation markers.
                yield f"data: [REPLACE] {_json.dumps(annotated, ensure_ascii=False)}\n\n"

                # End stream immediately — summarization and DB save happen in background
                yield "data: [DONE]\n\n"

                language = _get_language(db)
                asyncio.ensure_future(_background_save(
                    annotated, references, summary_model,
                    payload.messages, payload.conversation_id, language,
                ))
                return

            # Tool call round — tell frontend to clear any displayed intermediate text,
            # then execute the tools and continue the loop.
            yield "data: [CLEAR]\n\n"
            working.append(ai_chunk)
            for tc in tool_calls:
                tc_event = _json.dumps({"name": tc["name"], "args": tc["args"]}, ensure_ascii=False)
                yield f"data: [TOOL_CALL] {tc_event}\n\n"
                searching_event = _json.dumps({"query": tc["args"].get("query", "")}, ensure_ascii=False)
                yield f"data: [SEARCHING] {searching_event}\n\n"
                try:
                    result = await asyncio.to_thread(search_tool.invoke, tc["args"])
                except Exception as exc:
                    result = f"Search error: {exc}"
                working.append(ToolMessage(content=str(result), tool_call_id=tc["id"]))

        else:
            # Max rounds exceeded — one non-streaming call to get the final answer
            try:
                forced: AIMessage = await llm.ainvoke(working)
                final_text = _content_to_text(forced.content)
                annotated, references, cite_map = build_rag_response(
                    final_text, retrieved, db, payload.citation_style,
                    existing_references=payload.existing_references,
                )
                yield f"data: [REPLACE] {_json.dumps(annotated, ensure_ascii=False)}\n\n"
                if references:
                    payload_json = _json.dumps(
                        {"references": references, "cite_map": cite_map},
                        ensure_ascii=False,
                    )
                    yield f"data: [CITATIONS] {payload_json}\n\n"

                yield "data: [DONE]\n\n"

                language = _get_language(db)
                asyncio.ensure_future(_background_save(
                    annotated, references, summary_model,
                    payload.messages, payload.conversation_id, language,
                ))
            except Exception as exc:
                yield f"data: [ERROR] {exc}\n\n"
                yield "data: [DONE]\n\n"

    return StreamingResponse(token_generator(), media_type="text/event-stream")
