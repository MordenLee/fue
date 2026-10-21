"""Explicit tool bindings; tools cannot obtain database sessions from a request."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Awaitable, Callable, Literal

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, ConfigDict, Field, field_validator


TOOL_IDS = {"knowledge.search", "memory.search", "sources.read"}


class SearchArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str = Field(min_length=1, max_length=4000)
    mode: Literal["vector", "keyword", "hybrid"] = "vector"
    top_n: int = Field(default=0, ge=0, le=50)
    kb_ids: list[int] | None = Field(default=None, max_length=20)

    @field_validator("query")
    @classmethod
    def nonempty_query(cls, value):
        if not value.strip():
            raise ValueError("Search query cannot be blank")
        return value.strip()


@dataclass
class ToolBinding:
    id: str
    schema: StructuredTool
    execute: Callable[[dict], Awaitable[str | ToolOutput]]


@dataclass(frozen=True)
class ToolOutput:
    content: str
    status: Literal["ok", "empty"] = "ok"


def make_knowledge_binding(kb_ids: list[int], retrieved: list, session_factory, initial_cite_num=1):
    import asyncio
    import json

    from chat.tools import make_search_tool

    # The KB scope is bound by the server, not exposed as an LLM tool argument.
    scope = tuple(kb_ids)

    async def execute(args: dict) -> ToolOutput:
        validated = SearchArguments.model_validate(args).model_dump()
        selected = validated.pop("kb_ids") or list(scope)
        if not set(selected) <= set(scope):
            raise PermissionError("Knowledge base selection exceeds this run's scope")

        def search():
            # Return local results; timeout/cancellation must not mutate shared state.
            with session_factory() as db:
                from memory.service import setting
                keyword_only = setting(db, "knowledge_query_mode") == "keyword"
                if keyword_only:
                    validated["mode"] = "keyword"
                validated["top_n"] = min(validated["top_n"] or 5, 8)
                options = {"raise_on_error": True}
                if keyword_only:
                    options["allow_rerank"] = False
                tool, chunks = make_search_tool(
                    selected, db, initial_cite_num + len(retrieved), **options,
                )
                tool.invoke(validated)
                chunks = chunks[:validated["top_n"]]
                # Search returns a catalog of hits. Full/neighboring text is read separately.
                catalog = {"results": [{"source": c.cite_label, "document_id": c.document_file_id,
                                        "kb_id": c.knowledge_base_id, "chunk_index": c.chunk_index,
                                        "filename": c.original_filename, "preview": c.content[:500]}
                                       for c in chunks]}
                return json.dumps(catalog, ensure_ascii=False), chunks

        result, chunks = await asyncio.to_thread(search)
        retrieved.extend(chunks)
        return ToolOutput(result, "ok" if chunks else "empty")

    schema = StructuredTool.from_function(
        name="search_knowledge_base",
        description=f"Search allowed knowledge base IDs {list(scope)}. kb_ids selects a subset. Returns [CITE-N] sources.",
        args_schema=SearchArguments,
        coroutine=execute,
    )
    return ToolBinding("knowledge.search", schema, execute)


class HistoryArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str = Field(default="", max_length=2000)
    mode: Literal["keyword", "vector", "hybrid"] = "keyword"
    days: Literal[7, 30, 360] | None = None
    conversation_id: int | None = None
    top_n: int = Field(default=5, ge=1, le=10)
    offset: int = Field(default=0, ge=0, le=100000)
    start_time: int | None = None
    end_time: int | None = None


class ReadArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source: Literal["chat", "knowledge"]
    pair_id: str | None = None
    document_id: int | None = None
    chunk_index: int = Field(default=0, ge=0)
    before: int = Field(default=0, ge=0, le=3)
    after: int = Field(default=0, ge=0, le=3)
    offset: int = Field(default=0, ge=0, le=10000000)
    length: int = Field(default=2000, ge=100, le=4000)


def make_source_bindings(kb_ids, session_factory, retrieved=None):
    import asyncio
    import json
    from memory import service
    retrieved = retrieved if retrieved is not None else []

    async def history(args):
        values = HistoryArguments.model_validate(args).model_dump()
        def run():
            with session_factory() as db:
                return service.search(db, **values)
        result = await asyncio.to_thread(run)
        return ToolOutput(json.dumps(result, ensure_ascii=False), "ok" if result["results"] else "empty")

    async def read(args):
        values = ReadArguments.model_validate(args)
        def run():
            with session_factory() as db:
                if values.source == "chat":
                    return service.read_chat(db, values.pair_id, values.before, values.after, values.offset, values.length), []
                from knowledge.documents.models import DocumentFile
                from knowledge.models import KnowledgeBase
                from knowledge.chroma import get_chroma_client
                from chat.tools import RetrievedChunk
                doc = db.get(DocumentFile, values.document_id)
                if doc is None or doc.knowledge_base_id not in kb_ids:
                    raise PermissionError("Document is outside the allowed knowledge bases")
                kb = db.get(KnowledgeBase, doc.knowledge_base_id)
                raw = get_chroma_client().get_collection(kb.collection_name).get(
                    where={"$and": [{"document_file_id": doc.id},
                                     {"chunk_index": {"$gte": max(0, values.chunk_index - values.before)}},
                                     {"chunk_index": {"$lte": values.chunk_index + values.after}}]},
                    include=["documents", "metadatas"], limit=7)
                rows = sorted(zip(raw["documents"], raw["metadatas"]), key=lambda r: r[1]["chunk_index"])
                chunks, parts = [], []
                for content, meta in rows:
                    existing = next((c for c in retrieved if c.document_file_id == doc.id and c.chunk_index == meta["chunk_index"]), None)
                    label = existing.cite_label if existing else f"[CITE-{max([int(c.cite_label[6:-1]) for c in retrieved + chunks], default=0) + 1}]"
                    chunk = RetrievedChunk(label, doc.id, meta["chunk_index"], doc.original_filename, kb.id, content, 0)
                    chunks.append(chunk)
                    parts.append(f"{label} chunk={chunk.chunk_index}\n{content}")
                text = "\n\n".join(parts)
                # Only register sources from a page actually returned to the model.
                start, exposed = 0, []
                for chunk, part in zip(chunks, parts):
                    if start < values.offset + values.length and start + len(part) > values.offset:
                        exposed.append(chunk)
                    start += len(part) + 2
                return {"source": "knowledge", "document_id": doc.id, "text": text[values.offset:values.offset + values.length],
                        "next_offset": values.offset + values.length if values.offset + values.length < len(text) else None}, exposed
        result, chunks = await asyncio.to_thread(run)
        for chunk in chunks:
            if not any(c.cite_label == chunk.cite_label for c in retrieved):
                retrieved.append(chunk)
        return ToolOutput(json.dumps(result, ensure_ascii=False))

    return [
        ToolBinding("memory.search", StructuredTool.from_function(name="search_chat_history",
                    description="Search QA-pair history by text/time/conversation. Empty query browses chronologically. Results are previews; use read_context to expand.",
                    args_schema=HistoryArguments, coroutine=history), history),
        ToolBinding("sources.read", StructuredTool.from_function(name="read_context",
                    description="Read a QA pair plus neighboring turns, or a document chunk plus adjacent chunks. Paginated and scope restricted.",
                    args_schema=ReadArguments, coroutine=read), read),
    ]
