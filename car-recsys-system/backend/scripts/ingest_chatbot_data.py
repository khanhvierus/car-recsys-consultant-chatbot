"""Embed gold.vehicles into Qdrant — for chatbot RAG retrieval AND the
recommender's VectorRecaller (shared collection).

Thin wrapper over app.services.chatbot.VehicleEmbeddingIngestor. The same
ingestor is invoked by the Temporal ML workflow (incremental, `--since`).

Usage:
    python scripts/ingest_chatbot_data.py                  # full re-embed
    python scripts/ingest_chatbot_data.py --limit 100      # test slice
    python scripts/ingest_chatbot_data.py --since 2026-05-01T00:00:00
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv  # noqa: E402

load_dotenv()

from sqlalchemy import create_engine  # noqa: E402

from app.core.config import settings                         # noqa: E402
from app.services.chatbot import VehicleEmbeddingIngestor     # noqa: E402

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("ingest")


def main() -> int:
    ap = argparse.ArgumentParser(description="Embed gold.vehicles into Qdrant")
    ap.add_argument("--limit", type=int, default=None,
                    help="cap the number of vehicles (smoke test)")
    ap.add_argument("--since", type=str, default=None,
                    help="ISO timestamp — only embed vehicles crawled after this")
    args = ap.parse_args()

    if not settings.OPENAI_API_KEY:
        log.error("OPENAI_API_KEY is not set — cannot embed.")
        return 1

    from langchain_openai import OpenAIEmbeddings
    from qdrant_client import QdrantClient

    embeddings = OpenAIEmbeddings(model=settings.OPENAI_EMBEDDING_MODEL,
                                  openai_api_key=settings.OPENAI_API_KEY)
    qdrant = QdrantClient(url=settings.QDRANT_URL)
    db_engine = create_engine(settings.DATABASE_URL)

    ingestor = VehicleEmbeddingIngestor(db_engine, embeddings, qdrant)
    result = ingestor.run(since=args.since, limit=args.limit)
    log.info("Done — embedded %d vehicles into Qdrant collection '%s'.",
             result["embedded"], settings.QDRANT_COLLECTION)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
