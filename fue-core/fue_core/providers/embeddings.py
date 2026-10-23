"""Embedding model factory — build LangChain Embeddings from AIModel record."""

from fue_core.providers.models import AIModel


def _build_embedder(ai_model: AIModel, *, timeout_seconds: float | None = None):
    """根据供应商接口类型构建 LangChain Embeddings 实例。"""
    provider = ai_model.provider
    interface = provider.interface_type

    if interface in ("openai", "openai_compatible"):
        from langchain_openai import OpenAIEmbeddings
        kwargs: dict = {"model": ai_model.api_name}
        if timeout_seconds is not None:
            kwargs.update(request_timeout=timeout_seconds, max_retries=1)
        if provider.api_key:
            kwargs["api_key"] = provider.api_key
        if provider.api_base_url:
            kwargs["base_url"] = provider.api_base_url
        return OpenAIEmbeddings(**kwargs)

    if interface == "google":
        from langchain_google_genai import GoogleGenerativeAIEmbeddings
        kwargs = {"model": ai_model.api_name}
        if provider.api_key:
            kwargs["google_api_key"] = provider.api_key
        return GoogleGenerativeAIEmbeddings(**kwargs)

    if interface == "ollama":
        from langchain_ollama import OllamaEmbeddings
        kwargs = {"model": ai_model.api_name}
        if provider.api_base_url:
            kwargs["base_url"] = provider.api_base_url
        return OllamaEmbeddings(**kwargs)

    raise ValueError(f"Unsupported embedding interface type: {interface}")


def build_embedder(ai_model: AIModel, *, timeout_seconds: float | None = None):
    from fue_core.providers.telemetry import TrackedClient
    return TrackedClient(_build_embedder(ai_model, timeout_seconds=timeout_seconds), ai_model.id, "embedding")
