"""Citation post-processing for RAG chat responses.

After the LLM finishes generating its answer, this module:
1. Replaces [CITE-N] inline markers with sequential [1], [2], … numbers.
2. Builds the formatted reference list from the document files that were
   actually retrieved during tool calls.
3. Returns a ``cite_map`` dict (``{"[CITE-1]": "[1]", …}``) so streaming
   clients can apply the substitution after the stream ends.

The reference numbering follows chunk labels directly: ``[CITE-7]`` -> ``[7]``.
This keeps inline citation numbers fully consistent with retrieval chunk order.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from sqlalchemy.orm import Session

if TYPE_CHECKING:
    from chat.tools import RetrievedChunk


_CITE_MARKER_RE = re.compile(r"\[CITE-\d+(?:\s*[,，]\s*CITE-\d+)*\]", re.IGNORECASE)
_NUMERIC_REF_RE = re.compile(r"\[(\d+)\]")


def _extract_numeric_refs_in_order(text: str) -> list[int]:
    """Return unique numeric refs in first-appearance order."""
    seen: set[int] = set()
    ordered: list[int] = []
    for match in _NUMERIC_REF_RE.finditer(text):
        ref_num = int(match.group(1))
        if ref_num not in seen:
            seen.add(ref_num)
            ordered.append(ref_num)
    return ordered


def _extract_cite_labels_in_order(text: str) -> list[str]:
    """Return unique [CITE-N] labels in first-appearance order from raw LLM text."""
    seen: set[str] = set()
    ordered: list[str] = []
    for marker in _CITE_MARKER_RE.finditer(text):
        for n in re.findall(r"CITE-(\d+)", marker.group(0), flags=re.IGNORECASE):
            label = f"[CITE-{n}]"
            if label not in seen:
                seen.add(label)
                ordered.append(label)
    return ordered


def build_rag_response(
    llm_text: str,
    retrieved: list["RetrievedChunk"],
    db: Session,
    citation_style: str = "apa",
    citation_mode: str = "document",
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

    def _label_to_num(label: str) -> int | None:
        m = re.match(r"\[CITE-(\d+)\]", label, flags=re.IGNORECASE)
        return int(m.group(1)) if m else None

    # cite_label -> chunk mapping
    label_to_chunk: dict[str, "RetrievedChunk"] = {}
    for chunk in retrieved:
        if chunk.cite_label not in label_to_chunk:
            label_to_chunk[chunk.cite_label] = chunk

    # Only labels that actually appear in this answer should participate in
    # numbering. This keeps first-turn numbering contiguous.
    cited_labels_in_text = [
        label for label in _extract_cite_labels_in_order(llm_text)
        if label in label_to_chunk
    ]

    # Build map of already-cited documents from previous turns (document mode only)
    existing_doc_to_refnum: dict[int, int] = {}
    next_refnum = 1
    if existing_references:
        for ref in existing_references:
            doc_id = ref.get("document_file_id")
            ref_num = ref.get("ref_num")
            if isinstance(doc_id, int) and isinstance(ref_num, int):
                # Keep the earliest known number for one document to ensure
                # stable cross-turn numbering in document mode.
                if doc_id in existing_doc_to_refnum:
                    existing_doc_to_refnum[doc_id] = min(existing_doc_to_refnum[doc_id], ref_num)
                else:
                    existing_doc_to_refnum[doc_id] = ref_num
                next_refnum = max(next_refnum, ref_num + 1)

    doc_to_refnum: dict[int, int] = {}

    def _ensure_doc_refnum(doc_id: int) -> int:
        nonlocal next_refnum
        if doc_id in doc_to_refnum:
            return doc_to_refnum[doc_id]
        if doc_id in existing_doc_to_refnum:
            doc_to_refnum[doc_id] = existing_doc_to_refnum[doc_id]
        else:
            doc_to_refnum[doc_id] = next_refnum
            next_refnum += 1
        return doc_to_refnum[doc_id]

    cite_map: dict[str, str] = {}
    for label in cited_labels_in_text:
        chunk = label_to_chunk[label]
        if citation_mode == "chunk":
            label_num = _label_to_num(label)
            if label_num is not None:
                cite_map[label] = f"[{label_num}]"
        else:
            cite_map[label] = f"[{_ensure_doc_refnum(chunk.document_file_id)}]"

    # Replace [CITE-N] and comma-separated [CITE-1, CITE-3] patterns in LLM text.
    # Accept lowercase variants too because some models drift in casing.
    def _replace_multi(m: re.Match) -> str:
        individual = re.findall(r"CITE-(\d+)", m.group(0))
        return "".join(cite_map.get(f"[CITE-{n}]", f"[CITE-{n}]") for n in individual)

    annotated = _CITE_MARKER_RE.sub(_replace_multi, llm_text)

    # If the model omitted inline citations entirely but we do have retrieved
    # evidence, add a compact fallback citation cluster at the end so the answer
    # still exposes traceable sources instead of showing an uncited bibliography.
    cited_refnums = _extract_numeric_refs_in_order(annotated)
    if not cited_refnums and retrieved:
        if citation_mode == "chunk":
            fallback_refnums = sorted({
                n for n in (_label_to_num(c.cite_label) for c in retrieved[:3])
                if n is not None
            })
        else:
            doc_order: list[int] = []
            seen_doc_ids: set[int] = set()
            for chunk in retrieved:
                if chunk.document_file_id not in seen_doc_ids:
                    seen_doc_ids.add(chunk.document_file_id)
                    doc_order.append(chunk.document_file_id)
                if len(doc_order) >= 3:
                    break
            fallback_refnums = sorted({_ensure_doc_refnum(doc_id) for doc_id in doc_order})
        if fallback_refnums:
            suffix = "".join(f"[{ref_num}]" for ref_num in fallback_refnums)
            separator = "" if not annotated or annotated.endswith((" ", "\n")) else " "
            annotated = f"{annotated.rstrip()}{separator}{suffix}" if annotated.strip() else suffix
            cited_refnums = fallback_refnums

    references_by_num: dict[int, dict] = {}
    if citation_mode == "chunk":
        chunk_by_refnum: dict[int, "RetrievedChunk"] = {}
        for label, chunk in label_to_chunk.items():
            n = _label_to_num(label)
            if n is not None and n not in chunk_by_refnum:
                chunk_by_refnum[n] = chunk

        for ref_num in sorted(set(cited_refnums)):
            if ref_num not in chunk_by_refnum:
                continue
            rep_chunk = chunk_by_refnum[ref_num]
            doc_id = rep_chunk.document_file_id

            doc = db.query(DocumentFile).filter(DocumentFile.id == doc_id).first()

            formatted_citation: str = rep_chunk.original_filename  # safe fallback
            if doc and doc.citation:
                try:
                    formatted_citation = format_citation(doc.citation, citation_style)
                except Exception:
                    pass  # keep filename fallback

            references_by_num[ref_num] = {
                "ref_num": ref_num,
                "document_file_id": doc_id,
                "original_filename": rep_chunk.original_filename,
                "formatted_citation": formatted_citation,
                "chunk_index": rep_chunk.chunk_index,
                "chunk_content": rep_chunk.content,
                "knowledge_base_id": rep_chunk.knowledge_base_id,
                "score": rep_chunk.score,
                "chunks": [
                    {
                        "chunk_index": rep_chunk.chunk_index,
                        "chunk_content": rep_chunk.content,
                        "knowledge_base_id": rep_chunk.knowledge_base_id,
                        "score": rep_chunk.score,
                    }
                ],
            }
    else:
        chunks_per_doc: dict[int, list["RetrievedChunk"]] = {}
        for chunk in retrieved:
            chunks_per_doc.setdefault(chunk.document_file_id, []).append(chunk)

        deduped_chunks_per_doc: dict[int, list["RetrievedChunk"]] = {}
        for doc_id, doc_chunks in chunks_per_doc.items():
            seen_chunk_keys: set[tuple[int, str, int | float]] = set()
            unique_chunks: list["RetrievedChunk"] = []
            for chunk in doc_chunks:
                chunk_key = (chunk.chunk_index, chunk.content, chunk.score)
                if chunk_key in seen_chunk_keys:
                    continue
                seen_chunk_keys.add(chunk_key)
                unique_chunks.append(chunk)
            deduped_chunks_per_doc[doc_id] = unique_chunks

        for doc_id, ref_num in doc_to_refnum.items():
            if doc_id not in deduped_chunks_per_doc:
                continue
            doc_chunks = deduped_chunks_per_doc[doc_id]
            rep_chunk = doc_chunks[0]

            doc = db.query(DocumentFile).filter(DocumentFile.id == doc_id).first()

            formatted_citation: str = rep_chunk.original_filename
            if doc and doc.citation:
                try:
                    formatted_citation = format_citation(doc.citation, citation_style)
                except Exception:
                    pass

            references_by_num[ref_num] = {
                "ref_num": ref_num,
                "document_file_id": doc_id,
                "original_filename": rep_chunk.original_filename,
                "formatted_citation": formatted_citation,
                "chunk_index": rep_chunk.chunk_index,
                "chunk_content": rep_chunk.content,
                "knowledge_base_id": rep_chunk.knowledge_base_id,
                "score": rep_chunk.score,
                "chunks": [
                    {
                        "chunk_index": c.chunk_index,
                        "chunk_content": c.content,
                        "knowledge_base_id": c.knowledge_base_id,
                        "score": c.score,
                    }
                    for c in doc_chunks
                ],
            }

    # Also allow the current answer to reference citations from previous turns
    # by their existing numeric labels.
    if existing_references:
        for ref in existing_references:
            ref_num = ref.get("ref_num")
            if isinstance(ref_num, int) and ref_num not in references_by_num:
                references_by_num[ref_num] = {
                    "ref_num": ref_num,
                    "document_file_id": ref.get("document_file_id"),
                    "original_filename": ref.get("original_filename", ""),
                    "formatted_citation": ref.get("formatted_citation", ref.get("original_filename", "")),
                    "chunk_index": ref.get("chunk_index"),
                    "chunk_content": ref.get("chunk_content", ""),
                    "knowledge_base_id": ref.get("knowledge_base_id"),
                    "score": ref.get("score"),
                    "chunks": ref.get("chunks", []),
                }

    # Return only the references actually used in the answer, sorted ascending.
    if not cited_refnums:
        return annotated, [], cite_map

    references = [references_by_num[ref_num] for ref_num in sorted(cited_refnums) if ref_num in references_by_num]

    return annotated, references, cite_map
