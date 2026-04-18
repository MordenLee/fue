"""Reranker model factory — build a Reranker from AIModel record.

Usage:
    reranker = build_reranker(ai_model)
    ranked = reranker.rerank(query="what is RAG?", documents=["doc1 text", "doc2 text"])
    # returns list of (original_index, score) sorted by score descending
"""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import HTTPException
from providers.models import AIModel


@dataclass
class RankedResult:
    index: int          # original position in the input list
    score: float
    document: str


class _CohereReranker:
    def __init__(self, api_key: str, model: str, base_url: str | None = None):
        import cohere
        kwargs: dict = {"api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url
        self._client = cohere.Client(**kwargs)
        self._model = model

    def rerank(self, query: str, documents: list[str], top_n: int | None = None) -> list[RankedResult]:
        response = self._client.rerank(
            model=self._model,
            query=query,
            documents=documents,
            top_n=top_n,
        )
        results = [
            RankedResult(index=r.index, score=r.relevance_score, document=documents[r.index])
            for r in response.results
        ]
        return sorted(results, key=lambda r: r.score, reverse=True)


class _JinaReranker:
    def __init__(self, api_key: str, model: str, base_url: str | None = None):
        self._api_key = api_key
        self._model = model
        self._base_url = (base_url or "https://api.jina.ai/v1").rstrip("/")

    def rerank(self, query: str, documents: list[str], top_n: int | None = None) -> list[RankedResult]:
        import requests
        payload: dict = {
            "model": self._model,
            "query": query,
            "documents": documents,
        }
        if top_n is not None:
            payload["top_n"] = top_n

        resp = requests.post(
            f"{self._base_url}/rerank",
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        results = [
            RankedResult(
                index=r["index"],
                score=r["relevance_score"],
                document=documents[r["index"]],
            )
            for r in data["results"]
        ]
        return sorted(results, key=lambda r: r.score, reverse=True)


class _OpenAICompatibleReranker:
    """OpenAI-compatible reranker (e.g. SiliconFlow /rerank endpoint).

    The request/response format is identical to Jina's rerank API.
    """

    def __init__(self, api_key: str, model: str, base_url: str):
        if not base_url:
            raise ValueError("api_base_url is required for openai_compatible reranker")
        self._api_key = api_key
        self._model = model
        self._base_url = base_url.rstrip("/")

    def rerank(self, query: str, documents: list[str], top_n: int | None = None) -> list[RankedResult]:
        import requests
        payload: dict = {
            "model": self._model,
            "query": query,
            "documents": documents,
        }
        if top_n is not None:
            payload["top_n"] = top_n

        resp = requests.post(
            f"{self._base_url}/rerank",
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        results = [
            RankedResult(
                index=r["index"],
                score=r["relevance_score"],
                document=documents[r["index"]],
            )
            for r in data["results"]
        ]
        return sorted(results, key=lambda r: r.score, reverse=True)


def build_reranker(ai_model: AIModel) -> _CohereReranker | _JinaReranker | _OpenAICompatibleReranker:
    """根据供应商接口类型构建 Reranker 实例。

    Supported interface types:
    - ``cohere``             — Cohere Rerank API
    - ``jina``               — Jina AI Rerank API
    - ``openai_compatible``  — OpenAI-compatible /rerank endpoint (e.g. SiliconFlow)
    - ``openai``             — same as openai_compatible
    """
    provider = ai_model.provider
    interface = provider.interface_type

    if interface == "cohere":
        if not provider.api_key:
            raise HTTPException(status_code=400, detail="Cohere API key is required for reranking")
        return _CohereReranker(
            api_key=provider.api_key,
            model=ai_model.api_name,
            base_url=provider.api_base_url,
        )

    if interface == "jina":
        if not provider.api_key:
            raise HTTPException(status_code=400, detail="Jina API key is required for reranking")
        return _JinaReranker(
            api_key=provider.api_key,
            model=ai_model.api_name,
            base_url=provider.api_base_url,
        )

    if interface in ("openai", "openai_compatible"):
        if not provider.api_key:
            raise HTTPException(status_code=400, detail="API key is required for reranking")
        if not provider.api_base_url:
            raise HTTPException(status_code=400, detail="api_base_url is required for openai_compatible reranking")
        return _OpenAICompatibleReranker(
            api_key=provider.api_key,
            model=ai_model.api_name,
            base_url=provider.api_base_url,
        )

    raise HTTPException(
        status_code=400,
        detail=f"Unsupported reranking interface type: {interface}. Supported: cohere, jina, openai_compatible",
    )
