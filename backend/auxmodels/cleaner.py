"""Document text cleaner — auxiliary model for fixing mal-formatted parsed text.

Typical use-cases
-----------------
- Multi-column PDF layouts where columns interleave
- Page headers / footers mixed into body text
- Garbled table content from PDF extraction
- Incorrectly wrapped paragraphs

Each chunk is cleaned independently via ``clean_chunk()``; failures fall back
to the raw chunk text. The rate limiter ensures aggregate call rate stays
within the model's QPS limit across all parallel threads.
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor

from langchain_core.messages import HumanMessage, SystemMessage

from providers.models import AIModel

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT_BASE = (
    "You are a professional document text cleaning assistant. "
    "The user will provide raw text extracted from a PDF or Word document. "
    "Your goal is to produce a clean, well-structured Markdown document. "
    "The text may have the following issues:\n"
    "- Multi-column layout causing content interleaving\n"
    "- Paragraphs incorrectly split or merged\n"
    "- Page numbers, headers, or footers mixed into body text\n"
    "- Garbled or disordered table content\n"
    "- Excessive whitespace or out-of-order line breaks\n\n"
    "Instructions:\n"
    "1. Output the result as valid Markdown. Use appropriate Markdown syntax for headings, lists, tables, bold/italic, and code blocks.\n"
    "2. Preserve the ORIGINAL LANGUAGE of the text. Fix layout and ordering issues to make the content readable. "
    "You may moderately reword, reorder, or supplement text where necessary to restore semantic coherence and logical flow — "
    "but do not alter the factual meaning or omit essential information.\n"
    "3. Represent all mathematical formulas and equations using LaTeX syntax: "
    "inline formulas with $...$ and display (block) formulas with $$...$$.\n"
    "Output ONLY the cleaned Markdown text — no explanations, preamble, or annotations."
)

_STRIP_REFERENCES_INSTRUCTION = (
    "\n- Remove any reference list, bibliography, or works-cited section "
    "(e.g. sections headed 'References', 'Bibliography', '参考文献', '文献', '引用文献', 'Works Cited'). "
    "These sections typically appear near the end of the document and contain numbered or bulleted citation entries."
)

_STRIP_ANNOTATIONS_INSTRUCTION = (
    "\n- Remove any footnotes, endnotes, annotations, or explanatory notes sections "
    "(e.g. sections headed 'Notes', 'Footnotes', 'Endnotes', '附注', '注释', '脚注', '尾注'). "
    "These are typically numbered or symboled supplementary remarks appearing at the bottom of pages or end of documents."
)


def _build_system_prompt(keep_references: bool, keep_annotations: bool = False) -> str:
    """Return the system prompt, optionally instructing the model to strip references and/or annotations."""
    prompt = _SYSTEM_PROMPT_BASE
    removals: list[str] = []
    if not keep_references:
        removals.append("reference/bibliography sections")
    if not keep_annotations:
        removals.append("footnote/endnote/annotation sections")
    if removals:
        prompt = prompt.replace(
            "You may moderately reword, reorder, or supplement text where necessary to restore semantic coherence and logical flow — "
            "but do not alter the factual meaning or omit essential information.\n",
            "You may moderately reword, reorder, or supplement text where necessary to restore semantic coherence and logical flow — "
            "but do not alter the factual meaning or omit essential information. "
            f"Additionally, remove all {' and '.join(removals)} from the text.\n",
        )
    if not keep_references:
        prompt += _STRIP_REFERENCES_INSTRUCTION
    if not keep_annotations:
        prompt += _STRIP_ANNOTATIONS_INSTRUCTION
    return prompt


def clean_chunk(
    chunk_text: str,
    ai_model: AIModel,
    model_id: int,
    qps: int,
    chunk_idx: int = 0,
    keep_references: bool = False,
    keep_annotations: bool = False,
) -> str:
    """Clean a single chunk of text using *ai_model* with QPS throttling.

    This function is designed to be called from a thread pool.
    Returns the cleaned text, or the original text on failure.
    """
    from auxmodels.rate_limiter import acquire
    from providers.chat import build_llm

    if not chunk_text.strip():
        return chunk_text

    try:
        llm = build_llm(ai_model)
    except ValueError as exc:
        logger.warning("Cleaner: cannot build LLM — %s", exc)
        return chunk_text

    acquire(model_id, qps)
    try:
        response = llm.invoke([
            SystemMessage(content=_build_system_prompt(keep_references, keep_annotations)),
            HumanMessage(content=chunk_text),
        ])
        return response.content.strip() or chunk_text
    except Exception as exc:
        logger.warning("Cleaner failed on chunk %d: %s — using raw text", chunk_idx, exc)
        return chunk_text


def clean_document(
    raw_text: str,
    ai_model: AIModel,
    model_id: int,
    qps: int,
    keep_references: bool = False,
    keep_annotations: bool = False,
) -> str:
    """Clean an entire document by batching on the model's context window.

    Splits *raw_text* into large batches sized to ``ai_model.context_length``,
    making O(text / context) LLM calls instead of O(chunks) calls.
    For a 128 k-token model the whole document typically fits in one call.
    """
    from providers.chat import build_llm

    if not raw_text.strip():
        return raw_text

    try:
        llm = build_llm(ai_model)
    except ValueError as exc:
        logger.warning("Cleaner: cannot build LLM — %s", exc)
        return raw_text

    # context_length is stored in k-tokens; ~3 chars/token.
    # Use 35 % for input to leave headroom for system prompt + output of similar size.
    context_k = ai_model.context_length or 8
    batch_chars = max(int(context_k * 1000 * 3 * 0.35), 3000)

    if len(raw_text) <= batch_chars:
        return _clean_section(llm, raw_text, fallback=raw_text, model_id=model_id, qps=qps, keep_references=keep_references, keep_annotations=keep_annotations)

    batches = [raw_text[i: i + batch_chars] for i in range(0, len(raw_text), batch_chars)]
    logger.info(
        "Cleaner: %d batch(es) for document (%d chars/batch, context=%dk)",
        len(batches), batch_chars, context_k,
    )
    with ThreadPoolExecutor(max_workers=len(batches)) as executor:
        futures = [
            executor.submit(
                _clean_section, llm, batch,
                fallback=batch, model_id=model_id, qps=qps,
                section_idx=idx, keep_references=keep_references,
                keep_annotations=keep_annotations,
            )
            for idx, batch in enumerate(batches)
        ]
    return "\n".join(f.result() for f in futures)


def clean(raw_text: str, ai_model: AIModel, keep_references: bool = False, keep_annotations: bool = False) -> str:
    """Clean and reorganize *raw_text* using *ai_model* (legacy single-text API).

    Returns the cleaned text, or the original text on complete failure.
    """
    from providers.chat import build_llm

    if not raw_text.strip():
        return raw_text

    try:
        llm = build_llm(ai_model)
    except ValueError as exc:
        logger.warning("Cleaner: cannot build LLM — %s", exc)
        return raw_text

    model_id = ai_model.id
    qps = ai_model.qps or 0

    _SECTION_SIZE = 2500
    if len(raw_text) <= _SECTION_SIZE:
        return _clean_section(llm, raw_text, fallback=raw_text, model_id=model_id, qps=qps, keep_references=keep_references, keep_annotations=keep_annotations)

    sections = [raw_text[i: i + _SECTION_SIZE] for i in range(0, len(raw_text), _SECTION_SIZE)]
    cleaned_parts: list[str] = []
    for idx, section in enumerate(sections):
        cleaned_parts.append(
            _clean_section(llm, section, fallback=section, model_id=model_id, qps=qps, section_idx=idx, keep_references=keep_references, keep_annotations=keep_annotations)
        )

    return "\n".join(cleaned_parts)


def _clean_section(
    llm, text: str, *, fallback: str, model_id: int, qps: int, section_idx: int = 0, keep_references: bool = False, keep_annotations: bool = False
) -> str:
    from auxmodels.rate_limiter import acquire
    acquire(model_id, qps)
    try:
        response = llm.invoke([
            SystemMessage(content=_build_system_prompt(keep_references, keep_annotations)),
            HumanMessage(content=text),
        ])
        return response.content.strip() or fallback
    except Exception as exc:
        logger.warning("Cleaner failed on section %d: %s — using raw text", section_idx, exc)
        return fallback
