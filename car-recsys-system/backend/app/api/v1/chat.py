"""Chat API — agentic car-shopping assistant (chatbot_2 LangGraph).

POST /api/v1/chat  {session_id?, message, reset?} -> {session_id, answer}
In-memory per-session history + profile (Cloud Run runs max-instances=1, so a
session stays on one instance). The old gold.chat_* conversation endpoints are
removed — the agentic graph owns session state in memory.
"""
from __future__ import annotations

import logging
import threading
import uuid
from typing import Optional

import anyio
from fastapi import APIRouter, HTTPException, status
from langchain_core.messages import BaseMessage
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)
router = APIRouter()

# Global resources (LLM + Qdrant vector store), built once on first use.
_llm = None
_vector_store = None
_init_lock = threading.Lock()

# In-memory chat history per session_id.
_histories: dict[str, list[BaseMessage]] = {}
_hist_lock = threading.Lock()


def _resources():
    global _llm, _vector_store
    if _llm is None or _vector_store is None:
        with _init_lock:
            if _llm is None or _vector_store is None:
                from app.services.chatbot import initialize_resources
                _llm, _vector_store = initialize_resources()
    return _llm, _vector_store


class ChatRequest(BaseModel):
    session_id: Optional[str] = None
    message: str = Field(..., min_length=1, max_length=5000)
    reset: bool = False


class ChatResponse(BaseModel):
    session_id: str
    answer: str


@router.post("", response_model=ChatResponse)
@router.post("/", response_model=ChatResponse)
async def chat(req: ChatRequest):
    """Run one consultation turn through the agentic graph."""
    try:
        llm, vector_store = _resources()
    except Exception as exc:  # noqa: BLE001 — missing OPENAI_API_KEY / Qdrant unreachable
        logger.error("chatbot init failed: %s", exc)
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                            detail=f"Chatbot unavailable: {exc}")

    session_id = req.session_id or str(uuid.uuid4())

    if req.reset:
        with _hist_lock:
            _histories.pop(session_id, None)
        from app.services.chatbot.user_profile import delete_profile
        delete_profile(session_id)

    with _hist_lock:
        history = list(_histories.get(session_id, []))

    try:
        from app.services.chatbot import generate_response
        answer, updated_history = await anyio.to_thread.run_sync(
            generate_response, llm, vector_store, history, req.message, session_id,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("chat generate_response failed")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail=f"Failed to process message: {exc}")

    with _hist_lock:
        _histories[session_id] = updated_history

    return ChatResponse(session_id=session_id, answer=answer)


@router.get("/health")
async def chat_health():
    """Confirms the chatbot resources can initialize."""
    try:
        _resources()
        return {"status": "healthy", "chatbot": "initialized"}
    except Exception as exc:  # noqa: BLE001
        return {"status": "degraded", "error": str(exc)}
