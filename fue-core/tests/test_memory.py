"""Integration tests using real in-memory SQLite/Chroma, without remote models."""
import asyncio
import os
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import chromadb
from chromadb.config import Settings
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from database import Base
from conversations.models import Conversation, Message, MessageAppend, MessageCreate
from conversations import router as chats
from memory import service
from memory.models import QAPair, ChatEvent
from memory.mcp import dispatch, router as mcp_router
from agents.tools import make_source_bindings
from settings.models import Setting
from providers.models import Provider, AIModel
from knowledge.models import KnowledgeBase
from knowledge.documents.models import DocumentFile


class MemoryTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        self.sessions = sessionmaker(bind=self.engine)
        Base.metadata.create_all(self.engine)
        self.client = chromadb.EphemeralClient(settings=Settings(anonymized_telemetry=False))
        for collection in self.client.list_collections():
            self.client.delete_collection(getattr(collection, "name", collection))
        p = patch("knowledge.chroma.get_chroma_client", return_value=self.client)
        p.start()
        self.addCleanup(p.stop)
        self.addCleanup(self.engine.dispose)
        with self.sessions() as db:
            provider = Provider(name="test", interface_type="openai")
            db.add(provider)
            db.flush()
            model = AIModel(api_name="test", display_name="test", model_type="embedding", provider_id=provider.id)
            db.add(model)
            db.flush()
            self.model_id = model.id
            db.add_all([Setting(key="memory_query_scope", value="all"), Setting(key="memory_query_mode", value="keyword")])
            conv = Conversation(title="memory-test")
            db.add(conv)
            db.commit()
            self.conv_id = conv.id

    def append(self, question="project-orchid", answer="budget is 150000"):
        with self.sessions() as db:
            rows = chats.append_messages(self.conv_id, MessageAppend(messages=[
                MessageCreate(role="user", content=question), MessageCreate(role="assistant", content=answer)]), db)
            return [r.id for r in rows]

    def setting(self, key, value):
        with self.sessions() as db:
            db.merge(Setting(key=key, value=value))
            db.commit()

    def test_full_qa_pair_not_character_chunks_and_exact_log(self):
        question, answer = "q" * 4000, "a" * 16000
        self.append(question, answer)
        service.process_pending(self.sessions)
        raw = self.client.get_collection("chat_memory").get(include=["documents"])
        self.assertEqual(raw["documents"], [f"User:\n{question}\n\nAssistant:\n{answer}"])
        with self.sessions() as db:
            self.assertEqual(db.query(ChatEvent).count(), 2)
            self.assertEqual(db.query(QAPair).one().answer, answer)

    def test_keyword_works_without_rag_and_timeline_browses(self):
        self.append()
        service.process_pending(self.sessions)
        with self.sessions() as db:
            result = service.search(db, "orchid", mode="hybrid")
            self.assertEqual(result["mode"], "keyword")
            self.assertEqual(len(result["results"]), 1)
            self.assertEqual(service.search(db, "")["mode"], "timeline")

    def test_time_scope_restricts_search_read_and_neighbors(self):
        self.append("old", "old answer")
        self.append("recent", "recent answer")
        with self.sessions() as db:
            pairs = db.query(QAPair).order_by(QAPair.position).all()
            pairs[0].timestamp = int(time.time()) - 8 * 86400
            old_id, new_id = pairs[0].id, pairs[1].id
            db.commit()
        self.setting("memory_query_scope", "7")
        with self.sessions() as db:
            self.assertFalse(service.search(db, "old")["results"])
            with self.assertRaises(PermissionError):
                service.read_chat(db, old_id)
            self.assertNotIn("old answer", service.read_chat(db, new_id, before=3)["text"])
        self.setting("memory_query_scope", "disabled")
        with self.sessions() as db:
            with self.assertRaises(PermissionError):
                service.search(db, "recent")

    def test_edit_and_regeneration_log_versions_then_delete_everything(self):
        ids = self.append("original question", "original answer")
        with self.sessions() as db:
            chats.update_message(self.conv_id, ids[0], {"content": "revised question"}, db)
            self.assertEqual(db.query(Message).count(), 1)
            self.assertIsNotNone(db.query(QAPair).filter_by(answer="original answer").first())
            self.assertGreaterEqual(db.query(ChatEvent).count(), 3)
            rows = chats.append_messages(self.conv_id, MessageAppend(messages=[MessageCreate(role="assistant", content="revised answer")]), db)
            chats.prepare_regeneration(self.conv_id, rows[0].id, db)
            self.assertFalse(db.query(QAPair).filter_by(answer="revised answer").one().active)
        service.process_pending(self.sessions)
        with self.sessions() as db:
            chats.delete_conversation(self.conv_id, db)
            self.assertEqual(db.query(QAPair).count(), 0)
            self.assertEqual(db.query(ChatEvent).count(), 0)
            self.assertEqual(db.query(Message).count(), 0)
        self.assertEqual(self.client.get_collection("chat_memory").count(), 0)

    def test_late_embedding_cannot_resurrect_deleted_history(self):
        self.append()
        self.setting("memory_embed_model_id", str(self.model_id))
        def embed(content):
            with self.sessions() as db:
                chats.delete_conversation(self.conv_id, db)
            return [1.0, 0.0]
        embedder = MagicMock()
        embedder.embed_query.side_effect = embed
        with patch("providers.embeddings.build_embedder", return_value=embedder):
            service.process_pending(self.sessions)
        self.assertEqual(self.client.get_collection("chat_memory").count(), 0)
        self.assertNotIn(f"chat_memory_vectors_{self.model_id}", service._collections(self.client))

    def test_semantic_index_uses_complete_pair(self):
        self.append()
        self.setting("memory_embed_model_id", str(self.model_id))
        self.setting("memory_query_mode", "rag")
        embedder = MagicMock()
        embedder.embed_query.return_value = [1.0, 0.0]
        with patch("providers.embeddings.build_embedder", return_value=embedder):
            service.process_pending(self.sessions)
            with self.sessions() as db:
                result = service.search(db, "financial plan", mode="vector")
        self.assertEqual(len(result["results"]), 1)
        self.assertIn("User:", embedder.embed_query.call_args_list[0].args[0])
        self.assertIn("Assistant:", embedder.embed_query.call_args_list[0].args[0])

    def test_qa_neighbor_reading_is_paginated(self):
        for i in range(3):
            self.append(f"question {i}", f"answer {i}")
        with self.sessions() as db:
            pair = db.query(QAPair).filter_by(question="question 1").one()
            page = service.read_chat(db, pair.id, before=1, after=1, length=100)
            rest = service.read_chat(db, pair.id, before=1, after=1, offset=100, length=1000)
            for i in range(3):
                self.assertIn(f"answer {i}", page["text"] + rest["text"])

    def test_document_neighbor_reading_is_scoped(self):
        with self.sessions() as db:
            kb = KnowledgeBase(name="book", embed_model_id=self.model_id, collection_name="memory_test_book")
            db.add(kb)
            db.flush()
            doc = DocumentFile(knowledge_base_id=kb.id, original_filename="book.txt", file_path="book.txt", file_type="txt", file_size=10)
            db.add(doc)
            db.commit()
            kb_id, doc_id = kb.id, doc.id
        collection = self.client.create_collection("memory_test_book", embedding_function=None)
        collection.add(ids=["a", "b", "c"], embeddings=[[1.0], [1.0], [1.0]], documents=["before", "hit", "after"],
                       metadatas=[{"document_file_id": doc_id, "chunk_index": i} for i in range(3)])
        async def run():
            read = next(b for b in make_source_bindings([kb_id], self.sessions) if b.id == "sources.read")
            result = await read.execute({"source": "knowledge", "document_id": doc_id, "chunk_index": 1, "before": 1, "after": 1})
            self.assertIn("before", result.content)
            self.assertIn("after", result.content)
            denied = next(b for b in make_source_bindings([], self.sessions) if b.id == "sources.read")
            with self.assertRaises(PermissionError):
                await denied.execute({"source": "knowledge", "document_id": doc_id})
        asyncio.run(run())

    def test_mcp_dispatch_and_http_auth(self):
        self.append()
        bindings = make_source_bindings([], self.sessions)
        async def run():
            response = await dispatch({"id": 2, "method": "tools/call", "params": {
                "name": "search_chat_history", "arguments": {"query": "orchid"}}}, bindings)
            self.assertFalse(response["result"]["isError"])
            self.setting("memory_query_scope", "disabled")
            response = await dispatch({"id": 3, "method": "tools/call", "params": {
                "name": "search_chat_history", "arguments": {"query": "orchid"}}}, bindings)
            self.assertTrue(response["result"]["isError"])
        asyncio.run(run())
        app = FastAPI()
        app.include_router(mcp_router)
        with TestClient(app) as client, patch.dict(os.environ, {"APP_MCP_TOKEN": "test-secret"}):
            headers = {"Authorization": "Bearer test-secret", "Accept": "application/json, text/event-stream"}
            body = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}
            self.assertEqual(client.post("/api/mcp", json=body).status_code, 401)
            self.assertEqual(client.post("/api/mcp", json=body, headers={**headers, "Origin": "https://example.com"}).status_code, 403)
            # Initialization should not touch application storage.
            with patch("database.SessionLocal", self.sessions):
                response = client.post("/api/mcp", json=body, headers=headers)
            self.assertEqual(response.status_code, 200)
            self.assertIn("protocolVersion", response.json()["result"])
            self.assertEqual(client.get("/api/mcp").status_code, 405)

    def test_index_deletion_failure_does_not_report_chat_as_deleted(self):
        self.append()
        service.process_pending(self.sessions)
        broken = MagicMock()
        broken.list_collections.return_value = ["chat_memory"]
        broken.get_collection.return_value.delete.side_effect = RuntimeError("index unavailable")
        with self.sessions() as db, patch("knowledge.chroma.get_chroma_client", return_value=broken):
            with self.assertRaises(RuntimeError):
                chats.delete_conversation(self.conv_id, db)
            db.rollback()
        with self.sessions() as db:
            self.assertIsNotNone(db.get(Conversation, self.conv_id))
            self.assertEqual(db.query(ChatEvent).count(), 2)
            self.assertEqual(db.query(QAPair).count(), 1)

    def test_deleted_source_prevents_late_answer_persistence(self):
        from chat.router import _save_turn, ChatMessage
        ids = self.append()
        with self.sessions() as db:
            chats.clear_messages(self.conv_id, db)
        with self.sessions() as db:
            with self.assertRaisesRegex(ValueError, "deleted"):
                _save_turn(db, self.conv_id, [ChatMessage(role="user", content="project-orchid")],
                           "late private answer", source_user_message_id=ids[0])
            self.assertEqual(db.query(Message).count(), 0)

    def test_knowledge_keyword_only_never_uses_embedding_or_rerank(self):
        from agents.tools import make_knowledge_binding
        self.setting("knowledge_query_mode", "keyword")
        with self.sessions() as db:
            kb = KnowledgeBase(name="book", embed_model_id=self.model_id, collection_name="memory_test_keyword")
            db.add(kb)
            db.commit()
            kb_id = kb.id
        collection = self.client.create_collection("memory_test_keyword", embedding_function=None)
        collection.add(ids=["x"], embeddings=[[1.0]], documents=["orchid keyword evidence"], metadatas=[{
            "document_file_id": 1, "chunk_index": 0, "original_filename": "test.txt"}])
        async def run():
            binding = make_knowledge_binding([kb_id], [], self.sessions)
            with patch("providers.embeddings.build_embedder", side_effect=AssertionError("Embedding called")), \
                 patch("chat.tools._maybe_rerank", side_effect=AssertionError("Rerank called")):
                result = await binding.execute({"query": "orchid", "mode": "vector"})
            self.assertEqual(result.status, "ok")
            with self.assertRaises(PermissionError):
                await binding.execute({"query": "orchid", "kb_ids": [999]})
        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
