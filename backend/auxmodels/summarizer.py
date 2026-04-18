"""Conversation summarizer — auxiliary model for condensing chat turns.

After each non-streaming or streaming chat response, if a summary model
is configured in settings, this module produces a concise summary of the
full conversation turn (all user messages + the assistant response).

The summary is returned to the client as an additional field in the
response payload so the frontend can display / store it.
"""

from __future__ import annotations

import logging

from langchain_core.messages import HumanMessage, SystemMessage

from providers.models import AIModel

logger = logging.getLogger(__name__)

_PROMPTS: dict[str, tuple[str, str]] = {
    "zh": (
        "你是一位对话标题生成助手。"
        "请根据以下对话内容，生成一个极简的对话标题。\n"
        "要求：\n"
        "- 标题控制在 10 个字以内\n"
        "- 只输出标题文本，不添加标点、引号或任何前言说明",
        "本轮对话内容：\n\n{text}",
    ),
    "en": (
        "You are a conversation title generator. "
        "Generate a very short title for the following conversation.\n"
        "Requirements:\n"
        "- Keep the title under 10 words\n"
        "- Output only the title text, without any punctuation, quotes, preamble or explanation",
        "Conversation content:\n\n{text}",
    ),
}


def _get_prompts(language: str) -> tuple[str, str]:
    """Return (system_prompt, human_template) for *language* (falls back to 'zh')."""
    return _PROMPTS.get(language, _PROMPTS["zh"])


async def asummarize(conversation_text: str, ai_model: AIModel, language: str = "zh") -> str:
    """Async: summarize *conversation_text* using *ai_model*.

    *language* controls the output language (``'zh'`` or ``'en'``).
    Returns empty string on failure so callers never need to handle exceptions.
    """
    from providers.chat import build_llm

    system_prompt, human_template = _get_prompts(language)
    try:
        llm = build_llm(ai_model)
        response = await llm.ainvoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=human_template.format(text=conversation_text)),
        ])
        return response.content.strip()
    except Exception as exc:
        logger.warning("Summarizer failed: %s", exc)
        return ""


def summarize(conversation_text: str, ai_model: AIModel, language: str = "zh") -> str:
    """Sync version for use in background tasks.

    *language* controls the output language (``'zh'`` or ``'en'``).
    """
    from providers.chat import build_llm

    system_prompt, human_template = _get_prompts(language)
    try:
        llm = build_llm(ai_model)
        response = llm.invoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=human_template.format(text=conversation_text)),
        ])
        return response.content.strip()
    except Exception as exc:
        logger.warning("Summarizer failed: %s", exc)
        return ""
