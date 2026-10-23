"""Stable HTTP adapters for the chat service."""
from fastapi import Depends
from sqlalchemy.orm import Session
from fue_core.database import get_db
from .service import router, ChatRequest, ChatResponse, RAGChatRequest, RAGChatResponse, _respond, _stream_response

@router.post("/{model_id}", response_model=ChatResponse)
async def chat(model_id: int, payload: ChatRequest, db: Session = Depends(get_db)):
    from fue_core.execution import respond
    return await respond(model_id, payload, db, False, _respond)


@router.post("/{model_id}/stream")
async def chat_stream(model_id: int, payload: ChatRequest, db: Session = Depends(get_db)):
    return _stream_response(model_id, payload, db, rag=False)


@router.post("/{model_id}/rag", response_model=RAGChatResponse)
async def chat_rag(model_id: int, payload: RAGChatRequest, db: Session = Depends(get_db)):
    from fue_core.execution import respond
    return await respond(model_id, payload, db, True, _respond)


@router.post("/{model_id}/rag/stream")
async def chat_rag_stream(model_id: int, payload: RAGChatRequest, db: Session = Depends(get_db)):
    return _stream_response(model_id, payload, db, rag=True)
