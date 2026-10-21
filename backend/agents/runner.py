"""One execution loop for streaming/non-streaming plain chat and RAG.

HTTP, citation formatting, persistence and task instructions live outside this module.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass

from langchain_core.messages import HumanMessage, ToolMessage

from agents.context import check_context
from agents.registry import ResolvedAgent
from agents.tools import ToolBinding, ToolOutput


def content_to_text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for part in content:
            if isinstance(part, str):
                parts.append(part)
            elif isinstance(part, dict):
                value = next((part[k] for k in ("text", "content", "value") if isinstance(part.get(k), str)), "")
                parts.append(value)
        return "".join(parts)
    return "" if content is None else str(content)


@dataclass(frozen=True)
class AgentEvent:
    type: str
    data: object = None


class AgentRunner:
    def __init__(self, agent: ResolvedAgent, llm, tools: list[ToolBinding] = (),
                 *, context_length=None, max_tool_calls=None):
        self.agent, self.llm = agent, llm
        self.tools = {tool.schema.name: tool for tool in tools}
        if len(self.tools) != len(tools):
            raise ValueError("Duplicate model-facing tool names")
        supplied = {tool.id for tool in tools}
        if supplied != set(agent.tool_ids):
            raise ValueError("Tool bindings do not match resolved agent whitelist")
        self.context_length = context_length
        limits = agent.definition.limits
        self.tool_budget = min(limits.max_tool_calls, max_tool_calls or limits.max_tool_calls)

    async def events(self, messages, *, streaming=True):
        limits = self.agent.definition.limits
        # timeout also cancels pending provider/tool awaitables. CancelledError propagates.
        async with asyncio.timeout(limits.run_timeout_seconds):
            async for event in self._events(list(messages), streaming):
                yield event

    async def _events(self, messages, streaming):
        limits = self.agent.definition.limits
        working, base = list(messages), list(messages)
        # Conservative character budget (<= one token/character for this allowance).
        # All tool calls share this cap, including JSON envelopes and later page reads.
        base_chars = sum(len(str(m.content)) for m in base)
        self.result_budget = min(limits.max_tool_result_chars,
                                 max(0, int(self.context_length * 1000 * 0.8) - base_chars - 2048)
                                 if self.context_length else limits.max_tool_result_chars)
        # Reserve envelope/receipt space as well; raw result text cannot consume it.
        self.result_budget = self.result_budget * 3 // 4
        self.used_result_chars = 0
        self.used_search_chars = 0
        self.has_reader = any(t.id == "sources.read" for t in self.tools.values())
        self.blocked_tool_names = set()
        tools_enabled = bool(self.tools)
        calls, cache, evidence = 0, {}, []
        from memory import service as memory_service
        deletion_epoch = memory_service.DELETION_EPOCH
        try:
            bound = self.llm.bind_tools([t.schema for t in self.tools.values()]) if tools_enabled else self.llm
        except (NotImplementedError, AttributeError):
            # Declared fallback is valid only for one unambiguous read-only tool.
            retrieval = [t for t in self.tools.values() if t.id == "knowledge.search"]
            if not retrieval and len(self.tools) == 1:
                retrieval = list(self.tools.values())
            if self.agent.definition.unsupported_tool_mode != "retrieve_then_answer" or len(retrieval) != 1:
                raise ValueError("Model cannot bind the required tools")
            tool = retrieval[0]
            query = next((content_to_text(m.content) for m in reversed(base) if m.type == "human"), "")
            async for event in self._execute(tool, {"query": query}, "fallback", cache):
                yield event
                if event.type == "tool_result":
                    evidence.append(event.data)
            working = self._evidence_context(base, evidence)
            tools_enabled = False
            bound = self.llm

        for model_index in range(limits.max_model_calls):
            if memory_service.DELETION_EPOCH != deletion_epoch:
                # Drop transient tool caches/evidence when source history is deleted.
                evidence.clear()
                cache.clear()
                working = list(base)
                self.used_result_chars = 0
                self.used_search_chars = 0
                self.blocked_tool_names.clear()
                deletion_epoch = memory_service.DELETION_EPOCH
            # Always reserve the last model call for an answer without tools.
            may_use_tools = (tools_enabled and calls < self.tool_budget and model_index < limits.max_model_calls - 1
                             and self.result_budget - self.used_result_chars > 512)
            available = [t.schema for t in self.tools.values() if t.schema.name not in self.blocked_tool_names and
                         not (self.has_reader and t.id.endswith(".search") and self.used_search_chars >= self.result_budget // 2 - 256)]
            if may_use_tools and available and len(available) != len(self.tools):
                model = self.llm.bind_tools(available)
            elif may_use_tools and not available:
                may_use_tools, model = False, self.llm
            else:
                model = bound if may_use_tools else self.llm
            check_context(working, self.context_length)
            response = None
            if streaming:
                gen = model.astream(working)
                try:
                    async for chunk in gen:
                        response = chunk if response is None else response + chunk
                        text = content_to_text(chunk.content)
                        if text:
                            yield AgentEvent("token", text)
                finally:
                    await gen.aclose()
            else:
                response = await model.ainvoke(working)
            if response is None:
                raise ValueError("Model returned an empty response")
            tool_calls = getattr(response, "tool_calls", None) or []
            if not tool_calls:
                text = content_to_text(response.content)
                if not text.strip():
                    raise ValueError("Model returned no text answer")
                yield AgentEvent("final", text)
                return
            if not may_use_tools:
                raise ValueError("Model requested tools after tool execution was disabled")
            yield AgentEvent("clear")
            results = []
            executed_calls = []
            for tc in tool_calls:
                name, args = tc["name"], tc["args"]
                if name not in self.tools:
                    raise ValueError(f"Model requested an unregistered tool: {name}")
                if calls >= self.tool_budget or self.result_budget - self.used_result_chars <= 512:
                    # Do not execute excess calls; let the reserved final model call converge.
                    break
                calls += 1
                executed_calls.append(tc)
                async for event in self._execute(self.tools[name], args, tc.get("id", str(calls)), cache):
                    yield event
                    if event.type == "tool_result":
                        evidence.append(event.data)
                        results.append(ToolMessage(content=json.dumps(event.data, ensure_ascii=False), tool_call_id=tc["id"]))
            if self.agent.definition.tool_protocol in {"evidence_synthesis", "iterative_evidence"}:
                # Compatibility for reasoning providers: never replay incomplete tool history.
                working = self._evidence_context(base, evidence)
                tools_enabled = self.agent.definition.tool_protocol == "iterative_evidence"
            else:
                # Convert streamed chunks to a proper assistant message for native replay.
                from langchain_core.messages import AIMessage
                working.extend([AIMessage(content=response.content, tool_calls=executed_calls), *results])
        raise ValueError("Model call budget exhausted")

    async def _execute(self, tool, args, call_id, cache):
        yield AgentEvent("tool_call", {"name": tool.schema.name, "args": args})
        try:
            args = tool.schema.args_schema.model_validate(args).model_dump()
        except Exception as exc:
            result = {"call_id": call_id, "tool": tool.id, "status": "error",
                      "content": "Invalid tool arguments; use the registered parameter schema."}
            self.used_result_chars += len(json.dumps(result)) + 2
            yield AgentEvent("tool_result", result)
            return
        key = (tool.id, json.dumps(args, sort_keys=True, ensure_ascii=False))
        cached = key in cache
        if cached and self.has_reader:
            # A repeated identical request is not progress. Keep readers available
            # rather than spending the remaining turns replaying the same search.
            self.blocked_tool_names.add(tool.schema.name)
        if key not in cache:
            try:
                if self.has_reader and tool.id.endswith(".search") and self.used_search_chars >= self.result_budget // 2 - 256:
                    raise ValueError("Search preview budget exhausted; use read_context on existing hits")
                async with asyncio.timeout(self.agent.definition.limits.tool_timeout_seconds):
                    from memory.mcp import call_in_process
                    output = await call_in_process(tool, args)
                result = output if isinstance(output, ToolOutput) else ToolOutput(output)
                text = result.content
                cap = self.agent.definition.limits.max_tool_result_chars
                cache[key] = {"call_id": call_id, "tool": tool.id, "name": tool.schema.name, "status": result.status,
                              "content": text[:cap], "truncated": len(text) > cap}
            except Exception as exc:
                cache[key] = {"call_id": call_id, "tool": tool.id, "name": tool.schema.name, "status": "error",
                              "content": f"Tool execution failed: {exc}"}
        result = {**cache[key], "call_id": call_id, "cached": cached}
        room = max(0, self.result_budget - self.used_result_chars - 256)
        if self.has_reader and tool.id.endswith(".search"):
            room = min(room, max(0, self.result_budget // 2 - self.used_search_chars - 128))
        original = str(result.get("content", ""))
        # JSON escaping is included in the budget. Binary search avoids quadratic slicing.
        lo, hi = 0, min(len(original), room)
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if len(json.dumps({**result, "content": original[:mid]}, ensure_ascii=False)) <= room:
                lo = mid
            else:
                hi = mid - 1
        result["content"] = original[:lo]
        result["truncated"] = result.get("truncated", False) or lo < len(original)
        if not lo:
            result["content"] = "Result omitted: retrieval budget exhausted."
        self.used_result_chars += len(json.dumps(result, ensure_ascii=False)) + 2
        if tool.id.endswith(".search"):
            self.used_search_chars += len(json.dumps(result, ensure_ascii=False)) + 2
        yield AgentEvent("tool_result", result)

    @staticmethod
    def _evidence_context(base, evidence):
        # This envelope is data, not an additional system instruction.
        receipts = [{"name": e.get("name", e.get("tool")), "status": e.get("status")} for e in evidence]
        block = HumanMessage(content="<execution-receipts>" + json.dumps(receipts, ensure_ascii=False) +
                             "</execution-receipts>\n<tool-results>\n" + json.dumps(evidence, ensure_ascii=False) + "\n</tool-results>")
        # Observations follow the question, so the last user instruction does not
        # restart the plan from step one on every compatibility-mode iteration.
        return [*base, block]
