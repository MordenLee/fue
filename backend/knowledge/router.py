"""API routes for Knowledge Base CRUD."""

import json
import logging
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import Response
from sqlalchemy.orm import Session

from database import get_db
from knowledge.documents.models import DocumentFile
from knowledge.models import (
    KBImportResult,
    KnowledgeBase,
    KnowledgeBaseCreate,
    KnowledgeBaseOut,
    KnowledgeBaseUpdate,
    SearchResult,
)
from knowledge.documents.models import Citation
from providers.models import AIModel

router = APIRouter(prefix="/api/knowledge-bases", tags=["knowledge-bases"])

logger = logging.getLogger(__name__)
COLLECTION_PREFIX = "kb_"
_KEYWORD_SPLIT_RE = re.compile(r"[\s\u3000]+")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_all_chunks_for_export(collection_name: str) -> dict:
    from knowledge.chroma import get_all_chunks

    return get_all_chunks(collection_name)


def _get_collection(collection_name: str):
    from knowledge.chroma import get_or_create_collection

    return get_or_create_collection(collection_name)


def _delete_collection_by_name(collection_name: str) -> None:
    from knowledge.chroma import delete_collection

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
    """Export a knowledge base (metadata + all chunk vectors) as a downloadable JSON file.
    导出知识库（元数据 + 所有切片向量）为 JSON 文件。"""
    kb = _get_kb(kb_id, db)

    embed_model = db.get(AIModel, kb.embed_model_id)
    if not embed_model:
        raise HTTPException(
            status_code=409,
            detail="The embedding model linked to this knowledge base no longer exists. Re-link a valid model first.",
        )

    raw = _get_all_chunks_for_export(kb.collection_name or "")
    ids_list   = raw.get("ids") or []
    docs_list  = raw.get("documents") or []
    metas_list = raw.get("metadatas") or []
    embs_list  = raw.get("embeddings") or []

    chunks = [
        {
            "chroma_id":         chroma_id,
            "original_filename": meta.get("original_filename", ""),
            "chunk_index":       meta.get("chunk_index", i),
            "content":           content,
            "embedding":         emb,
        }
        for i, (chroma_id, content, meta, emb)
        in enumerate(zip(ids_list, docs_list, metas_list, embs_list))
    ]

    payload = {
        "format_version": "1.0",
        "exported_at":    datetime.now(timezone.utc).isoformat(),
        "kb_name":        kb.name,
        "kb_description": kb.description,
        "chunk_size":     kb.chunk_size,
        "chunk_overlap":  kb.chunk_overlap,
        "embed_model_info": {
            "api_name":       embed_model.api_name,
            "interface_type": embed_model.provider.interface_type,
            "display_name":   embed_model.display_name,
        },
        "chunks": chunks,
    }

    safe_name = kb.name.replace(" ", "_")[:40]
    filename = f"kb_{kb_id}_{safe_name}.json"
    return Response(
        content=json.dumps(payload, ensure_ascii=False),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/import", response_model=KBImportResult, status_code=status.HTTP_201_CREATED)
async def import_knowledge_base(
    file: UploadFile,
    embed_model_id: int = Form(..., description="本地 embedding 模型 ID，应与导出时使用的模型一致"),
    kb_name: str | None = Form(default=None, description="覆盖导入后知识库名称（留空则使用原名）"),
    db: Session = Depends(get_db),
):
    """Import a previously exported knowledge base from a JSON file.

    The caller must specify which of their local embedding models corresponds to
    the one used during export.  The server enforces that the model type is
    'embedding' and warns when the ``api_name`` differs from the exported value
    (which would indicate potentially incompatible vector spaces).

    Pre-computed vectors are inserted directly into ChromaDB — no re-embedding.
    """
    # 1. Validate target embedding model
    embed_model = db.get(AIModel, embed_model_id)
    if not embed_model:
        raise HTTPException(status_code=404, detail="Embedding model not found")
    if embed_model.model_type != "embedding":
        raise HTTPException(
            status_code=400,
            detail=f"Model type is '{embed_model.model_type}', not an embedding model",
        )

    # 2. Parse JSON file
    raw_bytes = await file.read()
    try:
        data = json.loads(raw_bytes)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid JSON: {exc}")

    if data.get("format_version") != "1.0":
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported export format version: {data.get('format_version')!r}",
        )

    # 3. Model compatibility check (soft — warn only, do not block)
    warnings: list[str] = []
    exported_info = data.get("embed_model_info", {})
    if exported_info.get("api_name") != embed_model.api_name:
        warnings.append(
            f"Model mismatch: file was exported with '{exported_info.get('api_name')}' "
            f"but you selected '{embed_model.api_name}'. "
            "Search results will be incorrect if these models produce incompatible vector spaces."
        )

    # 4. Validate chunks
    chunks: list[dict] = data.get("chunks", [])
    if not chunks:
        raise HTTPException(status_code=400, detail="Export file contains no chunks")

    dims = {len(c["embedding"]) for c in chunks if isinstance(c.get("embedding"), list)}
    if not dims:
        raise HTTPException(status_code=400, detail="Chunks are missing embedding vectors")
    if len(dims) > 1:
        raise HTTPException(
            status_code=400,
            detail=f"Inconsistent embedding dimensions in export file: {dims}",
        )

    # 5. Create KnowledgeBase record
    new_name = (kb_name or "").strip() or data.get("kb_name", "Imported KB")
    kb = KnowledgeBase(
        name=new_name,
        description=data.get("kb_description"),
        embed_model_id=embed_model_id,
        chunk_size=int(data.get("chunk_size", 500)),
        chunk_overlap=int(data.get("chunk_overlap", 50)),
    )
    db.add(kb)
    db.flush()
    kb.collection_name = f"{COLLECTION_PREFIX}{kb.id}"
    db.flush()

    # 6. Create one DocumentFile per unique filename
    now = datetime.now(timezone.utc)
    file_chunks: dict[str, list[dict]] = defaultdict(list)
    for chunk in chunks:
        file_chunks[chunk.get("original_filename") or "unknown"].append(chunk)

    doc_map: dict[str, int] = {}  # original_filename → document_file_id
    for original_filename, fc_list in file_chunks.items():
        file_ext = Path(original_filename).suffix.lstrip(".") or "txt"
        doc = DocumentFile(
            knowledge_base_id=kb.id,
            original_filename=original_filename,
            file_path="<imported>",   # no file on disk
            file_type=file_ext,
            file_size=0,
            status="indexed",
            chunk_count=len(fc_list),
            indexed_at=now,
        )
        db.add(doc)
        db.flush()
        doc_map[original_filename] = doc.id

    db.commit()
    db.refresh(kb)

    # 7. Bulk-write chunks + pre-computed vectors into ChromaDB
    collection = _get_collection(kb.collection_name)
    chroma_ids:   list[str]         = []
    chroma_docs:  list[str]         = []
    chroma_embs:  list[list[float]] = []
    chroma_metas: list[dict]        = []

    for chunk in chunks:
        fn     = chunk.get("original_filename") or "unknown"
        doc_id = doc_map[fn]
        cidx   = int(chunk.get("chunk_index", 0))
        chroma_ids.append(f"imported_kb{kb.id}_doc{doc_id}_chunk{cidx}")
        chroma_docs.append(chunk.get("content") or "")
        chroma_embs.append(chunk["embedding"])
        chroma_metas.append({
            "document_file_id":  doc_id,
            "knowledge_base_id": kb.id,
            "original_filename": fn,
            "chunk_index":       cidx,
        })

    # ChromaDB recommends batching large inserts
    _BATCH = 500
    for i in range(0, len(chroma_ids), _BATCH):
        collection.add(
            ids=chroma_ids[i: i + _BATCH],
            embeddings=chroma_embs[i: i + _BATCH],
            documents=chroma_docs[i: i + _BATCH],
            metadatas=chroma_metas[i: i + _BATCH],
        )

    return KBImportResult(
        knowledge_base=KnowledgeBaseOut(**_to_out(kb)),
        chunks_imported=len(chroma_ids),
        documents_created=len(doc_map),
        warnings=warnings,
    )


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

    from settings.models import DEFAULTS, Setting
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

    from providers.embeddings import build_embedder
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
            from providers.reranker import build_reranker
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
