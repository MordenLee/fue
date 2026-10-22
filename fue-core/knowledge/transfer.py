"""Portable retrieval data. No model calls, original attachments or credentials."""
import hashlib
import json
import logging
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, FiniteFloat, ValidationError, model_validator

from knowledge.documents.models import Citation, CitationCreate, DocumentFile
from knowledge.models import KnowledgeBase

MAX_BYTES = 256 * 1024 * 1024
PROFILE_KEY = 'fue_embedding_profile'
logger = logging.getLogger(__name__)


def profile(model):
    # Never export provider URLs (which may contain credentials) or API keys.
    endpoint = (model.provider.api_base_url or '').strip().rstrip('/')
    return dict(api_name=model.api_name, interface_type=model.provider.interface_type,
                endpoint_sha256=hashlib.sha256(endpoint.encode()).hexdigest(),
                normalization='provider_default', revision=None)


def digest(payload):
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True,
                                    separators=(',', ':'), allow_nan=False).encode()).hexdigest()


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)


class Chunk(StrictModel):
    index: int = Field(ge=0)
    content: str = Field(min_length=1)
    embedding: list[FiniteFloat] = Field(min_length=1, max_length=65536)


class Document(StrictModel):
    id: str = Field(min_length=1)
    filename: str = Field(min_length=1, max_length=256)
    file_type: str = Field(max_length=32)
    abstract: str | None = None
    citation: CitationCreate | None = None
    chunks: list[Chunk]

    @model_validator(mode='after')
    def sequence(self):
        if sorted(c.index for c in self.chunks) != list(range(len(self.chunks))):
            raise ValueError('Chunk indices must be unique and contiguous from zero')
        return self


class Package(StrictModel):
    format: str
    format_version: str
    exported_at: str
    kb_name: str = Field(min_length=1, max_length=128)
    kb_description: str | None
    chunk_size: int = Field(ge=100, le=5000)
    chunk_overlap: int = Field(ge=0, le=1000)
    use_delimiter_split: bool
    embedding_profile: dict
    profile_verified: bool
    dimension: int = Field(ge=0, le=65536)
    documents: list[Document]

    @model_validator(mode='after')
    def integrity(self):
        if self.format != 'fue-knowledge-base' or self.format_version != '2.0':
            raise ValueError('Only FUE knowledge-base format 2.0 is supported')
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError('Chunk overlap must be smaller than chunk size')
        if len({d.id for d in self.documents}) != len(self.documents):
            raise ValueError('Duplicate document IDs')
        for d in self.documents:
            for c in d.chunks:
                if len(c.embedding) != self.dimension or not any(c.embedding):
                    raise ValueError('Invalid embedding dimension or zero vector')
                if any(abs(v) > 3.402823466e38 for v in c.embedding):
                    raise ValueError('Embedding exceeds float32 range')
        return self


def decode(raw):
    try:
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise ValueError('Expected a JSON object')
        checksum = data.pop('sha256', None)
        if not checksum or checksum != digest(data):
            raise ValueError('Checksum missing or invalid; export the knowledge base again')
        return Package.model_validate(data)
    except (ValueError, TypeError, UnicodeError, RecursionError, ValidationError) as exc:
        raise HTTPException(400, 'Invalid knowledge-base package: ' + str(exc)[:500]) from exc


def export_package(kb, model, collection):
    if any(d.status != 'indexed' for d in kb.documents):
        raise HTTPException(409, '请先完成所有文档的索引，或移除未完成的文档，再导出知识库。')
    raw = collection.get(include=['documents', 'metadatas', 'embeddings']) if collection else {}
    by_doc = {d.id: [] for d in kb.documents}
    ids = raw.get('ids', [])
    texts, metas, vectors = raw.get('documents'), raw.get('metadatas'), raw.get('embeddings')
    if len(ids) and (texts is None or metas is None or vectors is None or
                     len({len(ids), len(texts), len(metas), len(vectors)}) != 1):
        raise HTTPException(409, 'Incomplete vector collection')
    for i in range(len(ids)):
        meta = metas[i] or {}
        if meta.get('document_file_id') not in by_doc:
            raise HTTPException(409, 'Orphaned chunks found; repair the index before export')
        by_doc[meta['document_file_id']].append(dict(index=meta['chunk_index'], content=texts[i],
                                                   embedding=[float(x) for x in vectors[i]]))
    docs = []
    for doc in kb.documents:
        chunks = sorted(by_doc[doc.id], key=lambda c: c['index'])
        if len(chunks) != doc.chunk_count:
            raise HTTPException(409, 'Document chunk count changed; retry after indexing completes')
        citation = ({key: getattr(doc.citation, key) for key in CitationCreate.model_fields}
                    if doc.citation else None)
        docs.append(dict(id=str(doc.id), filename=doc.original_filename, file_type=doc.file_type,
                         abstract=doc.abstract, citation=citation, chunks=chunks))
    stored = (collection.metadata or {}).get(PROFILE_KEY) if collection else None
    stored_profile = json.loads(stored) if stored else profile(model)
    if stored_profile != profile(model):
        raise HTTPException(409, 'Embedding configuration changed since indexing')
    dimension = next((len(c['embedding']) for d in docs for c in d['chunks']), 0)
    payload = dict(format='fue-knowledge-base', format_version='2.0',
                   exported_at=datetime.now(timezone.utc).isoformat(), kb_name=kb.name,
                   kb_description=kb.description, chunk_size=kb.chunk_size,
                   chunk_overlap=kb.chunk_overlap, use_delimiter_split=kb.use_delimiter_split,
                   embedding_profile=stored_profile,
                   profile_verified=bool(stored) and (collection.metadata or {}).get('fue_profile_verified', True),
                   dimension=dimension, documents=docs)
    try:
        Package.model_validate(payload)
    except ValidationError as exc:
        raise HTTPException(409, 'Knowledge-base data is inconsistent; export aborted') from exc
    return dict(payload, sha256=digest(payload))


def import_package(package, model, name, db, client, confirm_unverified=False):
    if package.embedding_profile != profile(model):
        raise HTTPException(409, '嵌入模型或服务配置不匹配，请选择与导出端一致的模型和服务地址。')
    if not package.profile_verified and not confirm_unverified:
        raise HTTPException(409, '旧索引没有模型来源记录，请确认所选模型与原索引一致。')
    name = (name or package.kb_name).strip()
    if not name or len(name) > 128:
        raise HTTPException(400, 'Knowledge-base name must contain 1–128 characters')
    # Unique collection prevents a crash orphan from colliding with a reused SQLite ID.
    collection_name = 'kb_import_' + uuid4().hex
    kb = KnowledgeBase(name=name, description=package.kb_description, embed_model_id=model.id,
                       chunk_size=package.chunk_size, chunk_overlap=package.chunk_overlap,
                       use_delimiter_split=package.use_delimiter_split, collection_name=collection_name)
    created = False
    count = 0
    try:
        db.add(kb)
        db.flush()
        collection = client.create_collection(collection_name, metadata={
            PROFILE_KEY: json.dumps(package.embedding_profile),
            'fue_profile_verified': package.profile_verified})
        created = True
        now = datetime.now(timezone.utc)
        batch_size = min(500, client.get_max_batch_size())
        for item in package.documents:
            doc = DocumentFile(knowledge_base_id=kb.id, original_filename=item.filename,
                               file_path='<imported>', file_type=item.file_type, file_size=0,
                               abstract=item.abstract, status='indexed', chunk_count=len(item.chunks),
                               indexed_at=now)
            db.add(doc)
            db.flush()
            if item.citation:
                db.add(Citation(document_file_id=doc.id, **item.citation.model_dump()))
            for start in range(0, len(item.chunks), batch_size):
                chunks = item.chunks[start:start + batch_size]
                collection.add(ids=[f'doc{doc.id}_chunk{c.index}' for c in chunks],
                    documents=[c.content for c in chunks], embeddings=[c.embedding for c in chunks],
                    metadatas=[dict(document_file_id=doc.id, knowledge_base_id=kb.id,
                                    original_filename=item.filename, chunk_index=c.index) for c in chunks])
            count += len(item.chunks)
        db.commit()
    except Exception:
        db.rollback()
        if created:
            try:
                client.delete_collection(collection_name)
            except Exception:
                logger.exception('Failed to remove incomplete import %s', collection_name)
        raise
    return kb, count
