"""Propagate a turn's ledger into synchronous retrieval worker threads."""
from contextvars import ContextVar
import hashlib
import json
from langchain_core.messages import HumanMessage

active_ledger = ContextVar("fue_model_ledger", default=None)


class TrackedClient:
    def __init__(self, client, model_id, category):
        self.client, self.model_id, self.category = client, model_id, category

    def __getattr__(self, name):
        method = getattr(self.client, name)
        if name not in {"embed_query", "embed_documents", "rerank"}:
            return method
        def call(*args, **kwargs):
            ledger = active_ledger.get()
            if ledger is None:
                return method(*args, **kwargs)
            payload = json.dumps([args, kwargs], ensure_ascii=False, default=str)
            key = (self.model_id, hashlib.sha256(payload.encode()).hexdigest())
            cache = ledger.embedding_cache
            if name == "embed_query" and key in cache:
                return cache[key]
            estimated, _, started = ledger._start([HumanMessage(content=payload)], self.category)
            status = "failed"
            try:
                result = method(*args, **kwargs)
                status = "completed"
                if name == "embed_query":
                    cache[key] = result
                return result
            finally:
                # These adapters return vectors/ranks, without provider token metadata.
                ledger._finish(estimated, started, None, status, self.category, self.model_id)
        return call
