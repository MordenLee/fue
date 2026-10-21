"""AI-powered citation extraction and matching utilities.

Two strategies are supported:

1. ai_extract_citations_stream  (async-friendly, per-document progress)
   ─────────────────────────────
   Generator that yields progress dicts for each document.
   The async SSE endpoint wraps each blocking LLM call with asyncio.to_thread.

2. match_citations_from_text
   ─────────────────────────
   Single LLM call: given a list of document IDs and a raw citation text block
   pasted by the user, the model matches each entry to a document and upserts
   the resulting Citation records.
   Uses the ``info_extract_model_id`` setting.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Optional

from langchain_core.messages import HumanMessage, SystemMessage
from sqlalchemy.orm import Session, joinedload

from knowledge.documents.models import Citation, DocumentFile
from knowledge.parser import parse_file
from providers.models import AIModel
from settings.models import DEFAULTS, Setting

logger = logging.getLogger(__name__)

_SNIPPET_CHARS = 3000
_VALID_TYPES = {"article", "book", "chapter", "thesis", "conference", "website", "other"}

# ---------------------------------------------------------------------------
# System prompts
# ---------------------------------------------------------------------------

_EXTRACT_SYSTEM = """\
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
  "url": "URL if available, otherwise null"
}

Rules:
- Output ONLY the JSON object — no extra text or markdown code fences
- Set undetermined fields to null
- citation_type must be one of the listed values
- ALL extracted text values (title, authors, source, etc.) MUST be in the SAME LANGUAGE as the source document\
"""

_MATCH_SYSTEM = """\
You are an academic citation matching assistant.
The user provides:
1. A list of documents (each with an id, filename, and optionally a known title).
2. A block of citation text containing one or more citation entries.

Your task:
- Parse each citation entry in the text block.
- Match each parsed citation to the most likely document from the document list.
- For each successfully matched document, return structured citation fields.

Return a JSON array (one object per matched document):
[
  {
    "doc_id": <integer id from the document list>,
    "title": "Full title",
    "authors": ["Author Name", ...],
    "year": <integer or null>,
    "citation_type": "article|book|chapter|thesis|conference|website|other",
    "source": "Journal/book/conference/website name or null",
    "volume": "volume string or null",
    "issue": "issue string or null",
    "pages": "page range or null",
    "publisher": "publisher name or null",
    "doi": "DOI or null",
    "isbn": "ISBN or null",
    "url": "URL or null"
  },
  ...
]

Rules:
- Output ONLY the JSON array — no extra text or markdown code fences
- Only include documents that have a confident match in the citation text
- Set unknown fields to null
- citation_type must be one of: article, book, chapter, thesis, conference, website, other\
"""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def extract_one_doc(doc_id: int, model_id: int) -> dict:
    """Extract citation for a single document in an isolated DB session.

    Designed to be called from ``asyncio.to_thread`` so that each blocking
    LLM call runs in its own thread with its own session — no shared state.

    Returns a result dict::
        {"status": "done"}
        {"status": "error", "message": "..."}
    """
    from database import SessionLocal
    db = SessionLocal()
    try:
        doc = db.get(DocumentFile, doc_id)
        if not doc:
            return {"status": "error", "message": "Document not found"}

        ai_model = (
            db.query(AIModel)
            .options(joinedload(AIModel.provider))
            .filter(AIModel.id == model_id)
            .first()
        )
        if not ai_model:
            return {"status": "error", "message": "AI model not found"}

        try:
            raw_text = parse_file(doc.file_path)
        except Exception as exc:
            return {"status": "error", "message": f"Parse error: {exc}"}

        snippet = raw_text[:_SNIPPET_CHARS].strip()
        if not snippet:
            return {"status": "error", "message": "No text content in document"}

        from providers.chat import build_llm
        from auxmodels.rate_limiter import acquire
        try:
            llm = build_llm(ai_model)
        except ValueError as exc:
            return {"status": "error", "message": str(exc)}

        acquire(ai_model.id, ai_model.qps or 0)
        response = llm.invoke([
            SystemMessage(content=_EXTRACT_SYSTEM),
            HumanMessage(
                content=f"文件名：{doc.original_filename}\n\n文档内容（前两页）：\n{snippet}"
            ),
        ])
        data = _parse_json_object(response.content)
        if data:
            _upsert_citation(doc, data, db)
            db.commit()

        return {"status": "done"}
    except Exception as exc:
        logger.warning("extract_one_doc: doc %d failed — %s", doc_id, exc)
        return {"status": "error", "message": str(exc)}
    finally:
        db.close()


def match_citations_from_text(
    kb_id: int,
    doc_ids: list[int],
    citation_text: str,
    db: Session,
) -> list[DocumentFile]:
    """Match a user-pasted citation block to the selected documents using AI.

    The LLM is given the document list and the raw citation text; it returns a
    JSON array mapping each matched document to its structured citation fields.

    Returns the list of DocumentFile objects (refreshed after commit).
    Raises ValueError on model misconfiguration or LLM failure.
    """
    ai_model = _load_model(db)
    if ai_model is None:
        raise ValueError("未配置信息提取模型，请先在设置中配置 info_extract_model_id")

    docs = (
        db.query(DocumentFile)
        .filter(DocumentFile.knowledge_base_id == kb_id, DocumentFile.id.in_(doc_ids))
        .options(joinedload(DocumentFile.citation))
        .all()
    )

    # Build the document list context for the LLM
    doc_list: list[dict] = []
    for doc in docs:
        entry: dict = {"id": doc.id, "filename": doc.original_filename}
        if doc.citation and doc.citation.title:
            entry["known_title"] = doc.citation.title
        doc_list.append(entry)

    user_msg = (
        f"文档列表：\n{json.dumps(doc_list, ensure_ascii=False, indent=2)}\n\n"
        f"引文文本：\n{citation_text.strip()}"
    )

    from providers.chat import build_llm

    try:
        llm = build_llm(ai_model)
    except ValueError as exc:
        raise ValueError(f"无法加载 AI 模型: {exc}") from exc

    try:
        from auxmodels.rate_limiter import acquire
        acquire(ai_model.id, ai_model.qps or 0)
        response = llm.invoke([
            SystemMessage(content=_MATCH_SYSTEM),
            HumanMessage(content=user_msg),
        ])
        matches = _parse_json_array(response.content)
    except Exception as exc:
        logger.error("citation_ai: text matching failed — %s", exc)
        raise ValueError(f"AI 匹配引文失败: {exc}") from exc

    doc_map = {doc.id: doc for doc in docs}
    for match in matches:
        doc_id = match.get("doc_id")
        if not isinstance(doc_id, int) or doc_id not in doc_map:
            continue
        _upsert_citation(doc_map[doc_id], match, db)

    db.commit()
    return docs


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _load_model(db: Session) -> Optional[AIModel]:
    """Load the configured info-extraction AI model, or None if not set."""
    row = db.get(Setting, "info_extract_model_id")
    value = row.value if row else ""
    if not value:
        return None
    try:
        model_id = int(value)
    except (ValueError, TypeError):
        return None

    return (
        db.query(AIModel)
        .options(joinedload(AIModel.provider))
        .filter(AIModel.id == model_id)
        .first()
    )


def _upsert_citation(doc: DocumentFile, data: dict, db: Session) -> None:
    """Create or partially update the Citation record for *doc* using *data*."""
    fields: dict = {
        "citation_type": (
            data.get("citation_type")
            if data.get("citation_type") in _VALID_TYPES
            else "other"
        ),
        "title": data.get("title") or None,
        "authors": data.get("authors") if isinstance(data.get("authors"), list) else None,
        "year": _to_int(data.get("year")),
        "source": data.get("source") or None,
        "volume": str(data["volume"]) if data.get("volume") is not None else None,
        "issue": str(data["issue"]) if data.get("issue") is not None else None,
        "pages": data.get("pages") or None,
        "publisher": data.get("publisher") or None,
        "doi": data.get("doi") or None,
        "isbn": data.get("isbn") or None,
        "url": data.get("url") or None,
    }
    # Remove None values so existing data is not cleared
    fields = {k: v for k, v in fields.items() if v is not None}

    if doc.citation:
        for key, val in fields.items():
            setattr(doc.citation, key, val)
    else:
        citation = Citation(document_file_id=doc.id, **fields)
        db.add(citation)


def _to_int(value) -> Optional[int]:
    try:
        return int(value) if value is not None else None
    except (ValueError, TypeError):
        return None


def _strip_fences(text: str) -> str:
    """Remove markdown code fences if present."""
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text)
    return text.strip()


def _parse_json_object(text: str) -> dict:
    """Parse LLM response as a JSON object; return {} on failure."""
    text = _strip_fences(text)
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group())
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            pass
    logger.debug("citation_ai: no JSON object found in LLM response")
    return {}


def _parse_json_array(text: str) -> list[dict]:
    """Parse LLM response as a JSON array; return [] on failure."""
    text = _strip_fences(text)
    try:
        data = json.loads(text)
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]
        # Model may have wrapped the array in an object
        if isinstance(data, dict):
            for val in data.values():
                if isinstance(val, list):
                    return [item for item in val if isinstance(item, dict)]
    except json.JSONDecodeError:
        pass
    match = re.search(r"\[.*\]", text, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group())
            if isinstance(data, list):
                return [item for item in data if isinstance(item, dict)]
        except json.JSONDecodeError:
            pass
    logger.debug("citation_ai: no JSON array found in LLM response")
    return []
