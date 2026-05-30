"""Feature assembly — merge recaller outputs + vehicle attributes into the
per-candidate feature vectors the ranker scores.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

log = logging.getLogger(__name__)


@dataclass(slots=True)
class Candidate:
    """A scored recommendation candidate carried through ranking + re-ranking."""

    vehicle_id: str
    # stage-1 recaller signals (each normalized 0..1)
    cf_score: float = 0.0
    content_score: float = 0.0
    vector_score: float = 0.0
    popularity: float = 0.0
    # attributes (filled by FeatureAssembler from gold.vehicles)
    brand: Optional[str] = None
    car_model: Optional[str] = None
    price: Optional[float] = None
    # derived ranking features (0..1)
    model_rating: float = 0.0
    price_fit: float = 1.0
    recency: float = 0.5
    # final
    rank_score: float = 0.0
    sources: list[str] = field(default_factory=list)

    def feature_dict(self) -> dict[str, float]:
        return {
            "cf_score": self.cf_score,
            "content_score": self.content_score,
            "vector_score": self.vector_score,
            "popularity": self.popularity,
            "price_fit": self.price_fit,
            "model_rating": self.model_rating,
            "recency": self.recency,
        }


class FeatureAssembler:
    """Builds Candidate objects: unions recaller outputs, then enriches with
    vehicle attributes and derives price_fit / model_rating / recency.
    """

    def __init__(self, db: Session):
        self.db = db

    def assemble(
        self,
        recaller_outputs: dict[str, dict[str, float]],
        budget: Optional[float] = None,
        pool_size: int = 300,
    ) -> list[Candidate]:
        # 1. Union all candidate ids with per-source scores.
        cand: dict[str, Candidate] = {}
        for source, scores in recaller_outputs.items():
            for vid, score in scores.items():
                c = cand.get(vid)
                if c is None:
                    c = Candidate(vehicle_id=vid)
                    cand[vid] = c
                if source == "collaborative":
                    c.cf_score = score
                elif source == "content":
                    c.content_score = score
                elif source == "vector":
                    c.vector_score = score
                elif source == "popularity":
                    c.popularity = score
                if source not in c.sources:
                    c.sources.append(source)

        if not cand:
            return []

        # Trim to the strongest pool_size by a quick pre-score (sum of signals)
        # before the (more expensive) attribute fetch.
        ordered = sorted(
            cand.values(),
            key=lambda c: c.cf_score + c.content_score + c.vector_score + c.popularity,
            reverse=True,
        )[:pool_size]

        # 2. Batch-fetch attributes.
        self._enrich(ordered, budget)
        return ordered

    def _enrich(self, candidates: list[Candidate], budget: Optional[float]) -> None:
        ids = [c.vehicle_id for c in candidates]
        try:
            rows = self.db.execute(
                text("""
                    SELECT vehicle_id, brand, car_model, price,
                           car_rating, crawled_at
                    FROM gold.vehicles
                    WHERE vehicle_id = ANY(:ids)
                """),
                {"ids": ids},
            ).fetchall()
        except Exception as exc:  # noqa: BLE001
            log.warning("FeatureAssembler enrichment query failed: %s", exc)
            return

        attrs = {r[0]: r for r in rows}
        now = datetime.now(timezone.utc)
        for c in candidates:
            row = attrs.get(c.vehicle_id)
            if row is None:
                continue
            _, brand, car_model, price, car_rating, crawled_at = row
            c.brand = brand
            c.car_model = car_model
            c.price = float(price) if price is not None else None
            # model_rating: cars.com rating is 0..5 -> 0..1
            c.model_rating = (float(car_rating) / 5.0) if car_rating else 0.0
            c.price_fit = self._price_fit(c.price, budget)
            c.recency = self._recency(crawled_at, now)

    @staticmethod
    def _price_fit(price: Optional[float], budget: Optional[float]) -> float:
        """1.0 = right on budget, decaying as the price diverges. Neutral (1.0)
        when no budget is known (guests / no interaction history)."""
        if budget is None or budget <= 0 or price is None:
            return 1.0
        rel = abs(price - budget) / budget
        return max(0.0, 1.0 - min(1.0, rel))

    @staticmethod
    def _recency(crawled_at: Optional[datetime], now: datetime) -> float:
        """Fresher listings score higher. exp decay, ~half-life 30 days."""
        if crawled_at is None:
            return 0.5
        ts = crawled_at if crawled_at.tzinfo else crawled_at.replace(tzinfo=timezone.utc)
        days = max(0.0, (now - ts).total_seconds() / 86400.0)
        return math.exp(-0.023 * days)   # 0.023 ≈ ln(2)/30
