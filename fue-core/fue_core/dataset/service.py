"""Public Dataset reading, with content-bound evidence and explicit scope."""
import hashlib
from fastapi import HTTPException
from knowledge.models import KnowledgeBase
from knowledge.documents.models import DocumentFile
from knowledge.chroma import get_chroma_client
from fue_core.dataset.retrieval import make_search_tool
from settings.service import setting


def libraries(db, allowed=None):
    query = db.query(KnowledgeBase)
    if allowed is not None:
        query = query.filter(KnowledgeBase.id.in_(allowed))
    return query.order_by(KnowledgeBase.id)


def scope(db, requested, allowed=None):
    available = [row.id for row in libraries(db, allowed)]
    selected = available if requested is None else requested
    if not set(selected) <= set(available):
        raise HTTPException(403, "Library is missing or outside this connection's scope")
    return selected


def document(db, doc_id, allowed=None):
    row = db.get(DocumentFile, doc_id)
    if row is None:
        raise HTTPException(404, "Document no longer exists")
    scope(db, [row.knowledge_base_id], allowed)
    return row


def evidence_id(doc, index, content):
    # A rebuild may invalidate evidence, but can never silently retarget it.
    revision = f"{doc.id}|{doc.file_path}|{doc.created_at}|{doc.indexed_at}|{index}|{content}"
    digest = hashlib.sha256(revision.encode()).hexdigest()
    return f"ev_{doc.id}_{index}_{digest}"


def search(db, query, kb_ids, mode, limit, allowed=None):
    selected = scope(db, kb_ids, allowed)
    if not selected:
        return {"items": [], "unindexed_documents": 0}
    keyword_only = setting(db, "knowledge_query_mode") == "keyword"
    if keyword_only:
        mode = "keyword"
    tool, chunks = make_search_tool(selected, db, raise_on_error=True, allow_rerank=not keyword_only)
    tool.invoke({"query": query, "mode": mode, "top_n": limit})
    items = []
    for chunk in chunks[:limit]:
        doc = document(db, chunk.document_file_id, allowed)
        items.append({"evidence_id": evidence_id(doc, chunk.chunk_index, chunk.content),
                      "document_id": doc.id, "library_id": doc.knowledge_base_id,
                      "filename": doc.original_filename, "chunk_index": chunk.chunk_index,
                      "preview": chunk.content[:350], "truncated": len(chunk.content) > 350,
                      "text_type": "indexed", "page": None})
    unindexed = db.query(DocumentFile).filter(DocumentFile.knowledge_base_id.in_(selected),
                                              DocumentFile.status != "indexed").count()
    return {"items": items, "unindexed_documents": unindexed}


def read(db, ref, before=0, after=0, offset=0, length=2000, allowed=None):
    try:
        prefix, doc_id, index, digest = ref.split("_")
        if prefix != "ev" or len(digest) != 64:
            raise ValueError()
        doc_id, index = int(doc_id), int(index)
    except ValueError:
        raise HTTPException(400, "Invalid evidence ID") from None
    doc = document(db, doc_id, allowed)
    kb = db.get(KnowledgeBase, doc.knowledge_base_id)
    try:
        raw = get_chroma_client().get_collection(kb.collection_name).get(
            where={"$and": [{"document_file_id": doc.id},
                             {"chunk_index": {"$gte": max(0, index-before)}},
                             {"chunk_index": {"$lte": index+after}}]},
            include=["documents", "metadatas"], limit=7)
    except Exception:
        raise HTTPException(409, "Source index is unavailable") from None
    rows = sorted(zip(raw["documents"], raw["metadatas"]), key=lambda r: r[1]["chunk_index"])
    center = next((content for content, meta in rows if meta["chunk_index"] == index), None)
    if center is None or evidence_id(doc, index, center) != ref:
        raise HTTPException(410, "Evidence expired after source change or deletion; search again")
    parts, positions, cursor = [], [], 0
    for content, meta in rows:
        part = f"chunk={meta['chunk_index']}\n{content}"
        positions.append((cursor, cursor+len(part), evidence_id(doc, meta['chunk_index'], content)))
        parts.append(part)
        cursor += len(part)+2
    full = "\n\n".join(parts)
    end = offset+length
    return {"document_id": doc.id, "text": full[offset:end], "text_type": "indexed", "page": None,
            "evidence_ids": [ref for start, stop, ref in positions if start < end and stop > offset],
            "next_offset": end if end < len(full) else None, "truncated": offset > 0 or end < len(full)}
