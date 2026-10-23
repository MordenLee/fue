"""API routes for Knowledge Base CRUD."""

import json
import logging
import re
from typing import Literal

from fastapi import APIRouter, Depends, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import Response
from sqlalchemy.orm import Session

from fue_core.database import get_db
from fue_core.knowledge.documents.models import DocumentFile
from fue_core.knowledge.models import (
    KBImportResult,
    KnowledgeBase,
    KnowledgeBaseCreate,
    KnowledgeBaseOut,
    KnowledgeBaseUpdate,
    SearchResult,
)
from fue_core.knowledge.documents.models import Citation
from fue_core.providers.models import AIModel

router = APIRouter(prefix="/api/knowledge-bases", tags=["knowledge-bases"])

logger = logging.getLogger(__name__)
COLLECTION_PREFIX = "kb_"
_KEYWORD_SPLIT_RE = re.compile(r"[\s\u3000]+")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_all_chunks_for_export(collection_name: str) -> dict:
    from fue_core.knowledge.chroma import get_all_chunks

    return get_all_chunks(collection_name)


def _get_collection(collection_name: str):
    from fue_core.knowledge.chroma import get_or_create_collection

    return get_or_create_collection(collection_name)


def _delete_collection_by_name(collection_name: str) -> None:
    from fue_core.knowledge.chroma import delete_collection

    delete_collection(collection_name)

def _validate_embed_model(db: Session, model_id: int) -> None:
    """Verify that the given model exists and is of type 'embedding'."""
    model = db.get(AIModel, model_id)
    if not model:
        raise HTTPException(status_code=404, detail="Embedding model not found")
    if model.model_type != "embedding":
        raise HTTPException(status_code=400, detail=f"Model type is '{model.model_type}', not an embedding model")


def _to_out(kb: KnowledgeBase) -> dict:
    """Convert ORM object to dict with computed document_count."""
    try:
        use_delim = kb.use_delimiter_split
    except Exception:
        use_delim = True
    return {
        "id": kb.id,
        "name": kb.name,
        "description": kb.description,
        "collection_name": kb.collection_name,
        "embed_model_id": kb.embed_model_id,
        "chunk_size": kb.chunk_size,
        "chunk_overlap": kb.chunk_overlap,
        "use_delimiter_split": use_delim if use_delim is not None else True,
        "rerank_model_id": kb.rerank_model_id,
        "folder_id": kb.folder_id,
        "created_at": kb.created_at,
        "updated_at": kb.updated_at,
        "document_count": len(kb.documents) if kb.documents else 0,
    }


def _get_kb(kb_id: int, db: Session) -> KnowledgeBase:
    kb = db.get(KnowledgeBase, kb_id)
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")
    return kb


def _get_citation_for_document(document_id: int, db: Session) -> dict | None:
    """Fetch citation info for a document if it exists."""
    citation = db.query(Citation).filter(Citation.document_file_id == document_id).first()
    if not citation:
        return None
    return {
        "citation_id": citation.id,
        "citation_title": citation.title,
        "citation_authors": citation.authors or [],
        "citation_year": citation.year,
    }


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
    distinct_hits, total_hits, first_pos = _keyword_match_stats(text, terms)
    return (-distinct_hits, -total_hits, first_pos, len(text))


# ============================= Knowledge Bases =============================

@router.get("", response_model=list[KnowledgeBaseOut])
def list_knowledge_bases(
    skip: int = Query(default=0, ge=0, description="跳过条数 / Offset"),
    limit: int = Query(default=50, ge=1, le=200, description="每页条数 / Page size"),
    db: Session = Depends(get_db),
):
    """List all knowledge bases / 列出所有知识库。"""
    kbs = db.query(KnowledgeBase).order_by(KnowledgeBase.created_at.desc()).offset(skip).limit(limit).all()
    return [_to_out(kb) for kb in kbs]


@router.post("", response_model=KnowledgeBaseOut, status_code=status.HTTP_201_CREATED)
def create_knowledge_base(
    payload: KnowledgeBaseCreate,
    db: Session = Depends(get_db),
):
    """Create a new knowledge base / 新建知识库。"""
    _validate_embed_model(db, payload.embed_model_id)

    record = KnowledgeBase(**payload.model_dump())
    db.add(record)
    db.flush()  # 获取 id，用于生成 collection_name
    record.collection_name = f"{COLLECTION_PREFIX}{record.id}"
    db.commit()
    db.refresh(record)
    return _to_out(record)


# ============================= Export / Import =============================
@router.get("/{kb_id}/export")
def export_knowledge_base(kb_id: int, db: Session = Depends(get_db)):
    from fue_core.knowledge.transfer import MAX_BYTES, export_package
    from fue_core.knowledge.chroma import get_chroma_client
    kb = _get_kb(kb_id, db)
    model = db.get(AIModel, kb.embed_model_id)
    if not model:
        raise HTTPException(409, "Embedding model no longer exists")
    client = get_chroma_client()
    # Do not create or mutate an index during export.
    names = {c.name for c in client.list_collections()}
    collection = client.get_collection(kb.collection_name) if kb.collection_name in names else None
    payload = export_package(kb, model, collection)
    content = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode('utf-8')
    if len(content) > MAX_BYTES:
        raise HTTPException(413, '知识库 JSON 超过 256 MiB，请拆分知识库后导出。')
    return Response(content=content,
                    media_type="application/json",
                    headers={"Content-Disposition": f'attachment; filename="fue-kb-{kb_id}.json"'})


@router.post("/import", response_model=KBImportResult, status_code=status.HTTP_201_CREATED)
def import_knowledge_base(
    file: UploadFile,
    embed_model_id: int = Form(...),
    kb_name: str | None = Form(default=None),
    confirm_unverified: bool = Form(default=False),
    db: Session = Depends(get_db),
):
    from fue_core.knowledge.transfer import MAX_BYTES, decode, import_package
    from fue_core.knowledge.chroma import get_chroma_client
    _validate_embed_model(db, embed_model_id)
    raw = file.file.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise HTTPException(413, "Knowledge-base JSON exceeds 256 MiB")
    package = decode(raw)
    kb, count = import_package(package, db.get(AIModel, embed_model_id), kb_name, db,
                               get_chroma_client(), confirm_unverified)
    warnings = []
    if not package.profile_verified:
        warnings.append("旧索引的模型来源由用户确认，未通过历史记录验证。")
    return KBImportResult(knowledge_base=KnowledgeBaseOut(**_to_out(kb)),
                          chunks_imported=count, documents_created=len(package.documents), warnings=warnings)


@router.get("/{kb_id}", response_model=KnowledgeBaseOut)
def get_knowledge_base(kb_id: int, db: Session = Depends(get_db)):
    """Get a single knowledge base / 获取知识库详情。"""
    return _to_out(_get_kb(kb_id, db))


@router.put("/{kb_id}", response_model=KnowledgeBaseOut)
def update_knowledge_base(
    kb_id: int,
    payload: KnowledgeBaseUpdate,
    db: Session = Depends(get_db),
):
    """Update knowledge base config (partial update) / 更新知识库配置。"""
    record = _get_kb(kb_id, db)
    if payload.embed_model_id is not None:
        _validate_embed_model(db, payload.embed_model_id)
        if payload.embed_model_id != record.embed_model_id and any(d.chunk_count for d in record.documents):
            from fue_core.knowledge.transfer import profile
            previous = db.get(AIModel, record.embed_model_id)
            if not previous or profile(previous) != profile(db.get(AIModel, payload.embed_model_id)):
                raise HTTPException(409, '现有索引与新嵌入模型不兼容，请新建知识库后重新索引。')
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(record, field, value)
    db.commit()
    db.refresh(record)
    return _to_out(record)


@router.delete("/{kb_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_knowledge_base(kb_id: int, db: Session = Depends(get_db)):
    """Delete a knowledge base and its ChromaDB collection / 删除知识库及其向量数据。"""
    record = _get_kb(kb_id, db)
    try:
        if record.collection_name:
            _delete_collection_by_name(record.collection_name)
    except Exception as exc:
        logger.warning("Failed to delete ChromaDB collection %s: %s", record.collection_name, exc)
    db.delete(record)
    db.commit()


# ============================= Search =============================

def _apply_diversity(results: list[SearchResult]) -> list[SearchResult]:
    """Keep only the highest-scoring chunk per document_id (diversity mode)."""
    seen: dict[int, SearchResult] = {}
    for r in results:
        if r.document_id not in seen or r.score > seen[r.document_id].score:
            seen[r.document_id] = r
    return sorted(seen.values(), key=lambda r: r.score, reverse=True)


def _keyword_search(collection, q: str, top_k: int) -> list[SearchResult]:
    """ChromaDB where_document keyword search.

    Strategy:
    1. Split whitespace-separated keywords.
    2. Retrieve candidates with OR matching when multiple keywords are given.
    3. Rank by keyword richness: more distinct keywords matched first,
       then by total occurrence count.

    Score field remains the match ratio for display purposes.
    Note: ChromaDB $contains is case-sensitive for filtering; ranking uses lower().
    """
    words = _split_keyword_terms(q)
    if not words:
        return []

    candidate_limit = max(top_k * 5, top_k)

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

    if not raw["ids"]:
        return []

    results: list[SearchResult] = []
    for doc_text, meta in zip(raw["documents"], raw["metadatas"]):
        distinct_hits, _total_hits, _first_pos = _keyword_match_stats(doc_text, words)
        if distinct_hits <= 0:
            continue
        results.append(
            SearchResult(
                document_id=meta["document_file_id"],
                original_filename=meta["original_filename"],
                chunk_index=meta["chunk_index"],
                content=doc_text,
                score=round(distinct_hits / len(words), 6),
            )
        )
    results.sort(key=lambda r: _keyword_sort_key(r.content, words))
    return results[:top_k]


@router.get("/{kb_id}/search", response_model=list[SearchResult])
def search_knowledge_base(
    kb_id: int,
    q: str = Query(..., min_length=1, description="查询文本 / Query text"),
    search_type: Literal["semantic", "keyword"] = Query(
        default="semantic",
        description="搜索模式：semantic=向量语义检索 / keyword=关键词检索",
    ),
    top_k: int = Query(
        default=None, ge=1, le=100,
        description="返回切片数，不传则使用知识库默认 top_k / Overrides KB default top_k",
    ),
    rerank: bool = Query(
        default=True,
        description="是否启用 Rerank（仅 semantic 模式，需知识库已配置 rerank_model_id）",
    ),
    diversity: bool = Query(
        default=False,
        description="多样性模式：每个文档仅保留匹配度最高的一个切片，确保结果来自不同文件",
    ),
    db: Session = Depends(get_db),
):
    """Search a knowledge base.

    **semantic**: vector similarity search.  The query is embedded using **the same model
    that was used during indexing** (``kb.embed_model_id``). This is enforced server-side
    and cannot be overridden by the caller — mixing models causes dimension mismatches or
    semantically wrong results.  Supports optional reranking.

    **keyword**: full-text substring search via ChromaDB ``$contains`` — no embedding
    call needed, useful while documents are still being indexed or for exact-term lookup.
    """
    kb = _get_kb(kb_id, db)
    if not kb.collection_name:
        return []

    from fue_core.settings.models import DEFAULTS, Setting
    query_mode = db.get(Setting, "knowledge_query_mode")
    if query_mode and query_mode.value == "keyword":
        search_type, rerank = "keyword", False
    if top_k is not None:
        effective_top_k = top_k
    else:
        row = db.get(Setting, "rag_top_k")
        effective_top_k = int(row.value) if row else int(DEFAULTS["rag_top_k"])
    collection = _get_collection(kb.collection_name)
    if collection.count() == 0:
        return []

    # ------------------------------------------------------------------
    # Keyword search path
    # ------------------------------------------------------------------
    if search_type == "keyword":
        results = _keyword_search(collection, q, effective_top_k)
        return _apply_diversity(results) if diversity else results

    # ------------------------------------------------------------------
    # Semantic search path
    # ------------------------------------------------------------------
    # Always use kb.embed_model_id — the exact model that generated the stored vectors.
    # A different model would produce wrong-dimension or semantically incompatible vectors.
    embed_model = db.get(AIModel, kb.embed_model_id)
    if not embed_model:
        raise HTTPException(
            status_code=409,
            detail=(
                "The embedding model linked to this knowledge base no longer exists. "
                "Please update the knowledge base to use a valid model and re-index all documents."
            ),
        )

    from fue_core.providers.embeddings import build_embedder
    try:
        embedder = build_embedder(embed_model)
        query_vector: list[float] = embedder.embed_query(q)
    except Exception as exc:
        logger.error("Embedding query failed: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=502,
            detail=f"嵌入模型调用失败，请检查供应商配置及网络连接：{exc}",
        )

    # Fetch extra candidates when reranking so the reranker has more to work with
    n_results = effective_top_k * 3 if (rerank and kb.rerank_model_id) else effective_top_k
    chroma_result = collection.query(
        query_embeddings=[query_vector],
        n_results=min(n_results, collection.count()),
        include=["documents", "metadatas", "distances"],
    )

    ids_list = chroma_result["ids"][0]
    docs_list = chroma_result["documents"][0]
    metas_list = chroma_result["metadatas"][0]
    distances = chroma_result["distances"][0]

    if not ids_list:
        return []

    # Optional rerank
    if rerank and kb.rerank_model_id:
        rerank_model = db.get(AIModel, kb.rerank_model_id)
        if rerank_model:
            from fue_core.providers.reranker import build_reranker
            try:
                reranker = build_reranker(rerank_model)
                ranked = reranker.rerank(query=q, documents=docs_list, top_n=effective_top_k)
            except Exception as exc:
                logger.error("Reranker call failed: %s", exc, exc_info=True)
                # Fall back to cosine-score results instead of failing the whole request
                ranked = None
            if ranked is not None:
                results = []
                for r in ranked:
                    doc_id = metas_list[r.index]["document_file_id"]
                    citation_info = _get_citation_for_document(doc_id, db)
                    result_data = {
                        "document_id": doc_id,
                        "original_filename": metas_list[r.index]["original_filename"],
                        "chunk_index": metas_list[r.index]["chunk_index"],
                        "content": r.document,
                        "score": r.score,
                    }
                    if citation_info:
                        result_data.update(citation_info)
                    results.append(SearchResult(**result_data))
                return _apply_diversity(results) if diversity else results

    # No rerank — cosine score ≈ 1 − distance (valid for L2 distances on normalised vectors)
    results = []
    for i in range(min(effective_top_k, len(ids_list))):
        doc_id = metas_list[i]["document_file_id"]
        citation_info = _get_citation_for_document(doc_id, db)
        result_data = {
            "document_id": doc_id,
            "original_filename": metas_list[i]["original_filename"],
            "chunk_index": metas_list[i]["chunk_index"],
            "content": docs_list[i],
            "score": round(1.0 - distances[i], 6),
        }
        if citation_info:
            result_data.update(citation_info)
        results.append(SearchResult(**result_data))
    results = sorted(results, key=lambda r: r.score, reverse=True)
    return _apply_diversity(results) if diversity else results
