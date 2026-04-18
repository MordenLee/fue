"""Background task: parse file → clean → chunk → embed → store in ChromaDB."""

import logging
import math
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from langchain_text_splitters import RecursiveCharacterTextSplitter

# ---------------------------------------------------------------------------
# Semantic delimiter separators for structural-aware text splitting.
# When use_delimiter_split=True, the splitter tries to break at structural
# boundaries first (headings → paragraphs → sentences → words → chars).
# ---------------------------------------------------------------------------
_SEMANTIC_SEPARATORS: list[str] = [
    # Markdown headings
    "\n# ", "\n## ", "\n### ", "\n#### ", "\n##### ",
    # Multiple blank lines (section break)
    "\n\n\n",
    # Paragraph break
    "\n\n",
    # Chinese sentence + newline
    "。\n", "？\n", "！\n",
    # English sentence + newline
    ".\n", "?\n", "!\n",
    # Single newline
    "\n",
    # Chinese sentence-ending punctuation
    "。", "？", "！", "；",
    # English sentence-ending punctuation
    ". ", "? ", "! ", "; ",
    # Word boundary
    " ",
    # Character fallback
    "",
]
from sqlalchemy.orm import Session, joinedload

from auxmodels.cleaner import clean_document as _clean_document_fn
from auxmodels.extractor import extract as _extract_fn
from knowledge.chroma import get_or_create_collection
from knowledge.documents.models import Citation, DocumentFile
from knowledge.models import KnowledgeBase
from knowledge.parser import SUPPORTED_EXTENSIONS, parse_file
from providers.chat import build_llm as _build_llm_base, load_chat_model as _load_aux_model
from providers.embeddings import build_embedder
from providers.models import AIModel
from settings.models import DEFAULTS, Setting

logger = logging.getLogger(__name__)

# Re-export so routers can keep importing from here
__all__ = ["SUPPORTED_EXTENSIONS", "index_document"]


def _get_embed_max_concurrency(db: Session) -> int:
    """Read embed_max_concurrency from settings, fall back to default."""
    row = db.get(Setting, "embed_max_concurrency")
    try:
        return int(row.value) if row else int(DEFAULTS["embed_max_concurrency"])
    except (ValueError, TypeError):
        return 4


def _get_parser_config(db: Session) -> tuple[str, str]:
    """Return (pdf_parser, docx_parser) from settings."""
    pdf_row = db.get(Setting, "pdf_parser")
    docx_row = db.get(Setting, "docx_parser")
    pdf_parser = (pdf_row.value if pdf_row else None) or DEFAULTS["pdf_parser"]
    docx_parser = (docx_row.value if docx_row else None) or DEFAULTS["docx_parser"]
    return pdf_parser, docx_parser


def _get_aux_model_id(db: Session, key: str) -> int | None:
    """Return an auxiliary model ID from settings, or None if not configured."""
    row = db.get(Setting, key)
    value = row.value if row else ""
    try:
        return int(value) if value else None
    except (ValueError, TypeError):
        return None


def _get_clean_keep_references(db: Session) -> bool:
    """Return the doc_clean_keep_references setting (default False)."""
    row = db.get(Setting, "doc_clean_keep_references")
    if row:
        return row.value.lower() == "true"
    return DEFAULTS.get("doc_clean_keep_references", "false").lower() == "true"


def _get_clean_keep_annotations(db: Session) -> bool:
    """Return the doc_clean_keep_annotations setting (default False)."""
    row = db.get(Setting, "doc_clean_keep_annotations")
    if row:
        return row.value.lower() == "true"
    return DEFAULTS.get("doc_clean_keep_annotations", "false").lower() == "true"


def _parallel_embed(embedder, chunks: list[str], max_concurrency: int) -> list[list[float]]:
    """Embed *chunks* using up to *max_concurrency* parallel API calls.

    Splits the chunk list into at most *max_concurrency* batches and submits
    each batch to a thread-pool worker, preserving original order.
    """
    if not chunks:
        return []
    n_batches = min(max_concurrency, len(chunks))
    batch_size = math.ceil(len(chunks) / n_batches)
    batches = [chunks[i: i + batch_size] for i in range(0, len(chunks), batch_size)]

    with ThreadPoolExecutor(max_workers=len(batches)) as executor:
        futures = [executor.submit(embedder.embed_documents, batch) for batch in batches]

    vectors: list[list[float]] = []
    for future in futures:
        vectors.extend(future.result())
    return vectors


def _is_cancelled_or_deleted(db: Session, doc_id: int) -> bool:
    """Return True if the document was deleted or cancelled by another session.

    Executes a raw SQL query after the preceding commit so the connection
    sees the latest committed state from any concurrent session (e.g. a cancel
    or delete API call that committed while we were processing).
    """
    from sqlalchemy import text as _text
    row = db.execute(
        _text("SELECT status FROM document_files WHERE id = :id"),
        {"id": doc_id},
    ).fetchone()
    return row is None or row[0] == "cancelled"


def index_document(db: Session, document_file_id: int) -> None:
    """Parse, chunk, clean, embed and index a single document file.

    Pipeline: parse → chunk → clean chunks (async) + extract (async) → embed → store.
    This function is designed to be run as a FastAPI BackgroundTask.
    It manages its own DB state transitions: pending → parsing → chunking → cleaning → embedding → indexed / failed.
    """
    doc = (
        db.query(DocumentFile)
        .options(joinedload(DocumentFile.knowledge_base))
        .filter(DocumentFile.id == document_file_id)
        .first()
    )
    if not doc:
        logger.error("DocumentFile %s not found", document_file_id)
        return

    kb: KnowledgeBase = doc.knowledge_base

    # Mark as parsing
    doc.status = "parsing"
    doc.error_message = None
    db.commit()

    try:
        # 1. Parse file
        pdf_parser, docx_parser = _get_parser_config(db)
        text = parse_file(doc.file_path, pdf_parser=pdf_parser, docx_parser=docx_parser)
        if not text.strip():
            raise ValueError("File content is empty after parsing")

        # Cancel-check 1: abort if deleted or cancelled while parsing
        if _is_cancelled_or_deleted(db, doc.id):
            logger.info("Doc %s: cancelled or deleted after parse — aborting", doc.id)
            return

        # 2. Load auxiliary models
        _clean_model_id   = _get_aux_model_id(db, "doc_clean_model_id")
        _extract_model_id = _get_aux_model_id(db, "info_extract_model_id")
        _clean_model   = _load_aux_model(_clean_model_id,   db) if _clean_model_id   else None
        _extract_model = _load_aux_model(_extract_model_id, db) if _extract_model_id else None
        _keep_references = _get_clean_keep_references(db)
        _keep_annotations = _get_clean_keep_annotations(db)

        # 3. Clean whole document + extract metadata concurrently (before chunking)
        _extract_result: dict = {}
        clean_text = text
        if _clean_model or _extract_model:
            doc.status = "cleaning"
            db.commit()

            clean_qps = 0
            if _clean_model and _clean_model_id:
                clean_model_row = db.get(AIModel, _clean_model_id)
                clean_qps = (clean_model_row.qps or 0) if clean_model_row else 0

            with ThreadPoolExecutor(max_workers=2) as pool:
                clean_future = None
                if _clean_model:
                    clean_future = pool.submit(
                        _clean_document_fn, text, _clean_model, _clean_model_id, clean_qps, _keep_references, _keep_annotations
                    )

                extract_future = None
                if _extract_model:
                    extract_future = pool.submit(
                        _extract_fn, text, doc.original_filename, _extract_model
                    )

                if clean_future is not None:
                    try:
                        clean_text = clean_future.result() or text
                        logger.info("Doc %s: document text cleaned", doc.id)
                    except Exception as exc:
                        logger.warning("Cleaner failed for doc %s: %s — using raw text", doc.id, exc)

                if extract_future is not None:
                    try:
                        _extract_result = extract_future.result() or {}
                    except Exception as _exc_e:
                        logger.warning("Extractor failed for doc %s: %s", doc.id, _exc_e)

        # Cancel-check 2: abort if deleted or cancelled while cleaning/extracting
        if _is_cancelled_or_deleted(db, doc.id):
            logger.info("Doc %s: cancelled or deleted after clean — aborting", doc.id)
            return

        # 4. Chunk cleaned text
        doc.status = "chunking"
        db.commit()
        splitter_kwargs: dict = dict(
            chunk_size=kb.chunk_size,
            chunk_overlap=kb.chunk_overlap,
        )
        if kb.use_delimiter_split:
            splitter_kwargs["separators"] = _SEMANTIC_SEPARATORS
            splitter_kwargs["is_separator_regex"] = False
        splitter = RecursiveCharacterTextSplitter(**splitter_kwargs)
        chunks = splitter.split_text(clean_text)
        if not chunks:
            raise ValueError("No chunks produced after splitting")

        # 5. Get embedding model
        embed_model = (
            db.query(AIModel)
            .filter(AIModel.id == kb.embed_model_id)
            .first()
        )
        if not embed_model:
            raise ValueError(f"Embedding model (id={kb.embed_model_id}) not found")

        embedder = build_embedder(embed_model)

        # 6. Compute embeddings in parallel
        doc.status = "embedding"
        db.commit()
        max_concurrency = _get_embed_max_concurrency(db)
        vectors = _parallel_embed(embedder, chunks, max_concurrency)

        # Cancel-check 3: final guard — prevents orphaned chunks in ChromaDB
        if _is_cancelled_or_deleted(db, doc.id):
            logger.info("Doc %s: cancelled or deleted before chroma write — aborting", doc.id)
            return

        # 7. Store into ChromaDB collection
        collection = get_or_create_collection(kb.collection_name)
        ids = [f"doc{doc.id}_chunk{i}" for i in range(len(chunks))]
        metadatas = [
            {
                "document_file_id": doc.id,
                "knowledge_base_id": kb.id,
                "original_filename": doc.original_filename,
                "chunk_index": i,
            }
            for i in range(len(chunks))
        ]
        collection.add(
            ids=ids,
            embeddings=vectors,
            documents=chunks,
            metadatas=metadatas,
        )

        # 8. Mark success
        doc.status = "indexed"
        doc.chunk_count = len(chunks)
        doc.indexed_at = datetime.now(timezone.utc)
        db.commit()

        logger.info(
            "Indexed document %s (%s) → %d chunks into collection %s",
            doc.id, doc.original_filename, len(chunks), kb.collection_name,
        )
        # 9. Apply extraction results
        if _extract_result:
            abstract = _extract_result.pop("abstract", None)
            if abstract:
                doc.abstract = abstract
            if _extract_result:
                db.refresh(doc)
                if doc.citation:
                    for field, value in _extract_result.items():
                        setattr(doc.citation, field, value)
                else:
                    doc.citation = Citation(document_file_id=doc.id, **_extract_result)
            db.commit()
    except Exception as exc:
        # The doc may have been deleted by a concurrent session; only update
        # status if the row still exists to avoid spurious DB errors.
        from sqlalchemy import text as _text
        still_exists = db.execute(
            _text("SELECT id FROM document_files WHERE id = :id"), {"id": doc.id}
        ).fetchone() is not None
        if still_exists:
            doc.status = "failed"
            doc.error_message = str(exc)[:2000]
            db.commit()
        logger.exception("Failed to index document %s: %s", doc.id, exc)
