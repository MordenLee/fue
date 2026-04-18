"""LLM factory — build a LangChain ChatModel from an AIModel record.

Extracted so that both the chat router and auxiliary-model modules
can share the same construction logic without circular imports.
Raises ValueError (not HTTPException) so background-task callers
can handle errors gracefully.
"""

from __future__ import annotations

from sqlalchemy.orm import joinedload

from providers.models import AIModel


def build_llm(ai_model: AIModel):
    """Return a LangChain ChatModel for *ai_model*.

    Raises
    ------
    ValueError  if the provider interface type is not supported.
    """
    provider = ai_model.provider
    interface = provider.interface_type
    kwargs: dict = {"model": ai_model.api_name}

    if provider.api_key:
        kwargs["api_key"] = provider.api_key
    if provider.api_base_url:
        kwargs["base_url"] = provider.api_base_url
    if ai_model.temperature is not None:
        kwargs["temperature"] = ai_model.temperature
    if ai_model.top_p is not None:
        kwargs["top_p"] = ai_model.top_p

    if interface in ("openai", "openai_compatible"):
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(**kwargs)

    if interface == "anthropic":
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(**kwargs)

    if interface == "google":
        from langchain_google_genai import ChatGoogleGenerativeAI
        g: dict = {"model": ai_model.api_name}
        if provider.api_key:
            g["google_api_key"] = provider.api_key
        if ai_model.temperature is not None:
            g["temperature"] = ai_model.temperature
        if ai_model.top_p is not None:
            g["top_p"] = ai_model.top_p
        return ChatGoogleGenerativeAI(**g)

    if interface == "ollama":
        from langchain_ollama import ChatOllama
        ol: dict = {"model": ai_model.api_name}
        if provider.api_base_url:
            ol["base_url"] = provider.api_base_url
        if ai_model.temperature is not None:
            ol["temperature"] = ai_model.temperature
        if ai_model.top_p is not None:
            ol["top_p"] = ai_model.top_p
        return ChatOllama(**ol)

    raise ValueError(f"Unsupported interface type: {interface!r}")


def load_chat_model(model_id: int, db) -> AIModel:
    """Load an AIModel by ID with its provider eagerly fetched.

    Returns None if not found, disabled, or not of type 'chat'.
    Used by aux modules that want a best-effort model load.
    """
    record = (
        db.query(AIModel)
        .options(joinedload(AIModel.provider))
        .filter(AIModel.id == model_id)
        .first()
    )
    if not record:
        return None
    if not record.is_enabled or not record.provider.is_enabled:
        return None
    if record.model_type != "chat":
        return None
    return record
