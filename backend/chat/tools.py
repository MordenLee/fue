"""LangChain function-call tool for knowledge-base retrieval during RAG chat.

Usage
-----
    search_tool, retrieved = make_search_tool(kb_ids=[1, 2], db=db_session)
    llm_with_tools = llm.bind_tools([search_tool])

    # After the agentic loop, ``retrieved`` holds every chunk the tool returned.
    # Each chunk carries a ``cite_label`` like "[CITE-1]" that the LLM is
    # instructed to embed inline.  Post-process with chat.citations.build_rag_response.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from langchain_core.tools import tool
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


@dataclass
class RetrievedChunk:
    """One document chunk returned by the search tool."""

    cite_label: str          # "[CITE-1]", "[CITE-2]", …
    document_file_id: int
    chunk_index: int
    original_filename: str
    knowledge_base_id: int
    content: str
    score: float             # Vector: lower is better; keyword: higher is better


_KEYWORD_SPLIT_RE = re.compile(r"[\s\u3000]+")


def _split_keyword_terms(query: str) -> list[str]:
    """Split a keyword query on whitespace and remove case-insensitive duplicates."""
    terms: list[str] = []
    seen: set[str] = set()
    for raw in _KEYWORD_SPLIT_RE.split(query.strip()):
        term = raw.strip()
        if not term:
            continue
        lowered = term.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        terms.append(term)
    return terms


def _keyword_match_stats(text: str, terms: list[str]) -> tuple[int, int, int]:
    """Return (distinct_terms_matched, total_occurrences, first_match_pos)."""
    lowered_text = text.lower()
    distinct_hits = 0
    total_hits = 0
    first_pos = len(lowered_text)

    for term in terms:
        lowered_term = term.lower()
        hits = lowered_text.count(lowered_term)
        if hits <= 0:
            continue
        distinct_hits += 1
        total_hits += hits
        pos = lowered_text.find(lowered_term)
        if pos >= 0:
            first_pos = min(first_pos, pos)

    return distinct_hits, total_hits, first_pos


def _keyword_sort_key(text: str, terms: list[str]) -> tuple[int, int, int, int]:
    """Sort richer keyword matches first: more distinct terms, then more hits."""
    distinct_hits, total_hits, first_pos = _keyword_match_stats(text, terms)
    return (-distinct_hits, -total_hits, first_pos, len(text))


def make_search_tool(kb_ids: list[int], db: Session, initial_cite_num: int = 1):
    """Create a knowledge-base search tool and a shared retrieved-chunks list.

    Parameters
    ----------
    kb_ids:
        Knowledge base IDs to search.
    db:
        Active SQLAlchemy session.
    initial_cite_num:
        The first CITE-N number to assign.  Pass ``max(existing_ref_nums) + 1``
        so that chunk numbers are globally unique across conversation turns.

    Returns
    -------
    tool : LangChain StructuredTool — bind to the LLM with ``llm.bind_tools([tool])``.
    retrieved : list[RetrievedChunk] — populated in-place on every tool invocation.
    """
    retrieved: list[RetrievedChunk] = []
    _cite_counter = [initial_cite_num - 1]  # incremented before use, so first label = initial_cite_num

    @tool
    def search_knowledge_base(
        query: str,
        mode: str = "vector",
        top_n: int = 0,
    ) -> str:
        """Search the knowledge base for document chunks relevant to the query.

        Call this tool ONCE per user question with the most relevant query.
        Include the [CITE-N] marker from each result immediately after
        any statement that is based on that chunk.
        After receiving the results, synthesize a complete answer — do NOT
        call this tool again in the same turn.

        Args:
            query: Natural-language query describing the information needed.
            mode:  Search strategy — one of:
                   "vector"  (default) semantic / embedding similarity search,
                             best for conceptual or paraphrased questions;
                   "keyword" exact-word match with whitespace-separated keyword
                             support, best when the user mentions specific
                             terms, names, or codes;
                   "hybrid"  run both and merge results, use when unsure.
            top_n: Number of chunks to retrieve (1–50). Use 0 to apply the
                   global default. Increase (e.g. 10–20) for broad surveys
                   ("what research covers X?"); decrease (e.g. 3) for focused
                   factual lookups.
        """
        from knowledge.chroma import get_chroma_client
        from knowledge.models import KnowledgeBase
        from providers.embeddings import build_embedder
        from providers.models import AIModel
        from settings.models import DEFAULTS, Setting

        # Resolve effective top_k
        _row = db.get(Setting, "rag_top_k")
        _default_k = int(_row.value) if _row else int(DEFAULTS["rag_top_k"])
        effective_k = max(1, min(top_n, 50)) if top_n and top_n > 0 else _default_k
        _kw_floor_row = db.get(Setting, "hybrid_keyword_floor_top_k")
        hybrid_kw_floor = int(_kw_floor_row.value) if _kw_floor_row else int(DEFAULTS["hybrid_keyword_floor_top_k"])
        hybrid_kw_floor = max(1, min(hybrid_kw_floor, 100))

        if mode not in ("vector", "keyword", "hybrid"):
            mode = "vector"

        raw_chunks: list[RetrievedChunk] = []

        for kb_id in kb_ids:
            kb = db.get(KnowledgeBase, kb_id)
            if not kb or not kb.collection_name:
                logger.warning("RAG: KB %d not found or missing collection", kb_id)
                continue

            try:
                client = get_chroma_client()
                try:
                    collection = client.get_collection(kb.collection_name)
                except ValueError:
                    logger.warning("RAG: collection %s not in ChromaDB", kb.collection_name)
                    continue

                coll_size = collection.count()
                if coll_size == 0:
                    continue

                # ---- keyword search helper --------------------------------
                def _keyword(q: str, k: int) -> list[RetrievedChunk]:
                    words = _split_keyword_terms(q)
                    if not words:
                        return []

                    candidate_limit = min(max(k * 5, k), coll_size)
                    where_doc = (
                        {"$contains": words[0]}
                        if len(words) == 1
                        else {"$or": [{"$contains": w} for w in words]}
                    )
                    raw = collection.get(
                        where_document=where_doc,
                        include=["documents", "metadatas"],
                        limit=candidate_limit,
                    )

                    out = []
                    for doc_text, meta in zip(raw["documents"], raw["metadatas"]):
                        distinct_hits, total_hits, _first_pos = _keyword_match_stats(doc_text, words)
                        if distinct_hits <= 0:
                            continue
                        out.append(RetrievedChunk(
                            cite_label="",
                            document_file_id=int(meta.get("document_file_id", 0)),
                            chunk_index=int(meta.get("chunk_index", 0)),
                            original_filename=meta.get("original_filename", "unknown"),
                            knowledge_base_id=kb_id,
                            content=doc_text,
                            score=round(distinct_hits / len(words), 6),
                        ))
                    out.sort(key=lambda chunk: _keyword_sort_key(chunk.content, words))
                    return out[:k]

                # ---- vector search helper ---------------------------------
                def _vector(q: str, k: int) -> list[RetrievedChunk]:
                    embed_model = (
                        db.query(AIModel)
                        .filter(AIModel.id == kb.embed_model_id)
                        .first()
                    )
                    if not embed_model:
                        logger.warning("RAG: embedding model not found for KB %d", kb_id)
                        return []
                    try:
                        embedder = build_embedder(embed_model)
                        query_vec = embedder.embed_query(q)
                    except Exception as exc:
                        logger.warning("RAG: embedding failed for KB %d: %s", kb_id, exc)
                        return []
                    n = min(k, coll_size)
                    results = collection.query(
                        query_embeddings=[query_vec],
                        n_results=n,
                        include=["documents", "metadatas", "distances"],
                    )
                    return [
                        RetrievedChunk(
                            cite_label="",
                            document_file_id=int(meta.get("document_file_id", 0)),
                            chunk_index=int(meta.get("chunk_index", 0)),
                            original_filename=meta.get("original_filename", "unknown"),
                            knowledge_base_id=kb_id,
                            content=doc,
                            score=float(dist),
                        )
                        for doc, meta, dist in zip(
                            results["documents"][0],
                            results["metadatas"][0],
                            results["distances"][0],
                        )
                    ]

                # ---- dispatch --------------------------------------------
                if mode == "keyword":
                    kb_chunks = _keyword(query, effective_k)
                elif mode == "hybrid":
                    vec_chunks = _vector(query, effective_k)
                    kw_chunks  = _keyword(query, hybrid_kw_floor)
                    # Keep vector hits, then guarantee a keyword budget in hybrid mode.
                    seen: set[str] = set()
                    kb_chunks = []
                    for c in vec_chunks:
                        if c.content not in seen:
                            seen.add(c.content)
                            kb_chunks.append(c)
                    kw_added = 0
                    for c in kw_chunks:
                        if c.content in seen:
                            continue
                        seen.add(c.content)
                        kb_chunks.append(c)
                        kw_added += 1
                        if kw_added >= hybrid_kw_floor:
                            break
                else:
                    kb_chunks = _vector(query, effective_k)

                raw_chunks.extend(kb_chunks)

            except Exception as exc:
                logger.warning("RAG: search failed for KB %d: %s", kb_id, exc)
                continue

        if not raw_chunks:
            return "No relevant information found in the knowledge base."

        if mode == "keyword":
            terms = _split_keyword_terms(query)
            raw_chunks.sort(key=lambda chunk: _keyword_sort_key(chunk.content, terms))
            raw_chunks = raw_chunks[:effective_k]

        # Optional reranking (uses the first KB that has a rerank model)
        raw_chunks = _maybe_rerank(
            query,
            raw_chunks,
            kb_ids,
            db,
            preserve_order=mode in ("keyword", "hybrid"),
        )

        # Global cap: hybrid mode has a larger cap so keyword floor can take effect.
        final_cap = effective_k + hybrid_kw_floor if mode == "hybrid" else effective_k
        raw_chunks = raw_chunks[:final_cap]

        # Max chars per chunk to prevent a single oversized document chunk from
        # flooding the LLM context. ~1200 chars ≈ 600 tokens, enough for meaning.
        _MAX_CHUNK_CHARS = 1200

        # Assign sequential cite labels and register in the shared list
        parts: list[str] = []
        for chunk in raw_chunks:
            _cite_counter[0] += 1
            chunk.cite_label = f"[CITE-{_cite_counter[0]}]"
            retrieved.append(chunk)
            display_content = chunk.content[:_MAX_CHUNK_CHARS]
            if len(chunk.content) > _MAX_CHUNK_CHARS:
                display_content += "…[truncated]"
            parts.append(
                f"{chunk.cite_label} "
                f"(file: {chunk.original_filename}, paragraph {chunk.chunk_index + 1})\n"
                f"{display_content}"
            )

        return "\n\n---\n\n".join(parts)

    return search_knowledge_base, retrieved


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _maybe_rerank(
    query: str,
    chunks: list[RetrievedChunk],
    kb_ids: list[int],
    db: Session,
    preserve_order: bool = False,
) -> list[RetrievedChunk]:
    """Apply reranking if any KB has a rerank_model_id configured."""
    from knowledge.models import KnowledgeBase
    from providers.models import AIModel
    from providers.reranker import build_reranker

    rerank_model_id: int | None = None
    for kb_id in kb_ids:
        kb = db.get(KnowledgeBase, kb_id)
        if kb and kb.rerank_model_id:
            rerank_model_id = kb.rerank_model_id
            break

    if rerank_model_id is None:
        if preserve_order:
            return chunks
        return sorted(chunks, key=lambda c: c.score)

    rerank_model = db.query(AIModel).filter(AIModel.id == rerank_model_id).first()
    if not rerank_model:
        if preserve_order:
            return chunks
        return sorted(chunks, key=lambda c: c.score)

    try:
        reranker = build_reranker(rerank_model)
        ranked = reranker.rerank(query, [c.content for c in chunks], top_n=len(chunks))
        return [chunks[r.index] for r in ranked]
    except Exception as exc:
        logger.warning("RAG rerank failed: %s — using distance order", exc)
        if preserve_order:
            return chunks
        return sorted(chunks, key=lambda c: c.score)
