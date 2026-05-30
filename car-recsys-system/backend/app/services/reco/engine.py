"""Multi-stage hybrid recommendation engine — the orchestrator.

    stage 1  candidate generation   4 recallers (candidates.py)
    stage 2  ranking                weighted-linear scorer (ranker.py)
    stage 3  re-ranking             MMR diversity + caps (reranker.py)

No in-request model fit: collaborative signal comes from the precomputed
gold.item_similarity table (refreshed by the car_recsys_ml DAG). An engine
instance is cheap — construct one per request.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from .candidates import (
    CollaborativeRecaller,
    ContentRecaller,
    PopularityRecaller,
    VectorRecaller,
)
from .config import get_reco_config
from .features import Candidate, FeatureAssembler
from .ranker import WeightedLinearRanker
from .reranker import MMRReranker

log = logging.getLogger(__name__)

_REASONS = {
    "collaborative": "Similar to cars you engaged with",
    "vector": "Semantically similar to your interests",
    "content": "Same segment / specs as your picks",
    "popularity": "Popular with other shoppers",
}


@dataclass(slots=True)
class Recommendation:
    vehicle_id: str
    score: float
    reason: str
    sources: list[str]


class RecommendationEngine:
    def __init__(
        self,
        db: Session,
        qdrant_client: Any = None,
        qdrant_collection: str = "car_chatbot_vectors",
    ):
        self.db = db
        self.cfg = get_reco_config()
        self._collaborative = CollaborativeRecaller(db, self.cfg)
        self._content = ContentRecaller(db, self.cfg)
        self._vector = VectorRecaller(qdrant_client, qdrant_collection, self.cfg)
        self._popularity = PopularityRecaller(db, self.cfg)
        self._assembler = FeatureAssembler(db)
        self._ranker = WeightedLinearRanker(self.cfg)
        self._reranker = MMRReranker(self.cfg)

    # ---- public API -------------------------------------------------------

    def recommend_for_user(
        self,
        user_id: str,
        top_k: Optional[int] = None,
        filters: Optional[dict[str, Any]] = None,
    ) -> list[Recommendation]:
        """Personalized recommendations. Falls back to popular for cold users."""
        top_k = top_k or self.cfg.top_k
        seeds = self._user_seeds(user_id)
        if not seeds:
            return self.popular(top_k, filters)

        seed_ids = [s["vehicle_id"] for s in seeds]
        budget = self._user_budget(seed_ids)
        cc = self.cfg.candidates
        outputs: dict[str, dict[str, float]] = {}
        if cc.collaborative_enabled:
            outputs["collaborative"] = self._collaborative.recall(seeds)
        if cc.content_enabled:
            outputs["content"] = self._content.recall(seed_ids)
        if cc.vector_enabled:
            outputs["vector"] = self._vector.recall(seed_ids)
        if cc.popularity_enabled:
            outputs["popularity"] = self._popularity.recall()
        return self._pipeline(outputs, budget, top_k, filters, exclude=set(seed_ids))

    def similar_to_vehicle(
        self,
        vehicle_id: str,
        top_k: Optional[int] = None,
        filters: Optional[dict[str, Any]] = None,
    ) -> list[Recommendation]:
        """'More like this' for a single vehicle (item page)."""
        top_k = top_k or self.cfg.top_k
        seeds = [{"vehicle_id": vehicle_id,
                  "interaction_type": "view", "created_at": None}]
        cc = self.cfg.candidates
        outputs: dict[str, dict[str, float]] = {}
        if cc.collaborative_enabled:
            outputs["collaborative"] = self._collaborative.recall(seeds)
        if cc.content_enabled:
            outputs["content"] = self._content.recall([vehicle_id])
        if cc.vector_enabled:
            outputs["vector"] = self._vector.recall([vehicle_id])
        budget = self._vehicle_price(vehicle_id)
        return self._pipeline(outputs, budget, top_k, filters, exclude={vehicle_id})

    def popular(
        self,
        top_k: Optional[int] = None,
        filters: Optional[dict[str, Any]] = None,
    ) -> list[Recommendation]:
        """Guest / cold-start fallback — popularity only."""
        top_k = top_k or self.cfg.top_k
        outputs = {"popularity": self._popularity.recall()}
        return self._pipeline(outputs, None, top_k, filters, exclude=set())

    # ---- pipeline ---------------------------------------------------------

    def _pipeline(
        self,
        outputs: dict[str, dict[str, float]],
        budget: Optional[float],
        top_k: int,
        filters: Optional[dict[str, Any]],
        exclude: set[str],
    ) -> list[Recommendation]:
        candidates = self._assembler.assemble(
            outputs, budget, self.cfg.candidate_pool_size)
        candidates = [c for c in candidates if c.vehicle_id not in exclude]
        if filters:
            candidates = self._apply_filters(candidates, filters)
        ranked = self._ranker.score(candidates)
        final = self._reranker.rerank(ranked, top_k)
        return [self._to_reco(c) for c in final]

    @staticmethod
    def _to_reco(c: Candidate) -> Recommendation:
        signals = {
            "collaborative": c.cf_score,
            "vector": c.vector_score,
            "content": c.content_score,
            "popularity": c.popularity,
        }
        dominant = max(signals, key=signals.get) if any(signals.values()) else "popularity"
        return Recommendation(
            vehicle_id=c.vehicle_id,
            score=round(c.rank_score, 4),
            reason=_REASONS.get(dominant, "Recommended for you"),
            sources=c.sources,
        )

    # ---- DB helpers -------------------------------------------------------

    def _user_seeds(self, user_id: str) -> list[dict[str, Any]]:
        limit = self.cfg.candidates.collaborative_user_history_limit
        try:
            rows = self.db.execute(
                text("""
                    SELECT vehicle_id, interaction_type, created_at
                    FROM gold.user_interactions
                    WHERE user_id = :uid::uuid
                    ORDER BY created_at DESC
                    LIMIT :limit
                """),
                {"uid": user_id, "limit": limit},
            ).fetchall()
        except Exception as exc:  # noqa: BLE001
            log.warning("user_seeds query failed for %s: %s", user_id, exc)
            return []
        return [
            {"vehicle_id": r[0], "interaction_type": r[1], "created_at": r[2]}
            for r in rows
        ]

    def _user_budget(self, seed_ids: list[str]) -> Optional[float]:
        """Budget proxy = average price of the user's interacted vehicles."""
        if not seed_ids:
            return None
        try:
            row = self.db.execute(
                text("""
                    SELECT AVG(price) FROM gold.vehicles
                    WHERE vehicle_id = ANY(:ids) AND price IS NOT NULL
                """),
                {"ids": seed_ids},
            ).fetchone()
        except Exception:  # noqa: BLE001
            return None
        return float(row[0]) if row and row[0] is not None else None

    def _vehicle_price(self, vehicle_id: str) -> Optional[float]:
        try:
            row = self.db.execute(
                text("SELECT price FROM gold.vehicles WHERE vehicle_id = :id"),
                {"id": vehicle_id},
            ).fetchone()
        except Exception:  # noqa: BLE001
            return None
        return float(row[0]) if row and row[0] is not None else None

    def _apply_filters(
        self, candidates: list[Candidate], filters: dict[str, Any]
    ) -> list[Candidate]:
        ids = [c.vehicle_id for c in candidates]
        if not ids:
            return []
        conditions = ["vehicle_id = ANY(:ids)"]
        params: dict[str, Any] = {"ids": ids}
        if filters.get("brand"):
            conditions.append("brand = :brand")
            params["brand"] = filters["brand"]
        if filters.get("price_min") is not None:
            conditions.append("price >= :price_min")
            params["price_min"] = filters["price_min"]
        if filters.get("price_max") is not None:
            conditions.append("price <= :price_max")
            params["price_max"] = filters["price_max"]
        if filters.get("fuel_type"):
            conditions.append("fuel_type = :fuel_type")
            params["fuel_type"] = filters["fuel_type"]
        if filters.get("new_used"):
            conditions.append("new_used = :new_used")
            params["new_used"] = filters["new_used"]
        try:
            valid = {
                r[0] for r in self.db.execute(
                    text(f"SELECT vehicle_id FROM gold.vehicles "
                         f"WHERE {' AND '.join(conditions)}"),
                    params,
                )
            }
        except Exception as exc:  # noqa: BLE001
            log.warning("filter query failed: %s", exc)
            return candidates
        return [c for c in candidates if c.vehicle_id in valid]
