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

def _get_chat_history_turns(db) -> int:
    """Return chat_history_turns: how many recent user/assistant turn-pairs to keep (0 = all)."""
    row = db.get(Setting, "chat_history_turns")
    try:
        return int(row.value) if row and row.value else 5
    except (ValueError, TypeError):
        return 5


def _get_max_tool_rounds(db) -> int:
    """Return chat_max_tool_rounds from settings (default 5)."""
    row = db.get(Setting, "chat_max_tool_rounds")
    try:
        return max(1, int(row.value)) if row and row.value else 5
    except (ValueError, TypeError):
        return 5


def _get_compress_model_id(db) -> int | None:
    """Return chat_compress_model_id from settings, or None if not configured."""
    row = db.get(Setting, "chat_compress_model_id")
    value = row.value if row else ""
    try:
        return int(value) if value else None
    except (ValueError, TypeError):
        return None


async def _compress_old_turns(
    messages: list[ChatMessage],
    compress_model_id: int,
    history_turns: int,
    db: Session,
    language: str = "zh",
) -> list[ChatMessage]:
    """Compress the oldest part of the conversation history into a single summary message.

    Only the user/assistant pairs older than the last *history_turns* rounds are
    compressed. The compressed content is inserted as a single system message
    at position 1 (after the first system message, if any).

    Returns the modified message list.
    """
    compress_model = load_chat_model(compress_model_id, db)
    if not compress_model:
        return messages

    user_indices = [i for i, m in enumerate(messages) if m.role == "user"]
    if len(user_indices) <= history_turns:
        return messages  # nothing to compress

    split_idx = user_indices[-history_turns]

    old_msgs = messages[:split_idx]
    recent_msgs = messages[split_idx:]

    dialogue_to_compress = [m for m in old_msgs if m.role in ("user", "assistant")]
    if not dialogue_to_compress:
        return messages

    dialogue_text = "\n".join(
        f"{'User' if m.role == 'user' else 'AI'}: {m.content[:600]}"
        for m in dialogue_to_compress
    )
    if language == "zh":
        compress_prompt = (
            "\u8bf7\u5c06\u4ee5\u4e0b\u5bf9\u8bdd\u5386\u53f2\u538b\u7f29\u4e3a\u4e00\u6bb5\u7b80\u6d01\u7684\u6458\u8981\uff08\u4e0d\u8d85\u8fc7500\u5b57\uff09\uff0c"
            "\u4fdd\u7559\u6240\u6709\u91cd\u8981\u7ed3\u8bba\u548c\u5173\u952e\u4fe1\u606f\uff0c\u53bb\u6389\u91cd\u590d\u6216\u5197\u4f59\u5185\u5bb9\uff1a\n\n" + dialogue_text
        )
    else:
        compress_prompt = (
            "Please compress the following conversation history into a concise summary "
            "(<=500 words), retaining all important conclusions and key information:\n\n" + dialogue_text
        )

    try:
        compress_llm = _build_llm_base(compress_model)
        response = await asyncio.wait_for(
            compress_llm.ainvoke([HumanMessage(content=compress_prompt)]),
            timeout=60,
        )
        summary_text = _content_to_text(response.content).strip()
    except Exception:
        logger.exception("_compress_old_turns: compression failed, keeping original history")
        return messages

    if not summary_text:
        return messages

    system_msgs = [m for m in old_msgs if m.role == "system"]
    summary_prefix = "[History Summary]" if language != "zh" else "[\u5386\u53f2\u5bf9\u8bdd\u6458\u8981]"
    summary_msg = ChatMessage(role="system", content=f"{summary_prefix}\n{summary_text}")

    result = system_msgs + [summary_msg] + recent_msgs
    logger.info(
        "_compress_old_turns: compressed %d old messages into summary (%d chars)",
        len(dialogue_to_compress), len(summary_text),
    )
    return result


def _save_turn(
    db: Session,
    conversation_id: int,
    user_messages: list[ChatMessage],
    assistant_content: str,
    summary: str | None = None,
    references: list | None = None,
    model_id: int | None = None,
) -> None:
    """Append the last user message(s) + assistant reply to *conversation_id*.

    Also writes *summary* to the conversation record when provided.
    Silently skips if the conversation is not found.
    """
    conv = db.get(Conversation, conversation_id)
    if not conv:
        logger.warning("_save_turn: conversation %d not found 鈥?skipping", conversation_id)
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
        model_id=model_id,
        position=next_pos,
    ))

    if summary:
        conv.summary = summary

    db.commit()


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


# ---------------------------------------------------------------------------
# 璺敱
# ---------------------------------------------------------------------------

@router.post("/{model_id}", response_model=ChatResponse)
async def chat(
    model_id: int,
    payload: ChatRequest,
    db: Session = Depends(get_db),
):
    """Non-streaming RAG chat with a specific model."""
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
        _save_turn(db, payload.conversation_id, payload.messages, final_content, summary, model_id=model_id)

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
    """Streaming chat via Server-Sent Events."""
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

    async def _bg_summarize_plain(full_response: str):
        """Run summarization in background and update the conversation summary field."""
        if not summary_model or not payload.conversation_id:
            return
        try:
            conv_text = _fmt_conversation(payload.messages, full_response)
            summary = await asummarize(conv_text, summary_model, language=_get_language(db))
            if summary:
                _update_conv_summary(db, payload.conversation_id, summary)
        except Exception as exc:
            logger.warning("chat_stream: background summarization failed: %s", exc)

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

        # Save user+assistant to DB NOW before [DONE] so the frontend reload
        # always finds the messages in DB (avoids user message disappearing).
        if payload.conversation_id:
            try:
                _save_turn(db, payload.conversation_id, payload.messages, full_response, model_id=model_id)
            except Exception as exc:
                logger.warning("chat_stream: failed to save turn: %s", exc)

        yield "data: [DONE]\n\n"

        # Background: only summarization (DB write already done above)
        asyncio.ensure_future(_bg_summarize_plain(full_response))

    return StreamingResponse(token_generator(), media_type="text/event-stream")


# ---------------------------------------------------------------------------
# RAG helpers
# ---------------------------------------------------------------------------

_RAG_SYSTEM_PREFIX = (
    "You have access to a knowledge base search tool. "
    "Call the search_knowledge_base tool ONCE to retrieve relevant information, "
    "then synthesize a complete answer based on what you find. "
    "Do NOT call the search tool multiple times in a single turn — "
    "one well-chosen query is sufficient. "
    "When you cite information from the search results, place the citation marker "
    "(e.g. [CITE-1], [CITE-2]) immediately after the relevant statement. "
    "Even if the retrieved content does not perfectly match the question, "
    "use the relevant parts to construct a helpful answer.\n\n"
)


import re

def _to_rag_messages(messages: list[ChatMessage], history_turns: int = 0):
    """Prepend RAG instructions to the system message (or insert one).

    Also strips leftover citation markers ([1], [2] 鈥? from assistant history
    and injects a tool-call reminder before the final user message so that
    every turn triggers a fresh search.
    """
    # Apply turn-window: keep only the last `history_turns` user/assistant pairs
    # (plus all system messages which are always preserved).
    if history_turns > 0:
        user_indices = [i for i, m in enumerate(messages) if m.role == "user"]
        if len(user_indices) > history_turns:
            split_idx = user_indices[-history_turns]
            system_prefix = [m for m in messages[:split_idx] if m.role == "system"]
            messages = system_prefix + messages[split_idx:]

    lc_msgs: list = []
    prefix_added = False
    for msg in messages:
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

    return lc_msgs


def _build_synthesis_context(original_messages: list, retrieved_chunks) -> list:
    """Build a clean synthesis context from the original messages + retrieved chunks.

    Replaces the tool-call exchange (AIMessage with tool_calls + ToolMessages)
    with a direct context injection.  This avoids the ``reasoning_content``
    round-trip requirement of thinking models (DeepSeek-R1, QwQ, etc.) that
    fails when LangChain serialises tool-call history back to the API.
    """
    _MAX_CHUNK_CHARS = 1200
    parts: list[str] = []
    for chunk in retrieved_chunks:
        display = chunk.content[:_MAX_CHUNK_CHARS]
        if len(chunk.content) > _MAX_CHUNK_CHARS:
            display += "…[truncated]"
        parts.append(
            f"{chunk.cite_label} "
            f"(file: {chunk.original_filename}, paragraph {chunk.chunk_index + 1})\n"
            f"{display}"
        )
    results_text = "\n\n---\n\n".join(parts)
    synthesis_msg = SystemMessage(
        content=(
            "The following information has been retrieved from the knowledge base:\n\n"
            f"{results_text}\n\n"
            "Now write a complete answer based on these results. "
            "Include [CITE-N] markers (e.g. [CITE-1]) immediately after statements "
            "that use information from the corresponding chunk. "
            "Do NOT call any tools."
        )
    )
    msgs = list(original_messages)
    # Insert the context block before the last message (the user’s question)
    msgs.insert(-1, synthesis_msg)
    return msgs



@router.post("/{model_id}/rag", response_model=RAGChatResponse)
async def chat_rag(
    model_id: int,
    payload: RAGChatRequest,
    db: Session = Depends(get_db),
):
    """RAG chat 鈥?the LLM automatically calls the knowledge-base search tool,
    then returns a response with inline [n] citations and a reference list.
    """
    ai_model = _get_chat_model(model_id, db)
    _check_rate_limit(model_id, ai_model.qps)

    llm = _build_llm(ai_model)

    search_tool, retrieved = make_search_tool(payload.kb_ids, db)
    llm_with_tools = llm.bind_tools([search_tool])

    history_turns = _get_chat_history_turns(db)
    max_tool_rounds = _get_max_tool_rounds(db)

    working = _to_rag_messages(payload.messages, history_turns=history_turns)
    _check_context_length(working, ai_model)
    final_content = ""
    initial_working = list(working)  # snapshot before any tool-call mutations

    # Agentic tool-calling loop
    for _round in range(max_tool_rounds):
        # After retrieving chunks, switch to plain llm (no tools bound) so we
        # never replay the AIMessage-with-tool_calls back to the API — this
        # avoids the reasoning_content round-trip error from thinking models
        # (DeepSeek-R1, QwQ, etc.).
        current_llm = llm if retrieved else llm_with_tools
        try:
            response: AIMessage = await current_llm.ainvoke(working)
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"Model call failed: {exc}") from exc

        tool_calls = getattr(response, "tool_calls", None) or []
        if not tool_calls:
            final_content = _content_to_text(response.content)
            break

        # Execute tool calls (populates retrieved); do NOT replay via LangChain
        # tool-message protocol to avoid reasoning_content serialisation issues.
        for tc in tool_calls:
            try:
                await asyncio.to_thread(search_tool.invoke, tc["args"])
            except Exception as exc:
                logger.warning("RAG tool call failed: %s", exc)

        if retrieved:
            # Rebuild working as a clean synthesis context derived from the
            # original messages + retrieved chunks.  Sidesteps the
            # reasoning_content requirement that breaks DeepSeek-R1 etc.
            working = _build_synthesis_context(initial_working, retrieved)
        else:
            # No chunks retrieved — fall back to LangChain tool-message protocol
            working.append(response)
            for tc in tool_calls:
                working.append(ToolMessage(
                    content="No relevant information found in the knowledge base.",
                    tool_call_id=tc["id"],
                ))
            working.append(SystemMessage(
                content="Please answer the user's question based on your general knowledge."
            ))
    else:
        # Max rounds reached 鈥?force a plain answer with no tools
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
            summary, references, model_id=model_id,
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
    - ``data: {token}``           鈥?incremental text token from the final answer
    - ``data: [TOOL_CALL] {...}`` 鈥?JSON object with ``name`` and ``args`` of each tool invocation
    - ``data: [CITATIONS] {...}`` 鈥?JSON with ``references`` list and ``cite_map`` substitution table
    - ``data: [DONE]``            鈥?stream end marker
    - ``data: [ERROR] {msg}``     鈥?error description
    """
    ai_model = _get_chat_model(model_id, db)
    _check_rate_limit(model_id, ai_model.qps)

    llm = _build_llm(ai_model)

    search_tool, retrieved = make_search_tool(payload.kb_ids, db)
    llm_with_tools = llm.bind_tools([search_tool])

    history_turns = _get_chat_history_turns(db)
    max_tool_rounds = _get_max_tool_rounds(db)

    working = _to_rag_messages(payload.messages, history_turns=history_turns)
    _check_context_length(working, ai_model)
    initial_working = list(working)  # snapshot before any tool-call mutations

    # Determine whether to summarize after streaming completes
    summary_model_id = _get_summary_model_id(db)
    summary_model = None
    if summary_model_id:
        summary_model = load_chat_model(summary_model_id, db)

    async def _background_summarize(annotated: str, payload_messages: list[ChatMessage], conversation_id: int | None, language: str):
        """Run summarization in background and update the conversation summary field."""
        if not summary_model or not conversation_id:
            return
        try:
            conv_text = _fmt_conversation(payload_messages, annotated)
            summary = await asummarize(conv_text, summary_model, language=language)
            if summary:
                _update_conv_summary(db, conversation_id, summary)
        except Exception as exc:
            logger.warning("chat_rag_stream: background summarization failed: %s", exc)

    _STREAM_TOKEN_TIMEOUT = 120  # seconds to wait for the next streamed token

    async def token_generator():
        for _round in range(max_tool_rounds):
            ai_chunk: AIMessageChunk | None = None
            text_tokens: list[str] = []

            try:
                # After retrieving chunks, switch to plain llm (no tools bound)
                # to avoid reasoning_content round-trip issues (DeepSeek-R1 etc.)
                current_llm = llm if retrieved else llm_with_tools
                gen = current_llm.astream(working)
                while True:
                    try:
                        chunk = await asyncio.wait_for(gen.__anext__(), timeout=_STREAM_TOKEN_TIMEOUT)
                    except StopAsyncIteration:
                        break
                    except asyncio.TimeoutError:
                        raise asyncio.TimeoutError(
                            f"No response from model within {_STREAM_TOKEN_TIMEOUT}s (provider may be overloaded)"
                        )
                    ai_chunk = chunk if ai_chunk is None else ai_chunk + chunk
                    token = _content_to_text(chunk.content)
                    if token:
                        text_tokens.append(token)
                        yield f"data: {token}\n\n"
            except Exception as exc:
                # If search already ran and we have retrieved chunks, fall back to
                # showing citations instead of failing silently with 0 output.
                if retrieved and _round > 0:
                    logger.warning("RAG final LLM call failed after search (round %d): %s", _round, exc)
                    language = _get_language(db)
                    fallback_text = (
                        "（模型生成回答失败，以下为知识库检索到的相关内容）"
                        if language == "zh"
                        else "(Model failed to generate a response — showing retrieved sources below)"
                    )
                    annotated, references, cite_map = build_rag_response(
                        fallback_text, retrieved, db, payload.citation_style,
                        existing_references=payload.existing_references,
                    )
                    if references:
                        payload_json = _json.dumps(
                            {"references": references, "cite_map": cite_map},
                            ensure_ascii=False,
                        )
                        yield f"data: [CITATIONS] {payload_json}\n\n"
                    yield f"data: [REPLACE] {_json.dumps(annotated, ensure_ascii=False)}\n\n"
                    # Save to DB before [DONE] so the frontend reload finds the messages
                    language = _get_language(db)
                    if payload.conversation_id:
                        try:
                            _save_turn(db, payload.conversation_id, payload.messages, annotated, None, references, model_id=model_id)
                        except Exception as save_exc:
                            logger.warning("RAG stream fallback: failed to save turn: %s", save_exc)
                    yield "data: [DONE]\n\n"
                    asyncio.ensure_future(_background_summarize(
                        annotated, payload.messages, payload.conversation_id, language,
                    ))
                else:
                    yield f"data: [ERROR] {exc}\n\n"
                    yield "data: [DONE]\n\n"
                return

            if ai_chunk is None:
                break

            tool_calls = getattr(ai_chunk, "tool_calls", None) or []
            if not tool_calls:
                # Final answer round 鈥?tokens already streamed in real-time.
                final_text = "".join(text_tokens)

                # Fallback: some models aggregate content in the final chunk
                # without emitting per-chunk content events.
                if not final_text:
                    final_text = _content_to_text(ai_chunk.content)

                # Last-resort fallback for providers that return empty streamed
                # content in the final round.
                if not final_text.strip():
                    try:
                        forced_final: AIMessage = await llm.ainvoke(working)
                        final_text = _content_to_text(forced_final.content)
                    except Exception as exc:
                        logger.warning("RAG stream final fallback failed: %s", exc)
                
                # 濡傛灉鎵€鏈?fallback 鍚庝粛鐒朵负绌猴紝寮哄埗璁剧疆鍐呭閬垮厤绌虹櫧姘旀场
                if not final_text.strip():
                    final_text = "No text response generated from knowledge base."

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

                # Save user+assistant to DB BEFORE [DONE] so the frontend reload
                # always finds the messages in DB (avoids user message disappearing).
                language = _get_language(db)
                if payload.conversation_id:
                    try:
                        _save_turn(db, payload.conversation_id, payload.messages, annotated, None, references, model_id=model_id)
                    except Exception as save_exc:
                        logger.warning("chat_rag_stream: failed to save turn: %s", save_exc)

                yield "data: [DONE]\n\n"

                # Background: only summarization (DB write already done above)
                asyncio.ensure_future(_background_summarize(
                    annotated, payload.messages, payload.conversation_id, language,
                ))
                return

            # Tool call round — tell frontend to clear any intermediate text,
            # then execute the tools.
            yield "data: [CLEAR]\n\n"
            for tc in tool_calls:
                tc_event = _json.dumps({"name": tc["name"], "args": tc["args"]}, ensure_ascii=False)
                yield f"data: [TOOL_CALL] {tc_event}\n\n"
                searching_event = _json.dumps({"query": tc["args"].get("query", "")}, ensure_ascii=False)
                yield f"data: [SEARCHING] {searching_event}\n\n"
                try:
                    await asyncio.to_thread(search_tool.invoke, tc["args"])
                except Exception as exc:
                    logger.warning("RAG stream tool call failed: %s", exc)

            if retrieved:
                # Rebuild working as a clean synthesis context to avoid
                # reasoning_content round-trip issues (DeepSeek-R1, QwQ, etc.)
                new_working = _build_synthesis_context(initial_working, retrieved)
                working.clear()
                working.extend(new_working)
            else:
                # No chunks — fall back to LangChain tool-message protocol
                working.append(ai_chunk)
                for tc in tool_calls:
                    working.append(ToolMessage(
                        content="No relevant information found in the knowledge base.",
                        tool_call_id=tc["id"],
                    ))
                working.append(SystemMessage(
                    content="Please answer the user's question based on your general knowledge."
                ))

        else:
            # Max rounds exceeded 鈥?one non-streaming call to get the final answer
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

                # Save to DB before [DONE]
                language = _get_language(db)
                if payload.conversation_id:
                    try:
                        _save_turn(db, payload.conversation_id, payload.messages, final_text, None, references, model_id=model_id)
                    except Exception as save_exc:
                        logger.warning("chat_rag_stream max-rounds: failed to save turn: %s", save_exc)

                yield "data: [DONE]\n\n"

                asyncio.ensure_future(_background_summarize(
                    annotated, payload.messages, payload.conversation_id, language,
                ))
            except Exception as exc:
                yield f"data: [ERROR] {exc}\n\n"
                yield "data: [DONE]\n\n"

    return StreamingResponse(token_generator(), media_type="text/event-stream")
