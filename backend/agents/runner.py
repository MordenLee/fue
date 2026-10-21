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
        tools_enabled = bool(self.tools)
        calls, cache, evidence = 0, {}, []
        try:
            bound = self.llm.bind_tools([t.schema for t in self.tools.values()]) if tools_enabled else self.llm
        except (NotImplementedError, AttributeError):
            # Declared fallback is valid only for one unambiguous read-only tool.
            if self.agent.definition.unsupported_tool_mode != "retrieve_then_answer" or len(self.tools) != 1:
                raise ValueError("Model cannot bind the required tools")
            tool = next(iter(self.tools.values()))
            query = next((content_to_text(m.content) for m in reversed(base) if m.type == "human"), "")
            async for event in self._execute(tool, {"query": query}, "fallback", cache):
                yield event
                if event.type == "tool_result":
                    evidence.append(event.data)
            working = self._evidence_context(base, evidence)
            tools_enabled = False
            bound = self.llm

        for model_index in range(limits.max_model_calls):
            # Always reserve the last model call for an answer without tools.
            may_use_tools = tools_enabled and calls < self.tool_budget and model_index < limits.max_model_calls - 1
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
            for tc in tool_calls:
                name, args = tc["name"], tc["args"]
                if name not in self.tools:
                    raise ValueError(f"Model requested an unregistered tool: {name}")
                if calls >= self.tool_budget:
                    raise ValueError("Tool call budget exhausted")
                calls += 1
                async for event in self._execute(self.tools[name], args, tc.get("id", str(calls)), cache):
                    yield event
                    if event.type == "tool_result":
                        evidence.append(event.data)
                        results.append(ToolMessage(content=json.dumps(event.data, ensure_ascii=False), tool_call_id=tc["id"]))
            if self.agent.definition.tool_protocol == "evidence_synthesis":
                # Compatibility for reasoning providers: never replay incomplete tool history.
                working = self._evidence_context(base, evidence)
                tools_enabled = False
            else:
                # Convert streamed chunks to a proper assistant message for native replay.
                from langchain_core.messages import AIMessage
                working.extend([AIMessage(content=response.content, tool_calls=tool_calls), *results])
        raise ValueError("Model call budget exhausted")

    async def _execute(self, tool, args, call_id, cache):
        yield AgentEvent("tool_call", {"name": tool.schema.name, "args": args})
        try:
            args = tool.schema.args_schema.model_validate(args).model_dump()
        except Exception as exc:
            yield AgentEvent("tool_result", {"call_id": call_id, "tool": tool.id,
                                            "status": "error", "content": f"Invalid tool arguments: {exc}"})
            return
        key = (tool.id, json.dumps(args, sort_keys=True, ensure_ascii=False))
        if key not in cache:
            try:
                async with asyncio.timeout(self.agent.definition.limits.tool_timeout_seconds):
                    output = await tool.execute(args)
                result = output if isinstance(output, ToolOutput) else ToolOutput(output)
                text = result.content
                cap = self.agent.definition.limits.max_tool_result_chars
                cache[key] = {"call_id": call_id, "tool": tool.id, "status": result.status,
                              "content": text[:cap], "truncated": len(text) > cap}
            except Exception as exc:
                cache[key] = {"call_id": call_id, "tool": tool.id, "status": "error",
                              "content": f"Tool execution failed: {exc}"}
        yield AgentEvent("tool_result", {**cache[key], "call_id": call_id})

    @staticmethod
    def _evidence_context(base, evidence):
        # This envelope is data, not an additional system instruction.
        block = HumanMessage(content="<tool-results>\n" + json.dumps(evidence, ensure_ascii=False) + "\n</tool-results>")
        return [*base[:-1], block, base[-1]]
