"""Stage 1 — candidate generation. Four independent recallers.

Each recaller returns ``{vehicle_id: score}`` with scores normalized to [0, 1]
so the ranker can combine them on a common scale. Recallers fail soft: an
error (e.g. Qdrant down, matview missing) yields ``{}`` rather than raising.
"""

from __future__ import annotations

import logging
import math
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from ..vehicle_vectors import vehicle_point_id
from .config import RecoConfig

log = logging.getLogger(__name__)


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

def time_decay(created_at: Optional[datetime], lam: float) -> float:
    """exp(-lambda * days_since). Recent interactions weigh more."""
    if created_at is None:
        return 1.0
    now = datetime.now(timezone.utc)
    ts = created_at if created_at.tzinfo else created_at.replace(tzinfo=timezone.utc)
    days = max(0.0, (now - ts).total_seconds() / 86400.0)
    return math.exp(-lam * days)


def normalize(scores: dict[str, float]) -> dict[str, float]:
    """Scale scores to [0, 1] by the max. Empty / all-zero -> zeros."""
    if not scores:
        return {}
    hi = max(scores.values())
    if hi <= 0:
        return {k: 0.0 for k in scores}
    return {k: v / hi for k, v in scores.items()}


# --------------------------------------------------------------------------
# recallers
# --------------------------------------------------------------------------

class CollaborativeRecaller:
    """Item-based CF via the precomputed gold.item_similarity table.

    No in-request model fit — the car_recsys_ml DAG precomputes neighbors
    nightly; here we just look them up for the user's interaction seeds.
    """

    name = "collaborative"

    def __init__(self, db: Session, config: RecoConfig):
        self.db = db
        self.cfg = config

    def recall(self, seeds: list[dict[str, Any]]) -> dict[str, float]:
        if not seeds:
            return {}
        cc = self.cfg.candidates
        seed_ids = list({s["vehicle_id"] for s in seeds})
        try:
            rows = self.db.execute(
                text("""
                    SELECT vehicle_id, neighbor_id, score
                    FROM gold.item_similarity
                    WHERE vehicle_id = ANY(:ids) AND rank <= :k
                """),
                {"ids": seed_ids, "k": cc.collaborative_neighbors_per_seed},
            ).fetchall()
        except Exception as exc:  # noqa: BLE001
            log.warning("CollaborativeRecaller query failed: %s", exc)
            return {}

        neighbors: dict[str, list[tuple[str, float]]] = {}
        for vid, nid, score in rows:
            neighbors.setdefault(vid, []).append((nid, float(score)))

        agg: dict[str, float] = {}
        seen = {s["vehicle_id"] for s in seeds}
        for s in seeds:
            w = self.cfg.interaction_weight(s.get("interaction_type", "view"))
            decay = time_decay(s.get("created_at"), self.cfg.time_decay_lambda)
            for nid, sim in neighbors.get(s["vehicle_id"], []):
                if nid in seen:
                    continue
                agg[nid] = agg.get(nid, 0.0) + w * decay * sim
        return normalize(agg)


class ContentRecaller:
    """Spec/feature similarity over gold.vehicles. Cold-start safe — needs no
    interaction data, only a seed vehicle's attributes.
    """

    name = "content"

    def __init__(self, db: Session, config: RecoConfig):
        self.db = db
        self.cfg = config

    def recall(self, seed_ids: list[str]) -> dict[str, float]:
        if not seed_ids:
            return {}
        cc = self.cfg.candidates
        agg: dict[str, float] = {}
        # Use up to 3 strongest seeds to keep the query count bounded.
        for seed in seed_ids[:3]:
            for vid, score in self._similar_to(seed, cc.content_limit,
                                               cc.content_price_band_pct):
                agg[vid] = max(agg.get(vid, 0.0), score)
        return normalize(agg)

    def _similar_to(self, seed: str, limit: int, band: float) -> list[tuple[str, float]]:
        try:
            ref = self.db.execute(
                text("""
                    SELECT brand, car_model, price, fuel_type,
                           transmission, drivetrain
                    FROM gold.vehicles WHERE vehicle_id = :id
                """),
                {"id": seed},
            ).fetchone()
        except Exception as exc:  # noqa: BLE001
            log.warning("ContentRecaller ref lookup failed: %s", exc)
            return []
        if not ref:
            return []
        brand, model, price, fuel, trans, drive = ref
        pmin = float(price) * (1 - band) if price else 0
        pmax = float(price) * (1 + band) if price else 1e12
        try:
            rows = self.db.execute(
                text("""
                    SELECT vehicle_id,
                        (CASE WHEN brand = :brand THEN 2.0 ELSE 0 END)
                      + (CASE WHEN car_model = :model THEN 1.5 ELSE 0 END)
                      + (CASE WHEN fuel_type = :fuel THEN 0.5 ELSE 0 END)
                      + (CASE WHEN transmission = :trans THEN 0.5 ELSE 0 END)
                      + (CASE WHEN drivetrain = :drive THEN 0.3 ELSE 0 END)
                      + (CASE WHEN price BETWEEN :pmin AND :pmax THEN 1.0 ELSE 0 END)
                        AS score
                    FROM gold.vehicles
                    WHERE vehicle_id <> :id AND brand IS NOT NULL
                    ORDER BY score DESC, car_rating DESC NULLS LAST
                    LIMIT :limit
                """),
                {"brand": brand, "model": model, "fuel": fuel, "trans": trans,
                 "drive": drive, "pmin": pmin, "pmax": pmax, "id": seed,
                 "limit": limit},
            ).fetchall()
        except Exception as exc:  # noqa: BLE001
            log.warning("ContentRecaller similarity query failed: %s", exc)
            return []
        return [(r[0], float(r[1])) for r in rows if r[1] and r[1] > 0]


class VectorRecaller:
    """Semantic similarity via Qdrant. Retrieves the seed vehicle's stored
    vector, then searches for nearest neighbors. Fails soft if Qdrant or the
    seed vector is unavailable.
    """

    name = "vector"

    def __init__(self, qdrant_client: Any, collection: str, config: RecoConfig):
        self.client = qdrant_client
        self.collection = collection
        self.cfg = config

    def recall(self, seed_ids: list[str]) -> dict[str, float]:
        if self.client is None or not seed_ids:
            return {}
        cc = self.cfg.candidates
        agg: dict[str, float] = {}
        for seed in seed_ids[:3]:
            for vid, score in self._neighbors(seed, cc.vector_limit):
                agg[vid] = max(agg.get(vid, 0.0), score)
        return normalize(agg)

    def _neighbors(self, seed: str, limit: int) -> list[tuple[str, float]]:
        try:
            point_id = vehicle_point_id(seed)
            stored = self.client.retrieve(
                collection_name=self.collection,
                ids=[point_id],
                with_vectors=True,
            )
            if not stored or stored[0].vector is None:
                return []
            hits = self.client.search(
                collection_name=self.collection,
                query_vector=stored[0].vector,
                limit=limit + 1,            # +1: the seed itself comes back
                with_payload=True,
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("VectorRecaller failed for seed %s: %s", seed, exc)
            return []
        out: list[tuple[str, float]] = []
        for h in hits:
            vid = (h.payload or {}).get("vehicle_id")
            if vid and vid != seed:
                out.append((vid, float(h.score)))
        return out


class PopularityRecaller:
    """Global popularity prior from gold.mv_popular_vehicles. The cold-start
    fallback for guests and brand-new users. Falls back to car_rating if the
    matview does not exist yet.
    """

    name = "popularity"

    def __init__(self, db: Session, config: RecoConfig):
        self.db = db
        self.cfg = config

    def recall(self) -> dict[str, float]:
        limit = self.cfg.candidates.popularity_limit
        try:
            rows = self.db.execute(
                text("""
                    SELECT vehicle_id,
                           COALESCE(pop_score_30d, 0)
                             + COALESCE(car_rating, 0) AS score
                    FROM gold.mv_popular_vehicles
                    ORDER BY score DESC
                    LIMIT :limit
                """),
                {"limit": limit},
            ).fetchall()
        except Exception as exc:  # noqa: BLE001
            log.warning("mv_popular_vehicles unavailable (%s) — car_rating fallback.", exc)
            rows = self.db.execute(
                text("""
                    SELECT vehicle_id, COALESCE(car_rating, 0) AS score
                    FROM gold.vehicles
                    WHERE title IS NOT NULL
                    ORDER BY score DESC NULLS LAST
                    LIMIT :limit
                """),
                {"limit": limit},
            ).fetchall()
        return normalize({r[0]: float(r[1]) for r in rows})
