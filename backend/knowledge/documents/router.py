"""API routes for Document and Citation management.

All routes are mounted under /api/knowledge-bases/{kb_id}/documents/...
"""

import asyncio
import json
import logging
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

logger = logging.getLogger(__name__)

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import SessionLocal, get_db
from knowledge.documents.citations import SUPPORTED_STYLES, format_citation
from knowledge.documents.models import (
    Citation,
    CitationCreate,
    CitationFormatted,
    CitationOut,
    CitationUpdate,
    DocumentFile,
    DocumentFileOut,
)
from knowledge.models import KnowledgeBase
from knowledge.parser import SUPPORTED_EXTENSIONS
from settings.models import DEFAULTS, Setting

router = APIRouter(prefix="/api/knowledge-bases", tags=["documents", "citations"])

def _get_index_max_workers_from_settings() -> int:
    """Read batch document-level indexing workers from settings (1-16)."""
    db = SessionLocal()
    try:
        row = db.get(Setting, "kb_index_max_workers")
        raw = row.value if row and row.value else DEFAULTS.get("kb_index_max_workers", "4")
        value = int(raw)
    except (ValueError, TypeError):
        value = 4
    finally:
        db.close()
    return max(1, min(value, 16))


class AddDocumentsRequest(BaseModel):
    paths: list[str]
    duplicate_action: str = "skip"  # "skip" | "reparse" | "add"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_kb(kb_id: int, db: Session) -> KnowledgeBase:
    kb = db.get(KnowledgeBase, kb_id)
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")
    return kb


def _get_doc(kb_id: int, doc_id: int, db: Session) -> DocumentFile:
    doc = db.get(DocumentFile, doc_id)
    if not doc or doc.knowledge_base_id != kb_id:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc


def _run_index_in_background(document_file_id: int) -> None:
    from knowledge.indexing import index_document

    db = SessionLocal()
    try:
        index_document(db, document_file_id)
    finally:
        db.close()


def _index_many_in_background(doc_ids: list[int]) -> None:
    """并行索引多个文档：每个文档在独立线程中运行，拥有各自的 DB session。"""
    workers = min(len(doc_ids), _get_index_max_workers_from_settings())
    with ThreadPoolExecutor(max_workers=workers) as pool:
        pool.map(_run_index_in_background, doc_ids)


def _delete_document_chunks(collection_name: str | None, document_file_id: int) -> None:
    if not collection_name:
        return

    from knowledge.chroma import delete_documents_by_file

    delete_documents_by_file(collection_name, document_file_id)


def _doc_to_out(doc: DocumentFile) -> DocumentFileOut:
    return DocumentFileOut(
        id=doc.id,
        knowledge_base_id=doc.knowledge_base_id,
        original_filename=doc.original_filename,
        file_type=doc.file_type,
        file_size=doc.file_size,
        status=doc.status,
        error_message=doc.error_message,
        chunk_count=doc.chunk_count,
        created_at=doc.created_at,
        indexed_at=doc.indexed_at,
        has_citation=doc.citation is not None,
    )


# ============================= Documents =============================

@router.get("/{kb_id}/documents", response_model=list[DocumentFileOut])
def list_documents(
    kb_id: int,
    skip: int = Query(default=0, ge=0, description="跳过条数 / Offset"),
    limit: int = Query(default=50, ge=1, le=200, description="每页条数 / Page size"),
    db: Session = Depends(get_db),
):
    """List all documents in a knowledge base / 列出知识库中的所有文档。"""
    _get_kb(kb_id, db)
    docs = (
        db.query(DocumentFile)
        .filter(DocumentFile.knowledge_base_id == kb_id)
        .order_by(DocumentFile.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return [_doc_to_out(d) for d in docs]


@router.post(
    "/{kb_id}/documents/batch",
    response_model=list[DocumentFileOut],
    status_code=status.HTTP_201_CREATED,
)
def batch_add_documents(
    kb_id: int,
    payload: AddDocumentsRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """通过本地文件路径批量添加文档并触发**并行**后台索引。

    所有记录创建完毕后立即返回（状态均为 pending），
    随后各文档在独立线程中同时执行
    解析 → 切分 → 向量化 → 写入 ChromaDB 的全流程。

    duplicate_action:
      - "skip":    跳过已存在的同名文件
      - "reparse": 删除旧文档并重新解析
      - "add":     不检查重复，直接添加
    """
    if not payload.paths:
        raise HTTPException(status_code=400, detail="No file paths provided")
    kb = _get_kb(kb_id, db)

    # Build lookup of existing filenames → doc records
    existing_docs: dict[str, DocumentFile] = {}
    if payload.duplicate_action != "add":
        for d in (
            db.query(DocumentFile)
            .filter(DocumentFile.knowledge_base_id == kb_id)
            .all()
        ):
            existing_docs[d.original_filename] = d

    docs: list[DocumentFile] = []
    reindex_ids: list[int] = []

    for file_path in payload.paths:
        p = Path(file_path)
        if not p.exists():
            raise HTTPException(status_code=400, detail=f"File not found: {file_path}")
        if not p.is_file():
            raise HTTPException(status_code=400, detail=f"Not a file: {file_path}")
        ext = p.suffix.lower()
        if ext not in SUPPORTED_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Unsupported file type '{ext}' for '{p.name}'. "
                    f"Supported: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
                ),
            )

        old_doc = existing_docs.get(p.name)

        if old_doc and payload.duplicate_action == "skip":
            # 跳过重复文件
            docs.append(old_doc)
            continue

        if old_doc and payload.duplicate_action == "reparse":
            # 删除旧 chunks，更新记录重新索引
            _delete_document_chunks(kb.collection_name, old_doc.id)
            old_doc.file_path = str(p.resolve())
            old_doc.file_size = p.stat().st_size
            old_doc.status = "pending"
            old_doc.error_message = None
            old_doc.chunk_count = 0
            old_doc.indexed_at = None
            old_doc.abstract = None
            docs.append(old_doc)
            reindex_ids.append(old_doc.id)
            continue

        # 新文档 (duplicate_action == "add" 或无重复)
        doc = DocumentFile(
            knowledge_base_id=kb_id,
            original_filename=p.name,
            file_path=str(p.resolve()),
            file_type=ext.lstrip("."),
            file_size=p.stat().st_size,
            status="pending",
        )
        db.add(doc)
        docs.append(doc)

    db.commit()
    for doc in docs:
        db.refresh(doc)

    # Collect all docs that need indexing (status == pending)
    index_ids = [doc.id for doc in docs if doc.status == "pending"]
    if index_ids:
        background_tasks.add_task(_index_many_in_background, index_ids)

    return [_doc_to_out(d) for d in docs]


class AddDocumentRequest(BaseModel):
    path: str


@router.post("/{kb_id}/documents", response_model=DocumentFileOut, status_code=status.HTTP_201_CREATED)
def add_document(
    kb_id: int,
    payload: AddDocumentRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """通过本地文件路径添加单个文档并触发后台索引。"""
    _get_kb(kb_id, db)

    p = Path(payload.path)
    if not p.exists():
        raise HTTPException(status_code=400, detail=f"File not found: {payload.path}")
    if not p.is_file():
        raise HTTPException(status_code=400, detail=f"Not a file: {payload.path}")
    ext = p.suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {ext}, supported: {', '.join(sorted(SUPPORTED_EXTENSIONS))}",
        )

    doc = DocumentFile(
        knowledge_base_id=kb_id,
        original_filename=p.name,
        file_path=str(p.resolve()),
        file_type=ext.lstrip("."),
        file_size=p.stat().st_size,
        status="pending",
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    background_tasks.add_task(_run_index_in_background, doc.id)
    return _doc_to_out(doc)


@router.get("/{kb_id}/documents/{doc_id}", response_model=DocumentFileOut)
def get_document(kb_id: int, doc_id: int, db: Session = Depends(get_db)):
    """Get a single document's status / 获取单个文档状态。"""
    _get_kb(kb_id, db)
    return _doc_to_out(_get_doc(kb_id, doc_id, db))


@router.post("/{kb_id}/documents/{doc_id}/reindex", response_model=DocumentFileOut)
def reindex_document(
    kb_id: int,
    doc_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """Re-index a document (clear old chunks, re-process) / 重新索引文档。"""
    kb = _get_kb(kb_id, db)
    doc = _get_doc(kb_id, doc_id, db)

    if kb.collection_name:
        _delete_document_chunks(kb.collection_name, doc.id)

    doc.status = "pending"
    doc.chunk_count = 0
    doc.error_message = None
    doc.indexed_at = None
    db.commit()
    db.refresh(doc)

    background_tasks.add_task(_run_index_in_background, doc.id)
    return _doc_to_out(doc)


_PROCESSING_STATUSES = {"pending", "parsing", "chunking", "cleaning", "embedding"}


@router.post("/{kb_id}/documents/{doc_id}/cancel", response_model=DocumentFileOut)
def cancel_document(kb_id: int, doc_id: int, db: Session = Depends(get_db)):
    """Cancel indexing of a document currently in progress / 取消正在处理的文档索引。"""
    doc = _get_doc(kb_id, doc_id, db)
    if doc.status not in _PROCESSING_STATUSES:
        raise HTTPException(status_code=400, detail="Document is not being processed")
    doc.status = "cancelled"
    doc.error_message = "Cancelled by user"
    db.commit()
    db.refresh(doc)
    return _doc_to_out(doc)


@router.delete("/{kb_id}/documents/{doc_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(kb_id: int, doc_id: int, db: Session = Depends(get_db)):
    """Delete a document and its chunks / 删除文档及其向量数据。"""
    kb = _get_kb(kb_id, db)
    doc = _get_doc(kb_id, doc_id, db)

    if kb.collection_name:
        _delete_document_chunks(kb.collection_name, doc.id)

    try:
        os.remove(doc.file_path)
    except OSError:
        pass

    db.delete(doc)
    db.commit()


class BatchDocIdsRequest(BaseModel):
    doc_ids: list[int]


@router.post("/{kb_id}/documents/batch-delete", status_code=status.HTTP_204_NO_CONTENT)
def batch_delete_documents(
    kb_id: int,
    payload: BatchDocIdsRequest,
    db: Session = Depends(get_db),
):
    """批量删除文档及其向量数据 / Batch delete documents and their chunks."""
    kb = _get_kb(kb_id, db)
    docs = (
        db.query(DocumentFile)
        .filter(DocumentFile.knowledge_base_id == kb_id, DocumentFile.id.in_(payload.doc_ids))
        .all()
    )
    for doc in docs:
        if kb.collection_name:
            _delete_document_chunks(kb.collection_name, doc.id)
        try:
            os.remove(doc.file_path)
        except OSError:
            pass
        db.delete(doc)
    db.commit()


@router.post(
    "/{kb_id}/documents/batch-reindex",
    response_model=list[DocumentFileOut],
)
def batch_reindex_documents(
    kb_id: int,
    payload: BatchDocIdsRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """批量重新索引文档 / Batch re-index documents."""
    kb = _get_kb(kb_id, db)
    docs = (
        db.query(DocumentFile)
        .filter(DocumentFile.knowledge_base_id == kb_id, DocumentFile.id.in_(payload.doc_ids))
        .all()
    )
    for doc in docs:
        if kb.collection_name:
            _delete_document_chunks(kb.collection_name, doc.id)
        doc.status = "pending"
        doc.chunk_count = 0
        doc.error_message = None
        doc.indexed_at = None
    db.commit()
    for doc in docs:
        db.refresh(doc)
    ids = [doc.id for doc in docs]
    if ids:
        background_tasks.add_task(_index_many_in_background, ids)
    return [_doc_to_out(d) for d in docs]


# ============================= Citations =============================

@router.get("/{kb_id}/documents/{doc_id}/citation", response_model=CitationOut)
def get_citation(kb_id: int, doc_id: int, db: Session = Depends(get_db)):
    """Get the citation metadata for a document / 获取文档的引用信息。"""
    _get_kb(kb_id, db)
    doc = _get_doc(kb_id, doc_id, db)
    if doc.citation is None:
        raise HTTPException(status_code=404, detail="No citation found for this document")
    return doc.citation


@router.put(
    "/{kb_id}/documents/{doc_id}/citation",
    response_model=CitationOut,
    status_code=status.HTTP_200_OK,
)
def upsert_citation(
    kb_id: int,
    doc_id: int,
    payload: CitationCreate,
    db: Session = Depends(get_db),
):
    """Create or replace the citation for a document (upsert) / 创建或更新文档的引用信息。"""
    _get_kb(kb_id, db)
    doc = _get_doc(kb_id, doc_id, db)

    data = payload.model_dump()
    logger.info("[upsert_citation] doc_id=%s, existing=%s, payload=%s", doc_id, doc.citation is not None, data)

    if doc.citation:
        for field, value in data.items():
            setattr(doc.citation, field, value)
        db.commit()
        db.refresh(doc.citation)
        logger.info("[upsert_citation] UPDATED doc_id=%s → title=%s, raw_citation=%s", doc_id, doc.citation.title, doc.citation.raw_citation)
        return doc.citation

    citation = Citation(document_file_id=doc.id, **data)
    db.add(citation)
    db.commit()
    db.refresh(citation)
    logger.info("[upsert_citation] CREATED doc_id=%s → citation_id=%s, title=%s", doc_id, citation.id, citation.title)
    return citation


@router.patch("/{kb_id}/documents/{doc_id}/citation", response_model=CitationOut)
def patch_citation(
    kb_id: int,
    doc_id: int,
    payload: CitationUpdate,
    db: Session = Depends(get_db),
):
    """Partially update citation fields / 部分更新引用字段。"""
    _get_kb(kb_id, db)
    doc = _get_doc(kb_id, doc_id, db)
    if doc.citation is None:
        raise HTTPException(
            status_code=404,
            detail="No citation found for this document. Use PUT to create one.",
        )
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(doc.citation, field, value)
    db.commit()
    db.refresh(doc.citation)
    return doc.citation


@router.delete("/{kb_id}/documents/{doc_id}/citation", status_code=status.HTTP_204_NO_CONTENT)
def delete_citation(kb_id: int, doc_id: int, db: Session = Depends(get_db)):
    """Delete citation metadata for a document / 删除文档的引用信息。"""
    _get_kb(kb_id, db)
    doc = _get_doc(kb_id, doc_id, db)
    if doc.citation is None:
        raise HTTPException(status_code=404, detail="No citation found for this document")
    db.delete(doc.citation)
    db.commit()


@router.get("/{kb_id}/documents/{doc_id}/citation/formatted", response_model=CitationFormatted)
def get_citation_formatted(
    kb_id: int,
    doc_id: int,
    style: str = "apa",
    db: Session = Depends(get_db),
):
    """Return the citation formatted in a specific style.
    支持的格式：apa / mla / chicago / gb_t7714。"""
    if style not in SUPPORTED_STYLES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported citation style '{style}'. Supported: {', '.join(SUPPORTED_STYLES)}",
        )
    _get_kb(kb_id, db)
    doc = _get_doc(kb_id, doc_id, db)
    if doc.citation is None:
        raise HTTPException(status_code=404, detail="No citation found for this document")
    return CitationFormatted(style=style, text=format_citation(doc.citation, style))


# ============================= AI Citation Parsing =============================

class BatchAIParseRequest(BaseModel):
    doc_ids: list[int]


class BatchMatchTextRequest(BaseModel):
    doc_ids: list[int]
    citation_text: str


@router.post("/" + "{kb_id}" + "/documents/batch-ai-parse")
async def batch_ai_parse_citations(
    kb_id: int,
    payload: BatchAIParseRequest,
    db: Session = Depends(get_db),
):
    """使用 AI 从文档内容中提取引用信息（批量，SSE 流式进度）。

    以 Server-Sent Events 格式逐文档返回进度：
      data: [PROGRESS] {"current":1,"total":7,"filename":"xxx.pdf","status":"parsing"}
      data: [PROGRESS] {"current":1,"total":7,"filename":"xxx.pdf","status":"done"}
      data: [DONE]

    每个文档的 LLM 调用在独立线程（asyncio.to_thread）中运行，
    不阻塞事件循环，并拥有各自的数据库 Session。
    需要在设置中配置 ``info_extract_model_id``。
    """
    _get_kb(kb_id, db)

    from knowledge.documents.citation_ai import _load_model, extract_one_doc

    ai_model = _load_model(db)
    if ai_model is None:
        raise HTTPException(status_code=400, detail="未配置信息提取模型，请先在设置中配置 info_extract_model_id")

    docs = (
        db.query(DocumentFile)
        .filter(
            DocumentFile.knowledge_base_id == kb_id,
            DocumentFile.id.in_(payload.doc_ids),
        )
        .all()
    )
    doc_info = [(doc.id, doc.original_filename) for doc in docs]
    model_id = ai_model.id

    async def _generate():
        total = len(doc_info)
        for i, (doc_id, filename) in enumerate(doc_info):
            progress = {
                "current": i + 1,
                "total": total,
                "filename": filename,
                "status": "parsing",
            }
            yield f"data: [PROGRESS] {json.dumps(progress, ensure_ascii=False)}\n\n"

            try:
                result = await asyncio.to_thread(extract_one_doc, doc_id, model_id)
                progress["status"] = result["status"]
                if result.get("message"):
                    progress["message"] = result["message"]
            except Exception as exc:
                progress["status"] = "error"
                progress["message"] = str(exc)

            yield f"data: [PROGRESS] {json.dumps(progress, ensure_ascii=False)}\n\n"

        yield "data: [DONE]\n\n"

    return StreamingResponse(
        _generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post(
    "/{kb_id}/documents/batch-match-text",
    response_model=list[DocumentFileOut],
)
def batch_match_citations_from_text(
    kb_id: int,
    payload: BatchMatchTextRequest,
    db: Session = Depends(get_db),
):
    """将用户粘贴的引文文本与所选文档匹配，并写入引用信息。

    将文档列表 + 引文文本发送给 AI 模型，由模型负责匹配并提取结构化字段，
    随后自动 upsert 每个文档的 Citation 记录。
    需要在设置中配置 ``info_extract_model_id``。
    """
    _get_kb(kb_id, db)
    if not payload.citation_text.strip():
        raise HTTPException(status_code=400, detail="citation_text must not be empty")
    from knowledge.documents.citation_ai import match_citations_from_text
    try:
        docs = match_citations_from_text(kb_id, payload.doc_ids, payload.citation_text, db)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    for doc in docs:
        db.refresh(doc)
    return [_doc_to_out(d) for d in docs]
