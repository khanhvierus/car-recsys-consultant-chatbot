"""Chat API — RAG car-shopping assistant.

Backed by app.services.chatbot.Chatbot (hybrid retrieval + grounded
generation). The chatbot owns session + message persistence
(gold.chat_sessions / gold.chat_messages), so these endpoints stay thin.

The public field name `conversation_id` is kept for frontend compatibility;
internally it is the gold.chat_sessions id.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user_id_optional

logger = logging.getLogger(__name__)
router = APIRouter()


# --------------------------------------------------------------------------
# request / response models
# --------------------------------------------------------------------------

class ChatMessageRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=5000)
    conversation_id: Optional[str] = None


class ChatMessageResponse(BaseModel):
    conversation_id: str
    message_id: str = ""
    response: str
    vehicles: List[Dict[str, Any]] = []
    constraints: Dict[str, Any] = {}
    timestamp: str


class ConversationResponse(BaseModel):
    conversation_id: str
    user_id: Optional[str]
    created_at: Optional[str]
    updated_at: Optional[str]
    message_count: int
    preview: Optional[str] = None


class MessageResponse(BaseModel):
    id: str
    conversation_id: str
    role: str
    content: str
    created_at: Optional[str]
    vehicles: List[Dict[str, Any]] = []


# --------------------------------------------------------------------------
# endpoints
# --------------------------------------------------------------------------

@router.post("/message", response_model=ChatMessageResponse)
async def send_message(
    request: ChatMessageRequest,
    user_id: Optional[str] = Depends(get_current_user_id_optional),
    db: Session = Depends(get_db),
):
    """Send a message; get a grounded answer + vehicle cards."""
    try:
        from app.services.chatbot import initialize_chatbot

        bot = initialize_chatbot()
        result = bot.chat(
            user_input=request.message,
            session_id=request.conversation_id,
            user_id=user_id,
        )
        return ChatMessageResponse(
            conversation_id=result["session_id"],
            response=result["response"],
            vehicles=result.get("vehicles", []),
            constraints=result.get("constraints", {}),
            timestamp=datetime.utcnow().isoformat(),
        )
    except ValueError as exc:
        # Missing OPENAI_API_KEY etc.
        logger.error("Chatbot misconfigured: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("Chat error")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process message: {exc}",
        )


@router.get("/conversations", response_model=List[ConversationResponse])
async def get_conversations(
    user_id: Optional[str] = Depends(get_current_user_id_optional),
    limit: int = 20,
    db: Session = Depends(get_db),
):
    """List a user's chat sessions (most recent first)."""
    if not user_id:
        return []
    try:
        rows = db.execute(
            text("""
                SELECT s.id, s.user_id, s.created_at, s.updated_at,
                       COUNT(m.id) AS message_count,
                       (SELECT content FROM gold.chat_messages
                        WHERE session_id = s.id
                        ORDER BY created_at DESC, id DESC LIMIT 1) AS preview
                FROM gold.chat_sessions s
                LEFT JOIN gold.chat_messages m ON m.session_id = s.id
                WHERE s.user_id = :uid::uuid
                GROUP BY s.id
                ORDER BY s.updated_at DESC
                LIMIT :limit
            """),
            {"uid": user_id, "limit": limit},
        )
        out: List[ConversationResponse] = []
        for r in rows:
            preview = r[5]
            if preview and len(preview) > 100:
                preview = preview[:100] + "..."
            out.append(ConversationResponse(
                conversation_id=str(r[0]),
                user_id=str(r[1]) if r[1] else None,
                created_at=r[2].isoformat() if r[2] else None,
                updated_at=r[3].isoformat() if r[3] else None,
                message_count=r[4] or 0,
                preview=preview,
            ))
        return out
    except Exception as exc:  # noqa: BLE001
        logger.error("Error listing conversations: %s", exc)
        return []


@router.get("/conversation/{conversation_id}", response_model=List[MessageResponse])
async def get_conversation_messages(
    conversation_id: str,
    user_id: Optional[str] = Depends(get_current_user_id_optional),
    limit: int = 100,
    db: Session = Depends(get_db),
):
    """All messages in a chat session, oldest first."""
    try:
        rows = db.execute(
            text("""
                SELECT id, role, content, vehicles, created_at
                FROM gold.chat_messages
                WHERE session_id = :sid::uuid
                ORDER BY created_at ASC, id ASC
                LIMIT :limit
            """),
            {"sid": conversation_id, "limit": limit},
        )
        return [
            MessageResponse(
                id=str(r[0]),
                conversation_id=conversation_id,
                role=r[1],
                content=r[2],
                created_at=r[4].isoformat() if r[4] else None,
                vehicles=r[3] or [],
            )
            for r in rows
        ]
    except Exception as exc:  # noqa: BLE001
        logger.error("Error getting messages: %s", exc)
        return []


@router.delete("/conversation/{conversation_id}")
async def delete_conversation(
    conversation_id: str,
    user_id: Optional[str] = Depends(get_current_user_id_optional),
    db: Session = Depends(get_db),
):
    """Delete a chat session (messages cascade)."""
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    try:
        row = db.execute(
            text("SELECT user_id FROM gold.chat_sessions WHERE id = :sid::uuid"),
            {"sid": conversation_id},
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Conversation not found")
        if str(row[0]) != user_id:
            raise HTTPException(status_code=403, detail="Not authorized")
        db.execute(
            text("DELETE FROM gold.chat_sessions WHERE id = :sid::uuid"),
            {"sid": conversation_id},
        )
        db.commit()
        return {"message": "Conversation deleted"}
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.error("Error deleting conversation: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/health")
async def chat_health():
    """Health check — confirms the chatbot can initialize."""
    try:
        from app.services.chatbot import initialize_chatbot

        initialize_chatbot()
        return {"status": "healthy", "chatbot": "initialized"}
    except Exception as exc:  # noqa: BLE001
        return {"status": "degraded", "error": str(exc)}
