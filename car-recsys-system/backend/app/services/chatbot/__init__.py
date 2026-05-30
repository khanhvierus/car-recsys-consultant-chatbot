"""RAG chatbot — hybrid retrieval (vector + SQL, RRF-fused) + grounded generation.

Public API:
    from app.services.chatbot import Chatbot, initialize_chatbot

    bot = initialize_chatbot()
    result = bot.chat(user_input, session_id=..., user_id=...)
    # -> {session_id, response, vehicles, constraints}
"""

from .config import CHATBOT_CONFIG
from .core import Chatbot, initialize_chatbot
from .ingest import VehicleEmbeddingIngestor

__all__ = ["Chatbot", "initialize_chatbot", "VehicleEmbeddingIngestor", "CHATBOT_CONFIG"]
