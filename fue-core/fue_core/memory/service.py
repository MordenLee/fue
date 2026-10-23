"""Durable logs → QA pairs → Chroma. No fixed-character splitting of conversations."""

from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
from datetime import datetime, timezone

from sqlalchemy import or_

from fue_core.conversations.models import Conversation, Message
from fue_core.memory.models import ChatEvent, QAPair
from fue_core.settings.models import Setting, DEFAULTS

logger = logging.getLogger(__name__)
# Desktop backend is a single process. Network embedding never holds this lock.
INDEX_LOCK = threading.RLock()
DELETION_EPOCH = 0
LEXICAL_COLLECTION = "chat_memory"


from fue_core.settings.service import setting


def timestamp(value):
    return int(value.replace(tzinfo=value.tzinfo or timezone.utc).timestamp()) if value else int(time.time())


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def record_conversation(db, conversation_id, action="snapshot"):
    """Called in the SAME transaction as the conversation mutation."""
    db.flush()
    messages = db.query(Message).filter_by(conversation_id=conversation_id).order_by(Message.position, Message.id).all()
    events = db.query(ChatEvent).filter_by(conversation_id=conversation_id).order_by(ChatEvent.sequence).all()
    latest = {e.message_id: e for e in events}
    sequence = max((e.sequence for e in events), default=0)
    for msg in messages:
        payload = {"role": msg.role, "content": msg.content, "position": msg.position,
                   "created_at": timestamp(msg.created_at), "references": msg.references, "model_id": msg.model_id}
        hashed = digest(payload)
        if msg.id not in latest or latest[msg.id].content_hash != hashed:
            sequence += 1
            event = ChatEvent(conversation_id=conversation_id, message_id=msg.id, sequence=sequence,
                              action=action, content_hash=hashed, payload=payload, timestamp=int(time.time()))
            db.add(event)
            latest[msg.id] = event
    if action in {"edit", "regenerate"}:
        sequence += 1
        payload = {"operation": action, "live_message_ids": [m.id for m in messages]}
        db.add(ChatEvent(conversation_id=conversation_id, message_id=0, sequence=sequence,
                         action=action, content_hash=digest([payload, time.time_ns()]),
                         payload=payload, timestamp=int(time.time())))
    db.flush()
    pairs = db.query(QAPair).filter_by(conversation_id=conversation_id).all()
    known = {p.signature: p for p in pairs}
    for pair in pairs:
        pair.active = False
    question, answers = None, []

    def project(user, replies):
        if user is None:
            return
        # Normally one reply. Preserve each regenerated candidate as a separate QA version.
        for reply in replies or [None]:
            signature = digest([user.id, user.content, reply.id if reply else None, reply.content if reply else ""])
            if signature in known:
                known[signature].active = True
            else:
                db.add(QAPair(conversation_id=conversation_id, user_message_id=user.id,
                              assistant_message_id=reply.id if reply else None, position=user.position,
                              timestamp=timestamp(user.created_at), signature=signature,
                              user_event_id=latest[user.id].id, assistant_event_id=latest[reply.id].id if reply else None,
                              state="complete" if reply else "pending",
                              question=latest[user.id].payload["content"],
                              answer=latest[reply.id].payload["content"] if reply else "", active=True))
    for msg in messages:
        if msg.role == "user":
            project(question, answers)
            question, answers = msg, []
        elif msg.role == "assistant" and question is not None:
            answers.append(msg)
    project(question, answers)


def _collections(client):
    return [getattr(c, "name", c) for c in client.list_collections()
            if str(getattr(c, "name", c)) == LEXICAL_COLLECTION or str(getattr(c, "name", c)).startswith("chat_memory_vectors_")]


def commit_chat(db, conversation_id=None, *, action="snapshot", forget_ids=None, forget_conversation=False, forget_all=False):
    """Deletion is synchronous and fails visibly if any index cannot be cleared.

    Holding the lock through COMMIT prevents a late embedding result resurrecting text.
    Deleted logs/versions are removed, not tombstoned with their content retained.
    """
    global DELETION_EPOCH
    with INDEX_LOCK:
        db.flush()
        from fue_core.memory.working import invalidate
        if forget_ids or forget_conversation or forget_all:
            from fue_core.execution import Execution, ExecutionEvent
            executions = db.query(Execution)
            if not forget_all:
                executions = executions.filter_by(conversation_id=conversation_id)
            keys = [r.id for r in executions.all()]
            if keys:
                db.query(ExecutionEvent).filter(ExecutionEvent.run_id.in_(keys)).delete(synchronize_session=False)
                # Retain only a tombstone ID to prevent a delayed retry recreating deleted content.
                executions.update({'result': None, 'state': 'interrupted', 'error': 'Source content deleted'}, synchronize_session=False)
            invalidate(db, None if forget_all else conversation_id, forget=True)
        elif action in {"edit", "regenerate"}:
            invalidate(db, conversation_id)
        if forget_ids or forget_conversation or forget_all:
            pair_query, event_query = db.query(QAPair), db.query(ChatEvent)
            if not forget_all:
                pair_query = pair_query.filter(QAPair.conversation_id == conversation_id)
                event_query = event_query.filter(ChatEvent.conversation_id == conversation_id)
                if not forget_conversation:
                    pair_query = pair_query.filter(or_(QAPair.user_message_id.in_(forget_ids), QAPair.assistant_message_id.in_(forget_ids)))
                    orphan_events = [p.assistant_event_id for p in pair_query.all()
                                     if p.assistant_message_id is None and p.assistant_event_id]
                    event_query = event_query.filter(or_(ChatEvent.message_id.in_(forget_ids), ChatEvent.id.in_(orphan_events)))
            ids = [p.id for p in pair_query.all()]
            if ids:
                from fue_core.knowledge.chroma import get_chroma_client
                client = get_chroma_client()
                for name in _collections(client):
                    for offset in range(0, len(ids), 200):
                        client.get_collection(name).delete(ids=ids[offset:offset + 200])
            pair_query.delete(synchronize_session=False)
            event_query.delete(synchronize_session=False)
        if conversation_id and not forget_conversation:
            record_conversation(db, conversation_id, action)
        db.commit()
        if forget_ids or forget_conversation or forget_all:
            DELETION_EPOCH += 1


def record_interruption(db, conversation_id, content, action, source_user_message_id=None, expected_question=None):
    """Preserve incomplete generated text in the log, outside the live answer chain."""
    with INDEX_LOCK:
        if not db.get(Conversation, conversation_id):
            return
        user = (db.get(Message, source_user_message_id) if source_user_message_id is not None else
                db.query(Message).filter_by(conversation_id=conversation_id, role="user").order_by(Message.position.desc()).first())
        if not user or user.conversation_id != conversation_id or (expected_question is not None and user.content != expected_question):
            return
        record_conversation(db, conversation_id, action)
        event = ChatEvent(conversation_id=conversation_id, message_id=0,
                          sequence=(db.query(ChatEvent).filter_by(conversation_id=conversation_id).count() + 1),
                          action=action, content_hash=digest([action, content, time.time_ns()]),
                          payload={"role": "assistant", "content": content, "state": action}, timestamp=int(time.time()))
        db.add(event)
        db.flush()
        db.add(QAPair(conversation_id=conversation_id, user_message_id=user.id, assistant_message_id=None,
                      position=user.position, timestamp=timestamp(user.created_at), signature=event.content_hash,
                      assistant_event_id=event.id, state=action, question=user.content, answer=content, active=False))
        db.commit()


def backfill(session_factory):
    """Backfill existing chats without modifying their original timestamps/content."""
    with session_factory() as db:
        ids = [r[0] for r in db.query(Conversation.id).all()]
    for conv_id in ids:
        with session_factory() as db:
            with INDEX_LOCK:
                if db.get(Conversation, conv_id):
                    record_conversation(db, conv_id, "import")
                    db.commit()


def text(pair):
    return f"User:\n{pair.question}\n\nAssistant:\n{pair.answer}"


def embedding_model(db):
    from fue_core.providers.models import AIModel
    raw = setting(db, "memory_embed_model_id") or setting(db, "default_embed_model_id")
    model = db.get(AIModel, int(raw)) if raw else None
    if model and model.model_type == "embedding" and model.is_enabled and model.provider.is_enabled:
        return model
    return None


def process_pending(session_factory, limit=16):
    """Local full-text indexing always runs; semantic indexing is optional and retryable."""
    from fue_core.knowledge.chroma import get_chroma_client
    from fue_core.providers.embeddings import build_embedder
    client = get_chroma_client()
    with session_factory() as db:
        pending = db.query(QAPair).filter_by(lexical_indexed=False).limit(limit).all()
        for pair in pending:
            pair_id = pair.id
            with INDEX_LOCK:
                db.refresh(pair)
                collection = client.get_or_create_collection(LEXICAL_COLLECTION, embedding_function=None)
                collection.upsert(ids=[pair.id], documents=[text(pair)], embeddings=[[0.0]], metadatas=[{
                    "conversation_id": pair.conversation_id, "timestamp": pair.timestamp,
                    "position": pair.position, "signature": pair.signature}])
                pair.lexical_indexed = True
                db.commit()
        model = embedding_model(db)
        if model is None:
            return len(pending)
        model_id = model.id
        embedder = build_embedder(model, timeout_seconds=45)
        pending_vectors = db.query(QAPair).filter(or_(QAPair.vector_model_id.is_(None), QAPair.vector_model_id != model_id),
                                                 QAPair.index_error.is_(None)).limit(limit).all()
        snapshots = [(p.id, p.signature, text(p)) for p in pending_vectors]
    if not snapshots:
        return len(pending)
    # Full QA pairs are embedding units. Oversized/API failures remain searchable lexically.
    for pair_id, signature, content in snapshots:
        try:
            vector = embedder.embed_query(content)
            with INDEX_LOCK, session_factory() as db:
                pair = db.get(QAPair, pair_id)
                current_model = embedding_model(db)
                if pair is None or pair.signature != signature or current_model is None or current_model.id != model_id:
                    continue
                collection = client.get_or_create_collection(f"chat_memory_vectors_{model_id}", embedding_function=None)
                collection.upsert(ids=[pair_id], documents=[content], embeddings=[vector], metadatas=[{
                    "conversation_id": pair.conversation_id, "timestamp": pair.timestamp, "signature": signature}])
                pair.vector_model_id, pair.index_error = model_id, None
                db.commit()
        except Exception as exc:
            with INDEX_LOCK, session_factory() as db:
                pair = db.get(QAPair, pair_id)
                if pair:
                    # Store only exception class, never provider response/credentials/history.
                    pair.index_error = type(exc).__name__
                    db.commit()
            logger.warning("Chat memory vector indexing failed (%s)", type(exc).__name__)
    return len(pending) + len(snapshots)



def cutoff(db, requested_days=None):
    scope = setting(db, "memory_query_scope")
    if scope == "disabled":
        raise PermissionError("Chat history access is disabled")
    days = None if scope == "all" else int(scope)
    if requested_days:
        days = min(days, requested_days) if days else requested_days
    return int(time.time()) - days * 86400 if days else 0


def eligible(db, requested_days=None):
    return db.query(QAPair).filter(QAPair.timestamp >= cutoff(db, requested_days))


def preview(pair, db):
    conv = db.get(Conversation, pair.conversation_id)
    return {"pair_id": pair.id, "conversation_id": pair.conversation_id,
            "title": conv.title if conv else "", "timestamp": pair.timestamp,
            "position": pair.position, "active": pair.active, "state": pair.state, "complete": pair.state == "complete",
            "question": pair.question[:250], "answer_preview": pair.answer[:450],
            "source": f"chat:{pair.id}"}


def search(db, query, *, mode="keyword", top_n=5, days=None, conversation_id=None, offset=0, start_time=None, end_time=None):
    from fue_core.knowledge.chroma import get_chroma_client
    base = eligible(db, days)
    if conversation_id is not None:
        base = base.filter_by(conversation_id=conversation_id)
    if start_time is not None:
        base = base.filter(QAPair.timestamp >= start_time)
    if end_time is not None:
        base = base.filter(QAPair.timestamp <= end_time)
    terms = list(dict.fromkeys(query.strip().split()))[:12]
    if not terms:
        rows = base.order_by(QAPair.timestamp, QAPair.position, QAPair.id).offset(offset).limit(top_n + 1).all()
        return {"mode": "timeline", "results": [preview(p, db) for p in rows[:top_n]],
                "next_offset": offset + top_n if len(rows) > top_n else None}
    if setting(db, "memory_query_mode") == "keyword":
        mode = "keyword"
    candidates = {}
    # SQL fallback covers new pairs before Chroma indexing; both query the same QA projection.
    if mode in ("keyword", "hybrid"):
        client = get_chroma_client()
        if LEXICAL_COLLECTION in _collections(client):
            where_doc = {"$contains": terms[0]} if len(terms) == 1 else {"$or": [{"$contains": t} for t in terms]}
            raw = client.get_collection(LEXICAL_COLLECTION).get(
                where={"timestamp": {"$gte": cutoff(db, days)}}, where_document=where_doc,
                include=["metadatas"], limit=100)
            for pair_id in raw["ids"]:
                pair = base.filter(QAPair.id == pair_id).first()
                if pair:
                    rank = sum((pair.question + pair.answer).lower().count(t.lower()) for t in terms)
                    candidates[pair.id] = (rank, pair)
        conditions = [or_(QAPair.question.contains(t, autoescape=True), QAPair.answer.contains(t, autoescape=True)) for t in terms]
        rows = base.filter(or_(*conditions)).order_by(QAPair.timestamp.desc()).limit(100).all()
        for pair in rows:
            rank = sum((pair.question + pair.answer).lower().count(t.lower()) for t in terms)
            candidates[pair.id] = (rank, pair)
    if mode in ("vector", "hybrid"):
        from fue_core.providers.embeddings import build_embedder
        model = embedding_model(db)
        if model is None:
            raise ValueError("Configure a memory embedding model before semantic search")
        client = get_chroma_client()
        name = f"chat_memory_vectors_{model.id}"
        if name in _collections(client):
            collection = client.get_collection(name)
            if collection.count():
                filters = [{"timestamp": {"$gte": max(cutoff(db, days), start_time or 0)}}]
                if end_time is not None:
                    filters.append({"timestamp": {"$lte": end_time}})
                if conversation_id is not None:
                    filters.append({"conversation_id": conversation_id})
                where = filters[0] if len(filters) == 1 else {"$and": filters}
                result = collection.query(query_embeddings=[build_embedder(model, timeout_seconds=20).embed_query(query)],
                                          n_results=min(top_n * 3, 30), where=where, include=["distances"])
                for index, pair_id in enumerate(result["ids"][0]):
                    pair = base.filter(QAPair.id == pair_id).first()
                    if pair:
                        candidates.setdefault(pair.id, (1 / (index + 1), pair))
    ranked = sorted(candidates.values(), key=lambda entry: (entry[0], entry[1].active, entry[1].timestamp), reverse=True)
    rows = ranked[offset:offset + top_n]
    return {"mode": mode, "results": [preview(pair, db) for _, pair in rows],
            "next_offset": offset + top_n if len(ranked) > offset + top_n else None}


def read_chat(db, pair_id, before=0, after=0, offset=0, length=2000):
    pair = eligible(db).filter(QAPair.id == pair_id).first()
    if not pair:
        raise PermissionError("Pair is outside the allowed history range or was deleted")
    rows = eligible(db).filter(QAPair.conversation_id == pair.conversation_id, QAPair.active.is_(True)).all()
    rows = sorted(rows, key=lambda p: (p.position, p.timestamp, p.id))
    earlier = [p for p in rows if p.position < pair.position][-before:] if before else []
    later = [p for p in rows if p.position > pair.position][:after]
    selected = [*earlier, pair, *later]
    content = "\n\n".join(f"[chat:{p.id}] {text(p)}" for p in selected)
    return {"source": "chat", "pair_id": pair_id, "text": content[offset:offset + length],
            "total_chars": len(content), "next_offset": offset + length if offset + length < len(content) else None,
            "pairs": [{"pair_id": p.id, "position": p.position, "timestamp": p.timestamp,
                       "active": p.active, "state": p.state, "source": f"chat:{p.id}"} for p in selected]}
