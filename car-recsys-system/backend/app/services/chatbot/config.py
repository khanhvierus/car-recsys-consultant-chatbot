"""Chatbot configuration — every tunable in one place (was scattered as magic
numbers across core.py: collection name, 3072 dim, the arbitrary 0.3 threshold,
temperature 0.5, the 10-message truncation)."""

from __future__ import annotations

from dataclasses import dataclass

from app.core.config import settings


@dataclass(frozen=True, slots=True)
class ChatbotConfig:
    # Qdrant
    qdrant_collection: str = settings.QDRANT_COLLECTION
    embedding_model: str = settings.OPENAI_EMBEDDING_MODEL
    embedding_dim: int = settings.OPENAI_EMBEDDING_DIM

    # LLM
    llm_model: str = settings.OPENAI_MODEL
    temperature: float = 0.3          # lower than the old 0.5 — less drift from facts

    # Hybrid retrieval
    vector_top_k: int = 20            # candidates from Qdrant vector search
    sql_top_k: int = 20               # candidates from the structured SQL filter
    rrf_k: int = 60                   # RRF constant (standard default)
    final_top_k: int = 6              # vehicles passed to the LLM as grounding

    # Conversation memory
    max_history_turns: int = 8        # turns kept verbatim before summarizing
    summary_trigger_turns: int = 12   # summarize once history exceeds this


CHATBOT_CONFIG = ChatbotConfig()
