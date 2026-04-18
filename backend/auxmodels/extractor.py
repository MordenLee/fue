"""Information extractor — auxiliary model for extracting citation metadata + abstract.

Only the first ~3000 characters of the document are sent (≈ 2 pages of an A4 document),
which is sufficient to identify title, authors, year, abstract, and identifiers.

The LLM is asked to respond with a JSON object.  The result is sanitised before
being used to upsert a Citation record and update DocumentFile.abstract.
"""

from __future__ import annotations

import json
import logging
import re

from langchain_core.messages import HumanMessage, SystemMessage

from providers.models import AIModel

logger = logging.getLogger(__name__)

# ~3000 chars ≈ first 2 pages of a typical A4 document at 1500 chars/page
_SNIPPET_CHARS = 3000

_VALID_CITATION_TYPES = {"article", "book", "chapter", "thesis", "conference", "website", "other"}

_SYSTEM_PROMPT = """\
You are an academic document information extraction assistant.
The user will provide the first two pages of a document and its filename.
Extract the following information and return it as a JSON object:

{
  "title": "Full title of the paper/book",
  "authors": ["Author 1 full name", "Author 2 full name"],
  "year": 2023,
  "citation_type": "article|book|chapter|thesis|conference|website|other",
  "source": "Journal/book/conference name",
  "volume": "Volume number if available, otherwise null",
  "issue": "Issue number if available, otherwise null",
  "pages": "Page range if available, otherwise null",
  "publisher": "Publisher if available, otherwise null",
  "doi": "DOI if available, otherwise null",
  "isbn": "ISBN if available, otherwise null",
  "url": "URL if available, otherwise null",
  "abstract": "100–300 word abstract; extract directly if present, otherwise summarize from content"
}

Rules:
- Output ONLY the JSON object — no extra text or markdown code fences
- Set undetermined fields to null
- abstract must be provided and must not be null
- citation_type must be one of the listed values
- ALL extracted text values (title, authors, source, abstract, etc.) MUST be in the SAME LANGUAGE as the source document\
"""


def extract(raw_text: str, filename: str, ai_model: AIModel) -> dict:
    """Extract structured information from the beginning of a document.

    Parameters
    ----------
    raw_text:  Full parsed document text (first _SNIPPET_CHARS chars will be used).
    filename:  Original filename (helps the LLM infer document type/year etc.).
    ai_model:  The auxiliary model to invoke.

    Returns
    -------
    A sanitised dict with keys matching Citation ORM fields plus 'abstract'.
    Returns ``{}`` on failure so callers can safely skip.
    """
    from providers.chat import build_llm

    snippet = raw_text[:_SNIPPET_CHARS].strip()
    if not snippet:
        return {}

    try:
        llm = build_llm(ai_model)
    except ValueError as exc:
        logger.warning("Extractor: cannot build LLM — %s", exc)
        return {}

    try:
        from auxmodels.rate_limiter import acquire
        acquire(ai_model.id, ai_model.qps or 0)
        response = llm.invoke([
            SystemMessage(content=_SYSTEM_PROMPT),
            HumanMessage(content=f"文件名：{filename}\n\n文档内容（前两页）：\n{snippet}"),
        ])
        return _parse_response(response.content)
    except Exception as exc:
        logger.warning("Info extraction failed for '%s': %s", filename, exc)
        return {}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _parse_response(text: str) -> dict:
    """Parse and sanitise the LLM JSON response."""
    text = text.strip()
    # Strip markdown code fences if present
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text)

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        # Fall back: find the first {...} block
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            logger.debug("Extractor: no JSON object found in response")
            return {}
        try:
            data = json.loads(match.group())
        except json.JSONDecodeError:
            return {}

    if not isinstance(data, dict):
        return {}

    result: dict = {}

    # String fields
    for field in ("title", "source", "volume", "issue", "pages",
                  "publisher", "doi", "isbn", "url", "abstract"):
        v = data.get(field)
        if v and isinstance(v, str) and v.strip():
            result[field] = v.strip()

    # citation_type with validation
    ct = data.get("citation_type")
    result["citation_type"] = ct if ct in _VALID_CITATION_TYPES else "other"

    # year (integer)
    year = data.get("year")
    if isinstance(year, (int, float)) and 1000 <= int(year) <= 9999:
        result["year"] = int(year)

    # authors (list of non-empty strings)
    authors = data.get("authors")
    if isinstance(authors, list):
        clean_authors = [str(a).strip() for a in authors if a and str(a).strip()]
        if clean_authors:
            result["authors"] = clean_authors

    return result
