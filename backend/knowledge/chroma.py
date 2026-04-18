"""ChromaDB client singleton and helper functions."""

import os
from pathlib import Path

import chromadb

# ChromaDB 持久化存储目录，放在项目根目录下的 chroma_data/
_DEFAULT_DATA_DIR = Path(__file__).resolve().parent.parent
_DATA_DIR = Path(os.environ.get("APP_BACKEND_DATA_DIR", _DEFAULT_DATA_DIR))
_CHROMA_DIR = _DATA_DIR / "chroma_data"

# Collection 命名前缀 —— 修改此值可为整个实例添加命名空间隔离
COLLECTION_PREFIX = "kb_"

_client: chromadb.ClientAPI | None = None


def get_chroma_client() -> chromadb.ClientAPI:
    """Return a singleton persistent ChromaDB client."""
    global _client
    if _client is None:
        _CHROMA_DIR.mkdir(parents=True, exist_ok=True)
        _client = chromadb.PersistentClient(path=str(_CHROMA_DIR))
    return _client


def get_or_create_collection(name: str) -> chromadb.Collection:
    """Get or create a ChromaDB collection by name."""
    client = get_chroma_client()
    return client.get_or_create_collection(name=name)


def delete_collection(name: str) -> None:
    """Delete a ChromaDB collection. Silently ignores if not found."""
    client = get_chroma_client()
    try:
        client.delete_collection(name=name)
    except Exception:
        pass


def delete_documents_by_file(collection_name: str, document_file_id: int) -> None:
    """Delete all chunks belonging to a specific document file from a collection."""
    client = get_chroma_client()
    try:
        collection = client.get_collection(name=collection_name)
    except ValueError:
        return
    # 使用 metadata 过滤删除
    results = collection.get(
        where={"document_file_id": document_file_id},
    )
    if results["ids"]:
        collection.delete(ids=results["ids"])


def get_all_chunks(collection_name: str) -> dict:
    """Fetch every chunk stored in *collection_name*, including raw embedding vectors.

    Returns a dict with keys: ids, documents, metadatas, embeddings.
    All lists are parallel and may be empty when the collection is missing or empty.
    """
    client = get_chroma_client()
    try:
        collection = client.get_collection(name=collection_name)
    except ValueError:
        return {"ids": [], "documents": [], "metadatas": [], "embeddings": []}
    count = collection.count()
    if count == 0:
        return {"ids": [], "documents": [], "metadatas": [], "embeddings": []}
    return collection.get(include=["documents", "metadatas", "embeddings"])
