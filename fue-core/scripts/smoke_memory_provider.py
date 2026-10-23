"""Live model → MCP history search → contextual reading, using only synthetic QA data."""
import asyncio
import json
import logging
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import chromadb
from chromadb.config import Settings
from sqlalchemy import create_engine
from sqlalchemy.orm import joinedload, sessionmaker
from sqlalchemy.pool import StaticPool
from fue_core.database import Base, SessionLocal
from fue_core.providers.models import AIModel, Provider
from fue_core.conversations.models import Conversation, MessageAppend, MessageCreate
from fue_core.conversations.router import append_messages
from fue_core.chat import service as api
from fue_core.chat.router import router as _registered_chat_router
from fue_core.memory.service import process_pending
from fue_core.settings.models import Setting
from fue_core import knowledge


async def main():
    logging.disable(logging.CRITICAL)
    with SessionLocal() as db:
        model = db.query(AIModel).options(joinedload(AIModel.provider)).filter_by(id=32).one()
        model_data = {c.name: getattr(model, c.name) for c in AIModel.__table__.columns}
        provider_data = {c.name: getattr(model.provider, c.name) for c in Provider.__table__.columns}
        secrets = [p.api_key for p in db.query(Provider).all() if p.api_key]
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    sessions = sessionmaker(bind=engine)
    Base.metadata.create_all(engine)
    client = chromadb.EphemeralClient(settings=Settings(anonymized_telemetry=False))
    with sessions() as db:
        db.add(Provider(**provider_data))
        db.add(AIModel(**model_data))
        db.add_all([Setting(key="memory_query_scope", value="all"), Setting(key="memory_query_mode", value="keyword")])
        conv = Conversation(title="Synthetic MCP book")
        db.add(conv)
        db.commit()
        append_messages(conv.id, MessageAppend(messages=[
            MessageCreate(role="user", content="Preparation"), MessageCreate(role="assistant", content="PREVIOUS-MARKER"),
            MessageCreate(role="user", content="FUE_QA_SMOKE secret location"),
            MessageCreate(role="assistant", content=("padding " * 160) + "The validation token is ORCHID-742."),
            MessageCreate(role="user", content="Review"), MessageCreate(role="assistant", content="NEXT-MARKER")]), db)
    try:
        with patch.object(api, "SessionLocal", sessions), patch("fue_core.knowledge.chroma.get_chroma_client", return_value=client):
            process_pending(sessions)
            payload = api.ChatRequest(messages=[api.ChatMessage(role="user", content=(
                "This is a synthetic history test. First search_chat_history for FUE_QA_SMOKE. "
                "Then use read_context on the returned pair_id with before=1, after=1, length=4000. "
                "Report the hidden validation token and both neighboring answer markers, citing the chat source. "
                "Do not guess from the preview; the token is beyond the preview."))])
            calls, answer, errors = [], None, []
            with sessions() as db:
                response = await api.chat_stream(32, payload, db)
                async for frame in response.body_iterator:
                    if frame.startswith("data: [TOOL_CALL] "):
                        calls.append(json.loads(frame[len("data: [TOOL_CALL] "):].strip()))
                    elif frame.startswith("data: [REPLACE] "):
                        answer = json.loads(frame[len("data: [REPLACE] "):].strip())
                    elif frame.startswith("data: [ERROR] "):
                        errors.append(frame[len("data: [ERROR] "):].strip())
            names = [c["name"] for c in calls]
            passed = bool(answer and not errors and "search_chat_history" in names and "read_context" in names and
                          all(marker in answer for marker in ["ORCHID-742", "PREVIOUS-MARKER", "NEXT-MARKER"]))
            output = json.dumps({"passed": passed, "tools": names, "answer": answer, "errors": errors}, ensure_ascii=True)
            for secret in secrets:
                output = output.replace(secret, "[REDACTED]")
            print(output, flush=True)
            return 0 if passed else 1
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
