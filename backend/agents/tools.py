"""Explicit tool bindings; tools cannot obtain database sessions from a request."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Awaitable, Callable, Literal

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, ConfigDict, Field, field_validator


TOOL_IDS = {"knowledge.search"}


class SearchArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str = Field(min_length=1, max_length=4000)
    mode: Literal["vector", "keyword", "hybrid"] = "vector"
    top_n: int = Field(default=0, ge=0, le=50)

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

    from chat.tools import make_search_tool

    # The KB scope is bound by the server, not exposed as an LLM tool argument.
    scope = tuple(kb_ids)

    async def execute(args: dict) -> ToolOutput:
        validated = SearchArguments.model_validate(args).model_dump()

        def search():
            # Return local results; timeout/cancellation must not mutate shared state.
            with session_factory() as db:
                tool, chunks = make_search_tool(
                    list(scope), db, initial_cite_num + len(retrieved), raise_on_error=True,
                )
                return tool.invoke(validated), chunks

        result, chunks = await asyncio.to_thread(search)
        retrieved.extend(chunks)
        return ToolOutput(result, "ok" if chunks else "empty")

    schema = StructuredTool.from_function(
        name="search_knowledge_base",
        description="Search selected knowledge bases. Returns excerpts with [CITE-N] source markers.",
        args_schema=SearchArguments,
        coroutine=execute,
    )
    return ToolBinding("knowledge.search", schema, execute)
