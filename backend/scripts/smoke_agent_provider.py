"""Opt-in live smoke test using configured providers and existing indexed data.

Run from repo root with explicit model/KB IDs. Sends short prompts and retrieved
excerpts to the configured provider. Does not create conversations or save messages.
Never prints credentials. This is deliberately not part of automated unit tests.
"""

import argparse
import asyncio
import json
import logging
import sys
import time
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from chat.router import ChatMessage, ChatRequest, RAGChatRequest, chat_stream, chat_rag_stream
from database import SessionLocal
from providers.models import Provider


async def check(model_id, kb_id, *, rag, secrets, session_factory=SessionLocal, synthetic=False, require_context=False):
    question = (
        "请检索所选知识库，根据资料说明贸易引力模型的用途，给出两点并标注引用。控制在150字以内。"
        if rag else "这是FUE Agent真实提供商连通性测试。请只回复：FUE真实模型连接成功。"
    )
    if rag and synthetic:
        question = ("请调用 search_knowledge_base，必须使用 mode=keyword、query=FUE_AGENT_SMOKE，"
                    "查找测试文档中的验证口令。只回复口令，并附资料引用。不要使用 vector 检索。")
    if rag and require_context:
        question = (
            "Call search_knowledge_base exactly once: query='贸易引力模型', mode='vector', top_n=1. "
            "Then immediately call read_context with source='knowledge', the returned document_id/chunk_index, "
            "before=1, after=1, length=2500. Do not replace reading with repeated searches. "
            "Briefly explain the model's use in Chinese with a source citation. "
            "State honestly if the execution receipts do not contain a successful read_context."
        )
    payload = (RAGChatRequest(kb_ids=[kb_id], messages=[ChatMessage(role="user", content=question)])
               if rag else ChatRequest(messages=[ChatMessage(role="user", content=question)]))
    started = time.monotonic()
    report = {"case": "knowledge_agent" if rag else "plain_chat", "model_id": model_id}
    if rag:
        report["kb_id"] = kb_id
    try:
        tool_calls, refs, final, errors, done = [], [], None, [], False
        with session_factory() as db:
            route = chat_rag_stream if rag else chat_stream
            async with asyncio.timeout(150):
                response = await route(model_id, payload, db)
                async for frame in response.body_iterator:
                    if isinstance(frame, bytes):
                        frame = frame.decode("utf-8")
                    # Provisional raw token frames can contain newlines. Only final
                    # structured frames are authoritative in this compatibility API.
                    if frame.startswith("data: [TOOL_CALL] "):
                        tool_calls.append(json.loads(frame[len("data: [TOOL_CALL] "):].strip()))
                    elif frame.startswith("data: [CITATIONS] "):
                        refs = json.loads(frame[len("data: [CITATIONS] "):].strip())["references"]
                    elif frame.startswith("data: [REPLACE] "):
                        final = json.loads(frame[len("data: [REPLACE] "):].strip())
                    elif frame.startswith("data: [ERROR] "):
                        errors.append(frame[len("data: [ERROR] "):].strip())
                    elif frame == "data: [DONE]\n\n":
                        done = True
        report.update({"done": done, "tool_calls": tool_calls, "reference_count": len(refs),
                       "referenced_files": sorted({r["original_filename"] for r in refs}),
                       "answer": final, "errors": errors})
        report["passed"] = bool(done and final and not errors and (not rag or (tool_calls and refs)))
        if rag and synthetic:
            report["passed"] = report["passed"] and "ORCHID-742" in final
        if rag and require_context:
            report["passed"] = report["passed"] and any(t["name"] == "read_context" for t in tool_calls)
    except Exception as exc:
        report.update({"passed": False, "error_type": type(exc).__name__, "error": str(exc)})
    report["seconds"] = round(time.monotonic() - started, 2)
    encoded = json.dumps(report, ensure_ascii=True)
    for secret in secrets:
        encoded = encoded.replace(secret, "[REDACTED]")
    print(encoded, flush=True)
    return report["passed"]


async def synthetic_checks(model_id, secrets):
    """Use real tools/Chroma with a synthetic document and an isolated in-memory DB."""
    from unittest.mock import patch
    import chromadb
    from chromadb.config import Settings
    from sqlalchemy import create_engine
    from sqlalchemy.orm import joinedload, sessionmaker
    from sqlalchemy.pool import StaticPool
    from database import Base
    from providers.models import AIModel
    from knowledge.models import KnowledgeBase
    from knowledge.documents.models import DocumentFile
    from chat import router as api

    # Read only the selected model/provider configuration, not conversations/documents.
    with SessionLocal() as db:
        source = db.query(AIModel).options(joinedload(AIModel.provider)).filter(AIModel.id == model_id).one()
        model_data = {c.name: getattr(source, c.name) for c in AIModel.__table__.columns}
        provider_data = {c.name: getattr(source.provider, c.name) for c in Provider.__table__.columns}
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    sessions = sessionmaker(bind=engine)
    Base.metadata.create_all(engine)
    scratch = Path(__file__).resolve().parents[2] / f".tmp_provider_{uuid4().hex}"
    scratch.mkdir()
    client = chromadb.PersistentClient(path=str(scratch / "chroma"), settings=Settings(anonymized_telemetry=False))
    collection = client.create_collection("fue_agent_smoke")
    # Keyword retrieval requires no embedding API and sends only this invented text.
    excerpt = "FUE_AGENT_SMOKE：本人工测试文档的验证口令是 ORCHID-742。此内容不包含用户真实资料。"
    with sessions() as db:
        db.add(Provider(**provider_data))
        db.add(AIModel(**model_data))
        db.flush()
        kb = KnowledgeBase(name="Synthetic agent test", collection_name=collection.name, embed_model_id=model_id)
        db.add(kb)
        db.flush()
        doc = DocumentFile(knowledge_base_id=kb.id, original_filename="synthetic-agent-test.txt",
                           file_path="synthetic-agent-test.txt", file_type="txt", file_size=len(excerpt.encode("utf-8")),
                           status="indexed", chunk_count=1)
        db.add(doc)
        db.flush()
        kb_id, doc_id = kb.id, doc.id
        db.commit()
    collection.add(ids=["synthetic-1"], embeddings=[[1.0, 0.0, 0.0]], documents=[excerpt],
                   metadatas=[{"document_file_id": doc_id, "chunk_index": 0, "original_filename": "synthetic-agent-test.txt"}])
    try:
        # Configure storage dependencies only. Models, routes, registry, runner,
        # search tool, Chroma retrieval and citation processing are all real.
        with patch.object(api, "SessionLocal", sessions), patch("knowledge.chroma._client", client):
            plain = await check(model_id, kb_id, rag=False, secrets=secrets, session_factory=sessions)
            if not plain:
                return False
            return await check(model_id, kb_id, rag=True, secrets=secrets, session_factory=sessions, synthetic=True)
    finally:
        engine.dispose()


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-id", type=int, required=True)
    parser.add_argument("--kb-id", type=int, help="Existing KB; requires explicit authorization to send its excerpts")
    parser.add_argument("--synthetic", action="store_true", help="Use invented evidence and isolated storage")
    parser.add_argument("--read-context", action="store_true", help="Require actual neighboring-chunk reading in the live KB test")
    args = parser.parse_args()
    # Suppress vendor request diagnostics; print only the scrubbed summary.
    logging.disable(logging.CRITICAL)
    with SessionLocal() as db:
        secrets = [row.api_key for row in db.query(Provider).all() if row.api_key]
    if args.synthetic:
        return 0 if await synthetic_checks(args.model_id, secrets) else 1
    if args.kb_id is None:
        parser.error("Choose --synthetic or explicitly authorized --kb-id")
    plain = await check(args.model_id, args.kb_id, rag=False, secrets=secrets)
    if not plain:
        return 1
    rag = await check(args.model_id, args.kb_id, rag=True, secrets=secrets, require_context=args.read_context)
    return 0 if plain and rag else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
