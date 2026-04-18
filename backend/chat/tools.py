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
    score: float             # L2 / cosine distance — lower means more relevant


def make_search_tool(kb_ids: list[int], db: Session):
    """Create a knowledge-base search tool and a shared retrieved-chunks list.

    Returns
    -------
    tool : LangChain StructuredTool — bind to the LLM with ``llm.bind_tools([tool])``.
    retrieved : list[RetrievedChunk] — populated in-place on every tool invocation.
    """
    retrieved: list[RetrievedChunk] = []
    _cite_counter = [0]  # mutable so the closure can increment it

    @tool
    def search_knowledge_base(
        query: str,
        mode: str = "vector",
        top_n: int = 0,
    ) -> str:
        """Search the knowledge base for document chunks relevant to the query.

        Use this tool whenever you need factual information from the knowledge
        base. Include the [CITE-N] marker from each result immediately after
        any statement that is based on that chunk.

        Call this tool again with a different query or mode when the user asks
        follow-up questions such as "what else mentions X?" or "find more studies
        about Y?" to retrieve fresh results.

        Args:
            query: Natural-language query describing the information needed.
            mode:  Search strategy — one of:
                   "vector"  (default) semantic / embedding similarity search,
                             best for conceptual or paraphrased questions;
                   "keyword" exact-word match, best when the user mentions
                             specific terms, names, or codes;
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
                    words = [w for w in q.strip().split() if w]
                    if not words:
                        return []
                    where_doc = (
                        {"$contains": words[0]}
                        if len(words) == 1
                        else {"$and": [{"$contains": w} for w in words]}
                    )
                    raw = collection.get(
                        where_document=where_doc,
                        include=["documents", "metadatas"],
                        limit=k,
                    )
                    if not raw["ids"] and len(words) > 1:
                        where_doc = {"$or": [{"$contains": w} for w in words]}
                        raw = collection.get(
                            where_document=where_doc,
                            include=["documents", "metadatas"],
                            limit=k,
                        )
                    out = []
                    for doc_text, meta in zip(raw["documents"], raw["metadatas"]):
                        doc_lower = doc_text.lower()
                        matched = sum(1 for w in words if w.lower() in doc_lower)
                        out.append(RetrievedChunk(
                            cite_label="",
                            document_file_id=int(meta.get("document_file_id", 0)),
                            chunk_index=int(meta.get("chunk_index", 0)),
                            original_filename=meta.get("original_filename", "unknown"),
                            knowledge_base_id=kb_id,
                            content=doc_text,
                            score=round(matched / len(words), 6),
                        ))
                    return out

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
                    kw_chunks  = _keyword(query, effective_k)
                    # merge by content dedup, prefer vector ordering
                    seen: set[str] = set()
                    kb_chunks = []
                    for c in vec_chunks + kw_chunks:
                        if c.content not in seen:
                            seen.add(c.content)
                            kb_chunks.append(c)
                    kb_chunks = kb_chunks[:effective_k]
                else:
                    kb_chunks = _vector(query, effective_k)

                raw_chunks.extend(kb_chunks)

            except Exception as exc:
                logger.warning("RAG: search failed for KB %d: %s", kb_id, exc)
                continue

        if not raw_chunks:
            return "No relevant information found in the knowledge base."

        # Optional reranking (uses the first KB that has a rerank model)
        raw_chunks = _maybe_rerank(query, raw_chunks, kb_ids, db)

        # Assign sequential cite labels and register in the shared list
        parts: list[str] = []
        for chunk in raw_chunks:
            _cite_counter[0] += 1
            chunk.cite_label = f"[CITE-{_cite_counter[0]}]"
            retrieved.append(chunk)
            parts.append(
                f"{chunk.cite_label} "
                f"(file: {chunk.original_filename}, paragraph {chunk.chunk_index + 1})\n"
                f"{chunk.content}"
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
        return sorted(chunks, key=lambda c: c.score)

    rerank_model = db.query(AIModel).filter(AIModel.id == rerank_model_id).first()
    if not rerank_model:
        return sorted(chunks, key=lambda c: c.score)

    try:
        reranker = build_reranker(rerank_model)
        ranked = reranker.rerank(query, [c.content for c in chunks])
        return [chunks[r.index] for r in ranked]
    except Exception as exc:
        logger.warning("RAG rerank failed: %s — using distance order", exc)
        return sorted(chunks, key=lambda c: c.score)
