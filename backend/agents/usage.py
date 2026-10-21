"""Per-turn accounting; absent provider usage is unknown rather than zero."""
import asyncio
import time
from agents.context import ContextLimitError
from memory.working import estimate_messages, estimate


class UsageLedger:
    def __init__(self, *, sink=None, input_limit=None, output_limit=None, per_input=None, per_output=None, schema_tokens=0):
        self.sink = sink
        self.input_limit, self.output_limit = input_limit, output_limit
        self.per_input, self.per_output = per_input, per_output
        self.schema_tokens = schema_tokens
        self.input_used = self.output_used = 0
        self.records = []
        self.embedding_cache = {}

    @staticmethod
    def bounded(model, cap):
        if not cap or not hasattr(model, "bind"):
            return model
        base = model
        while getattr(base, "bound", None) is not None:
            base = base.bound
        module = type(base).__module__
        if module.startswith("langchain_google_genai"):
            return model.bind(max_output_tokens=cap)
        if module.startswith("langchain_ollama"):
            return model.bind(options={"num_predict": cap})
        return model.bind(max_tokens=cap)

    def _start(self, messages, category):
        estimated = estimate_messages(messages) + (self.schema_tokens if category == "answer" else 0)
        if self.per_input and category == "answer" and estimated > self.per_input:
            raise ContextLimitError("Model input exceeds per-call token budget")
        if self.input_limit and self.input_used + estimated > self.input_limit:
            raise ContextLimitError("Turn input token budget exhausted; no further model call made")
        remaining = self.output_limit - self.output_used if self.output_limit else None
        if category in {"compaction", "title"} and remaining is not None:
            remaining -= self.per_output or 512  # Preserve a final answer allowance.
        if remaining is not None and remaining < 64:
            raise ContextLimitError("Turn output token budget exhausted")
        cap = min(self.per_output or 4096, remaining) if remaining is not None else self.per_output
        return estimated, cap, time.monotonic()

    def _finish(self, estimated, started, response, status, category, model_id, usage_override=None):
        usage = usage_override or (getattr(response, "usage_metadata", None) if response is not None else None)
        if not usage and response is not None:
            raw = (getattr(response, "response_metadata", None) or {}).get("token_usage")
            if raw:
                usage = {"input_tokens": raw.get("prompt_tokens"), "output_tokens": raw.get("completion_tokens")}
        output = estimate({"content": response.content, "tool_calls": getattr(response, "tool_calls", None),
                           "reasoning_content": (getattr(response, "additional_kwargs", None) or {}).get("reasoning_content")}) if response is not None else 0
        self.input_used += (usage or {}).get("input_tokens") or estimated
        self.output_used += (usage or {}).get("output_tokens") or output
        info = {"status": status, "input_estimated": estimated, "output_estimated": output,
                "usage": dict(usage) if usage else None, "elapsed_ms": int((time.monotonic()-started)*1000)}
        self.records.append({"category": category, "model_id": model_id, **info})
        if self.sink:
            self.sink(category, model_id, info)

    async def invoke(self, model, messages, *, streaming=False, category="answer", model_id=None):
        estimated, cap, started = self._start(messages, category)
        response, status = None, "failed"
        try:
            bounded = self.bounded(model, cap)
            response = await bounded.ainvoke(messages)
            status = "completed"
            return response
        except asyncio.CancelledError:
            status = "cancelled"
            raise
        finally:
            self._finish(estimated, started, response, status, category, model_id)

    async def stream(self, model, messages, model_id=None):
        estimated, cap, started = self._start(messages, "answer")
        response, status = None, "failed"
        bounded = self.bounded(model, cap)
        gen = bounded.astream(messages)
        base = model
        while getattr(base, "bound", None) is not None:
            base = base.bound
        # OpenAI-compatible endpoints can send cumulative usage on every chunk.
        # AIMessageChunk addition sums metadata, which would multiply these counts.
        cumulative_usage = type(base).__module__.startswith("langchain_openai")
        snapshot = None
        def merge_snapshot(old, new):
            result = dict(old or {})
            for key, value in new.items():
                if isinstance(value, dict):
                    result[key] = merge_snapshot(result.get(key), value)
                elif isinstance(value, (int, float)):
                    result[key] = max(result.get(key, 0), value)
            return result
        try:
            async for chunk in gen:
                if cumulative_usage and getattr(chunk, "usage_metadata", None):
                    snapshot = merge_snapshot(snapshot, chunk.usage_metadata)
                response = chunk if response is None else response + chunk
                yield chunk
            status = "completed"
        except asyncio.CancelledError:
            status = "cancelled"
            raise
        finally:
            try:
                await gen.aclose()
            finally:
                self._finish(estimated, started, response, status, "answer", model_id, snapshot)
