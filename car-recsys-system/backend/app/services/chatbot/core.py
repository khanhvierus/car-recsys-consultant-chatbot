"""Chatbot orchestrator — ties memory, hybrid retrieval and grounded
generation into one RAG turn.

    load history → condense follow-up → hybrid retrieve → generate (grounded)
                 → persist turn → return answer + vehicle cards

Replaces the old single-vector-search core. The unused Temporal `workflows.py`
has been removed — this is a clean synchronous flow.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Optional

from sqlalchemy import create_engine

from app.core.config import settings

from .config import CHATBOT_CONFIG
from .generation import ResponseGenerator
from .memory import ConversationMemory
from .retrieval import HybridRetriever, RetrievedVehicle

log = logging.getLogger(__name__)


def _vehicle_card(v: RetrievedVehicle) -> dict[str, Any]:
    """Compact card returned to the frontend for inline rendering."""
    p = v.payload
    return {
        "vehicle_id": v.vehicle_id,
        "title": p.get("title") or p.get("car_name"),
        "brand": p.get("brand"),
        "price": p.get("price"),
        "mileage": p.get("mileage"),
        "fuel_type": p.get("fuel_type"),
        "new_used": p.get("new_used"),
        "car_rating": p.get("car_rating"),
        "image_url": p.get("primary_image_url"),
        "relevance": round(v.rrf_score, 4),
    }


class Chatbot:
    """One instance per process; cheap per-request methods."""

    def __init__(self, llm: Any, embeddings: Any, qdrant_client: Any, db_engine: Any):
        self.llm = llm
        self.cfg = CHATBOT_CONFIG
        self.retriever = HybridRetriever(db_engine, embeddings, qdrant_client)
        self.generator = ResponseGenerator(llm)
        self.memory = ConversationMemory(db_engine, llm)

    def chat(
        self,
        user_input: str,
        session_id: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """Run one RAG turn. Returns answer + vehicle cards + session id."""
        session_id = self.memory.ensure_session(session_id, user_id)
        history = self.memory.build_context(session_id)

        # Follow-up → standalone search query (carries earlier constraints).
        search_query = self.generator.condense_question(history, user_input)

        # Hybrid retrieval (vector + SQL, RRF-fused).
        vehicles, constraints = self.retriever.retrieve(search_query)

        # Grounded generation.
        answer = self.generator.generate(history, user_input, vehicles, constraints)

        cards = [_vehicle_card(v) for v in vehicles]

        # Persist the turn.
        self.memory.append(session_id, "user", user_input)
        self.memory.append(session_id, "assistant", answer, vehicles=cards)

        return {
            "session_id": session_id,
            "response": answer,
            "vehicles": cards,
            "constraints": {
                "price_min": constraints.price_min,
                "price_max": constraints.price_max,
                "brand": constraints.brand,
                "new_used": constraints.new_used,
                "fuel_type": constraints.fuel_type,
                "year": constraints.year,
            },
        }


# --------------------------------------------------------------------------
# singleton factory
# --------------------------------------------------------------------------

_chatbot: Optional[Chatbot] = None


def initialize_chatbot() -> Chatbot:
    """Build (once) and return the process-wide Chatbot."""
    global _chatbot
    if _chatbot is not None:
        return _chatbot

    api_key = os.getenv("OPENAI_API_KEY") or settings.OPENAI_API_KEY
    if not api_key:
        raise ValueError("OPENAI_API_KEY is required for the chatbot")

    from langchain_openai import ChatOpenAI, OpenAIEmbeddings
    from qdrant_client import QdrantClient

    embeddings = OpenAIEmbeddings(model=CHATBOT_CONFIG.embedding_model,
                                  openai_api_key=api_key)
    llm = ChatOpenAI(model=CHATBOT_CONFIG.llm_model,
                     temperature=CHATBOT_CONFIG.temperature,
                     openai_api_key=api_key)
    qdrant = QdrantClient(url=settings.QDRANT_URL, api_key=settings.QDRANT_API_KEY or None)
    db_engine = create_engine(settings.DATABASE_URL, pool_size=5, max_overflow=10)

    _chatbot = Chatbot(llm=llm, embeddings=embeddings,
                       qdrant_client=qdrant, db_engine=db_engine)
    log.info("Chatbot initialized (hybrid retrieval + grounded generation)")
    return _chatbot
