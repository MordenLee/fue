"""CRUD API for Conversations and Messages."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from database import get_db
from conversations.models import (
    Conversation,
    ConversationCreate,
    ConversationDetail,
    ConversationOut,
    ConversationSearchResult,
    ConversationUpdate,
    MatchedMessage,
    Message,
    MessageAppend,
    MessageOut,
)

router = APIRouter(prefix="/api/conversations", tags=["conversations"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _escape_like(s: str) -> str:
    """Escape SQL LIKE wildcard characters."""
    return s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _get_conv(conv_id: int, db: Session) -> Conversation:
    conv = db.get(Conversation, conv_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conv


def _to_out(conv: Conversation) -> dict:
    return {
        "id": conv.id,
        "title": conv.title,
        "summary": conv.summary,
        "model_id": conv.model_id,
        "kb_ids": conv.kb_ids,
        "citation_style": conv.citation_style,
        "folder_id": conv.folder_id,
        "created_at": conv.created_at,
        "updated_at": conv.updated_at,
        "message_count": len(conv.messages) if conv.messages else 0,
    }


# ---------------------------------------------------------------------------
# Conversation CRUD
# ---------------------------------------------------------------------------

@router.get("", response_model=list[ConversationOut])
def list_conversations(
    skip: int = Query(default=0, ge=0, description="跳过条数 / Offset"),
    limit: int = Query(default=50, ge=1, le=200, description="每页条数 / Page size"),
    db: Session = Depends(get_db),
):
    """List all conversations ordered by most recently updated."""
    convs = (
        db.query(Conversation)
        .order_by(Conversation.updated_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return [_to_out(c) for c in convs]


@router.get("/search", response_model=list[ConversationSearchResult])
def search_conversations(
    q: str = Query(..., min_length=1, description="Search query"),
    db: Session = Depends(get_db),
):
    """Full-text search across conversation titles, summaries, and message content.

    Returns conversations that match *q* in any of:
    - title
    - summary
    - any message content

    Results are ordered by last-updated descending.
    Each result includes up to 5 matching message snippets (200 chars around the match).
    """
    like_q = f"%{_escape_like(q)}%"

    # Find conversation IDs that match via title/summary
    conv_ids_meta = {
        row.id
        for row in db.query(Conversation.id).filter(
            or_(
                Conversation.title.ilike(like_q, escape="\\"),
                Conversation.summary.ilike(like_q, escape="\\"),
            )
        ).all()
    }

    # Find conversation IDs that match via message content
    msg_matches = (
        db.query(Message)
        .filter(Message.content.ilike(like_q, escape="\\"))
        .order_by(Message.conversation_id, Message.position)
        .all()
    )
    conv_ids_msg: dict[int, list[Message]] = {}
    for msg in msg_matches:
        conv_ids_msg.setdefault(msg.conversation_id, []).append(msg)

    all_ids = conv_ids_meta | conv_ids_msg.keys()
    if not all_ids:
        return []

    convs = (
        db.query(Conversation)
        .filter(Conversation.id.in_(all_ids))
        .order_by(Conversation.updated_at.desc())
        .all()
    )

    results: list[ConversationSearchResult] = []
    for conv in convs:
        matched_msgs: list[MatchedMessage] = []
        for msg in conv_ids_msg.get(conv.id, [])[:5]:
            idx = msg.content.lower().find(q.lower())
            start = max(0, idx - 80)
            end = min(len(msg.content), idx + len(q) + 80)
            snippet = msg.content[start:end]
            if start > 0:
                snippet = "…" + snippet
            if end < len(msg.content):
                snippet = snippet + "…"
            matched_msgs.append(MatchedMessage(
                message_id=msg.id,
                role=msg.role,
                snippet=snippet,
                position=msg.position,
            ))

        results.append(ConversationSearchResult(
            conversation=ConversationOut(**_to_out(conv)),
            matched_in_title=bool(conv.title and q.lower() in conv.title.lower()),
            matched_in_summary=bool(conv.summary and q.lower() in conv.summary.lower()),
            matched_messages=matched_msgs,
        ))

    return results


@router.post("", response_model=ConversationOut, status_code=status.HTTP_201_CREATED)
def create_conversation(payload: ConversationCreate, db: Session = Depends(get_db)):
    """Create a new empty conversation."""
    conv = Conversation(**payload.model_dump())
    db.add(conv)
    db.commit()
    db.refresh(conv)
    return _to_out(conv)


@router.get("/{conv_id}", response_model=ConversationDetail)
def get_conversation(conv_id: int, db: Session = Depends(get_db)):
    """Get a conversation with all its messages."""
    conv = _get_conv(conv_id, db)
    return {
        **_to_out(conv),
        "messages": conv.messages,
    }


@router.patch("/{conv_id}", response_model=ConversationOut)
def update_conversation(
    conv_id: int,
    payload: ConversationUpdate,
    db: Session = Depends(get_db),
):
    """Update title, summary, model_id, kb_ids, or citation_style."""
    conv = _get_conv(conv_id, db)
    updates = payload.model_dump(exclude_unset=True)
    for key, value in updates.items():
        setattr(conv, key, value)
    db.commit()
    db.refresh(conv)
    return _to_out(conv)


@router.delete("/{conv_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_conversation(conv_id: int, db: Session = Depends(get_db)):
    """Delete a conversation and all its messages."""
    conv = _get_conv(conv_id, db)
    db.delete(conv)
    db.commit()


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
def clear_all_conversations(db: Session = Depends(get_db)):
    """Delete ALL conversations (irreversible). Used for a clean-slate reset."""
    db.query(Conversation).delete()
    db.commit()


# ---------------------------------------------------------------------------
# Messages
# ---------------------------------------------------------------------------

@router.get("/{conv_id}/messages", response_model=list[MessageOut])
def list_messages(conv_id: int, db: Session = Depends(get_db)):
    """Return all messages in a conversation ordered by position."""
    _get_conv(conv_id, db)  # 404 guard
    return (
        db.query(Message)
        .filter(Message.conversation_id == conv_id)
        .order_by(Message.position)
        .all()
    )


@router.post(
    "/{conv_id}/messages",
    response_model=list[MessageOut],
    status_code=status.HTTP_201_CREATED,
)
def append_messages(
    conv_id: int,
    payload: MessageAppend,
    db: Session = Depends(get_db),
):
    """Append one or more messages to the conversation.

    The position is assigned automatically as max(existing) + 1, + 2, …
    Typically called with a user+assistant pair after each chat turn.
    """
    conv = _get_conv(conv_id, db)

    # Determine next position
    max_pos = (
        db.query(func.max(Message.position))
        .filter(Message.conversation_id == conv_id)
        .scalar()
    )
    next_pos = (max_pos + 1) if max_pos is not None else 0

    created: list[Message] = []
    for i, msg_in in enumerate(payload.messages):
        msg = Message(
            conversation_id=conv_id,
            role=msg_in.role,
            content=msg_in.content,
            references=msg_in.references,
            position=next_pos + i,
        )
        db.add(msg)
        created.append(msg)

    # Bump conversation.updated_at so it floats to the top of the list
    conv.updated_at = func.now()  # type: ignore[assignment]

    db.commit()
    for msg in created:
        db.refresh(msg)
    return created


@router.delete("/{conv_id}/messages/{msg_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_message(conv_id: int, msg_id: int, db: Session = Depends(get_db)):
    """Delete a single message. Positions of remaining messages are unchanged."""
    _get_conv(conv_id, db)  # 404 guard
    msg = db.query(Message).filter(
        Message.id == msg_id, Message.conversation_id == conv_id
    ).first()
    if not msg:
        raise HTTPException(status_code=404, detail="Message not found")
    db.delete(msg)
    db.commit()


@router.delete("/{conv_id}/messages/{msg_id}/after", status_code=status.HTTP_204_NO_CONTENT)
def delete_message_and_after(conv_id: int, msg_id: int, db: Session = Depends(get_db)):
    """Delete a message and all messages after it (by position)."""
    _get_conv(conv_id, db)
    msg = db.query(Message).filter(
        Message.id == msg_id, Message.conversation_id == conv_id
    ).first()
    if not msg:
        raise HTTPException(status_code=404, detail="Message not found")
    db.query(Message).filter(
        Message.conversation_id == conv_id,
        Message.position >= msg.position,
    ).delete()
    db.commit()


@router.patch("/{conv_id}/messages/{msg_id}", response_model=MessageOut)
def update_message(conv_id: int, msg_id: int, payload: dict, db: Session = Depends(get_db)):
    """Update the content of a single message."""
    _get_conv(conv_id, db)
    msg = db.query(Message).filter(
        Message.id == msg_id, Message.conversation_id == conv_id
    ).first()
    if not msg:
        raise HTTPException(status_code=404, detail="Message not found")
    if "content" in payload:
        msg.content = payload["content"]
    db.commit()
    db.refresh(msg)
    return msg


@router.delete("/{conv_id}/messages", status_code=status.HTTP_204_NO_CONTENT)
def clear_messages(conv_id: int, db: Session = Depends(get_db)):
    """Delete all messages in a conversation (keeps the conversation record)."""
    _get_conv(conv_id, db)
    db.query(Message).filter(Message.conversation_id == conv_id).delete()
    db.commit()
