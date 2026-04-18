"""Citation post-processing for RAG chat responses.

After the LLM finishes generating its answer, this module:
1. Replaces [CITE-N] inline markers with sequential [1], [2], … numbers.
2. Builds the formatted reference list from the document files that were
   actually retrieved during tool calls.
3. Returns a ``cite_map`` dict (``{"[CITE-1]": "[1]", …}``) so streaming
   clients can apply the substitution after the stream ends.

The reference numbering follows the order in which each distinct document
first appears in the ``retrieved`` list (i.e. retrieval order, not text order).
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from sqlalchemy.orm import Session

if TYPE_CHECKING:
    from chat.tools import RetrievedChunk


def build_rag_response(
    llm_text: str,
    retrieved: list["RetrievedChunk"],
    db: Session,
    citation_style: str = "apa",
    existing_references: list[dict] | None = None,
) -> tuple[str, list[dict], dict[str, str]]:
    """Post-process the LLM's final text and build the reference list.

    Parameters
    ----------
    llm_text:
        Raw text from the LLM (may contain ``[CITE-N]`` markers).
    retrieved:
        All chunks that were returned by the search tool in this session,
        in the order they were appended (populated by ``make_search_tool``).
    db:
        Active SQLAlchemy session for Citation lookup.
    citation_style:
        One of ``apa`` / ``mla`` / ``chicago`` / ``gb_t7714``.
    existing_references:
        References from previous turns. Used to continue numbering and
        reuse ref_nums for already-cited documents.

    Returns
    -------
    annotated_text : str
        The response with ``[CITE-N]`` replaced by ``[n]``.
    references : list[dict]
        Ordered reference dicts, each with:
        ``ref_num``, ``document_file_id``, ``original_filename``, ``formatted_citation``.
    cite_map : dict[str, str]
        Substitution table ``{"[CITE-1]": "[1]", …}`` for streaming clients.
    """
    from knowledge.documents.models import DocumentFile
    from knowledge.documents.citations import format_citation

    if not retrieved:
        return llm_text, [], {}

    # Build map of already-cited documents from previous turns
    existing_doc_to_refnum: dict[int, int] = {}
    next_refnum = 1
    if existing_references:
        for ref in existing_references:
            doc_id = ref.get("document_file_id")
            ref_num = ref.get("ref_num")
            if doc_id is not None and ref_num is not None:
                existing_doc_to_refnum[doc_id] = ref_num
                next_refnum = max(next_refnum, ref_num + 1)

    # Build unique document order (de-dup by document_file_id, first-seen)
    doc_order: list[int] = []
    seen_doc_ids: set[int] = set()
    for chunk in retrieved:
        if chunk.document_file_id not in seen_doc_ids:
            doc_order.append(chunk.document_file_id)
            seen_doc_ids.add(chunk.document_file_id)

    # Assign ref_nums: reuse existing for same doc, otherwise increment
    doc_to_refnum: dict[int, int] = {}
    for doc_id in doc_order:
        if doc_id in existing_doc_to_refnum:
            doc_to_refnum[doc_id] = existing_doc_to_refnum[doc_id]
        else:
            doc_to_refnum[doc_id] = next_refnum
            next_refnum += 1

    # cite_label → ref_num mapping  (one label → one document → one ref_num)
    label_to_chunk: dict[str, "RetrievedChunk"] = {}
    for chunk in retrieved:
        if chunk.cite_label not in label_to_chunk:
            label_to_chunk[chunk.cite_label] = chunk

    cite_map: dict[str, str] = {
        label: f"[{doc_to_refnum[chunk.document_file_id]}]"
        for label, chunk in label_to_chunk.items()
    }

    # Replace [CITE-N] and comma-separated [CITE-1, CITE-3] patterns in LLM text
    def _replace_multi(m: re.Match) -> str:
        individual = re.findall(r"CITE-(\d+)", m.group(0))
        return "".join(cite_map.get(f"[CITE-{n}]", f"[CITE-{n}]") for n in individual)

    annotated = re.sub(r"\[CITE-\d+(?:\s*,\s*CITE-\d+)*\]", _replace_multi, llm_text)

    # Build formatted reference list (all retrieved docs, in order)
    # Keep a single representative chunk per doc for filename fallback
    chunk_per_doc: dict[int, "RetrievedChunk"] = {}
    for chunk in retrieved:
        if chunk.document_file_id not in chunk_per_doc:
            chunk_per_doc[chunk.document_file_id] = chunk

    references: list[dict] = []
    for doc_id in doc_order:
        ref_num = doc_to_refnum[doc_id]
        rep_chunk = chunk_per_doc[doc_id]

        doc = db.query(DocumentFile).filter(DocumentFile.id == doc_id).first()

        formatted_citation: str = rep_chunk.original_filename  # safe fallback
        if doc and doc.citation:
            try:
                formatted_citation = format_citation(doc.citation, citation_style)
            except Exception:
                pass  # keep filename fallback

        references.append({
            "ref_num": ref_num,
            "document_file_id": doc_id,
            "original_filename": rep_chunk.original_filename,
            "formatted_citation": formatted_citation,
            "chunk_content": rep_chunk.content,
            "knowledge_base_id": rep_chunk.knowledge_base_id,
            "score": rep_chunk.score,
        })

    return annotated, references, cite_map
