"""Hybrid retrieval for the RAG chatbot.

The old retriever was a single Qdrant vector search with an arbitrary 0.3
score cutoff. This replaces it with:

  1. query_parser  — pull hard constraints (budget, brand, condition, fuel,
                     year) out of the user's message via regex/keyword.
  2. vector search — Qdrant, WITH a payload filter built from those
                     constraints, so semantic hits still respect the budget.
  3. SQL search    — a structured gold.vehicles query for the same constraints
                     (catches exact-match listings vector search may rank low).
  4. RRF fusion    — Reciprocal Rank Fusion merges the two ranked lists into
                     one, no magic score threshold needed.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.engine import Engine

from .config import CHATBOT_CONFIG

log = logging.getLogger(__name__)

# --------------------------------------------------------------------------
# query parsing
# --------------------------------------------------------------------------

_NUM_RE = re.compile(r"\$?\s*([\d][\d,]*(?:\.\d+)?)\s*(k|thousand|nghìn|tr|triệu)?", re.I)
_UNDER_RE = re.compile(r"(under|below|less than|up to|max|cheaper than|<|dưới|tối đa|budget)", re.I)
_OVER_RE = re.compile(r"(over|above|more than|at least|min|>|trên|từ)", re.I)
_YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")
_FUEL_MAP = {
    "gasoline": "Gasoline", "gas": "Gasoline", "petrol": "Gasoline",
    "hybrid": "Hybrid", "electric": "Electric", "ev": "Electric",
    "diesel": "Diesel", "plug-in": "Plug-In Hybrid",
}
_CONDITION_MAP = {
    "brand new": "New", "new": "New", "used": "Used",
    "pre-owned": "Used", "second hand": "Used", "certified": "Certified",
}


@dataclass(slots=True)
class QueryConstraints:
    price_min: Optional[float] = None
    price_max: Optional[float] = None
    brand: Optional[str] = None
    new_used: Optional[str] = None
    fuel_type: Optional[str] = None
    year: Optional[int] = None

    def is_empty(self) -> bool:
        return not any((self.price_min, self.price_max, self.brand,
                        self.new_used, self.fuel_type, self.year))


class QueryParser:
    """Deterministic constraint extraction — no extra LLM call, no cost."""

    def __init__(self, known_brands: set[str]):
        # lower-cased brand -> canonical brand
        self._brands = {b.lower(): b for b in known_brands if b}

    def parse(self, message: str) -> QueryConstraints:
        msg = message.lower()
        c = QueryConstraints()

        # price: first number with a money cue
        for m in _NUM_RE.finditer(message):
            raw, unit = m.group(1), (m.group(2) or "").lower()
            try:
                value = float(raw.replace(",", ""))
            except ValueError:
                continue
            if unit in ("k", "thousand", "nghìn"):
                value *= 1_000
            elif unit in ("tr", "triệu"):
                value *= 1_000_000
            if value < 1000:           # ignore stray small numbers (years handled below)
                continue
            window = message[max(0, m.start() - 25):m.start()]
            if _OVER_RE.search(window):
                c.price_min = value
            else:                       # default: a stated number is a budget cap
                c.price_max = value
            break

        # brand
        for low, canon in self._brands.items():
            if re.search(rf"\b{re.escape(low)}\b", msg):
                c.brand = canon
                break

        # condition
        for kw, canon in _CONDITION_MAP.items():
            if kw in msg:
                c.new_used = canon
                break

        # fuel
        for kw, canon in _FUEL_MAP.items():
            if re.search(rf"\b{re.escape(kw)}\b", msg):
                c.fuel_type = canon
                break

        # year
        ym = _YEAR_RE.search(message)
        if ym:
            c.year = int(ym.group(0))
        return c


# --------------------------------------------------------------------------
# hybrid retriever
# --------------------------------------------------------------------------

@dataclass
class RetrievedVehicle:
    vehicle_id: str
    payload: dict[str, Any]
    vector_rank: Optional[int] = None
    sql_rank: Optional[int] = None
    rrf_score: float = 0.0


class HybridRetriever:
    def __init__(self, db_engine: Engine, embeddings: Any, qdrant_client: Any):
        self.db = db_engine
        self.embeddings = embeddings
        self.qdrant = qdrant_client
        self.cfg = CHATBOT_CONFIG
        self._parser: Optional[QueryParser] = None

    # ---- public -----------------------------------------------------------

    def retrieve(self, query: str) -> tuple[list[RetrievedVehicle], QueryConstraints]:
        constraints = self._get_parser().parse(query)
        vector_hits = self._vector_search(query, constraints)
        sql_hits = self._sql_search(constraints)
        fused = self._rrf_fuse(vector_hits, sql_hits)
        return fused[: self.cfg.final_top_k], constraints

    # ---- parser (lazy: needs the brand vocab from the DB) -----------------

    def _get_parser(self) -> QueryParser:
        if self._parser is None:
            try:
                with self.db.connect() as con:
                    brands = {
                        r[0] for r in con.execute(
                            text("SELECT DISTINCT brand FROM gold.vehicles "
                                 "WHERE brand IS NOT NULL"))
                    }
            except Exception as exc:  # noqa: BLE001
                log.warning("brand vocab load failed: %s", exc)
                brands = set()
            self._parser = QueryParser(brands)
        return self._parser

    # ---- vector leg -------------------------------------------------------

    def _vector_search(
        self, query: str, c: QueryConstraints
    ) -> list[RetrievedVehicle]:
        try:
            from qdrant_client.models import (
                FieldCondition, Filter, MatchValue, Range)
        except Exception:  # noqa: BLE001
            return []
        try:
            vector = self.embeddings.embed_query(query)
        except Exception as exc:  # noqa: BLE001
            log.error("embed_query failed: %s", exc)
            return []

        must: list[Any] = []
        if c.brand:
            must.append(FieldCondition(key="brand", match=MatchValue(value=c.brand)))
        if c.new_used:
            must.append(FieldCondition(key="new_used", match=MatchValue(value=c.new_used)))
        if c.fuel_type:
            must.append(FieldCondition(key="fuel_type", match=MatchValue(value=c.fuel_type)))
        if c.price_min is not None or c.price_max is not None:
            must.append(FieldCondition(
                key="price", range=Range(gte=c.price_min, lte=c.price_max)))
        qfilter = Filter(must=must) if must else None

        try:
            hits = self.qdrant.search(
                collection_name=self.cfg.qdrant_collection,
                query_vector=vector,
                query_filter=qfilter,
                limit=self.cfg.vector_top_k,
                with_payload=True,
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("Qdrant search failed: %s", exc)
            return []
        out: list[RetrievedVehicle] = []
        for rank, h in enumerate(hits):
            payload = h.payload or {}
            vid = payload.get("vehicle_id")
            if vid:
                out.append(RetrievedVehicle(vid, payload, vector_rank=rank))
        return out

    # ---- SQL leg ----------------------------------------------------------

    def _sql_search(self, c: QueryConstraints) -> list[RetrievedVehicle]:
        conditions: list[str] = ["title IS NOT NULL"]
        params: dict[str, Any] = {"limit": self.cfg.sql_top_k}
        if c.brand:
            conditions.append("brand = :brand")
            params["brand"] = c.brand
        if c.new_used:
            conditions.append("new_used = :new_used")
            params["new_used"] = c.new_used
        if c.fuel_type:
            conditions.append("fuel_type = :fuel_type")
            params["fuel_type"] = c.fuel_type
        if c.price_min is not None:
            conditions.append("price >= :price_min")
            params["price_min"] = c.price_min
        if c.price_max is not None:
            conditions.append("price <= :price_max")
            params["price_max"] = c.price_max
        if c.year:
            conditions.append("car_name ILIKE :year")
            params["year"] = f"%{c.year}%"

        try:
            with self.db.connect() as con:
                rows = con.execute(
                    text(f"""
                        SELECT vehicle_id, brand, car_name, title, new_used,
                               price, mileage, fuel_type, car_rating,
                               primary_image_url
                        FROM gold.vehicles
                        WHERE {' AND '.join(conditions)}
                        ORDER BY car_rating DESC NULLS LAST, price ASC NULLS LAST
                        LIMIT :limit
                    """),
                    params,
                ).mappings().all()
        except Exception as exc:  # noqa: BLE001
            log.warning("SQL retrieval failed: %s", exc)
            return []
        return [
            RetrievedVehicle(r["vehicle_id"], dict(r), sql_rank=rank)
            for rank, r in enumerate(rows)
        ]

    # ---- RRF fusion -------------------------------------------------------

    def _rrf_fuse(
        self,
        vector_hits: list[RetrievedVehicle],
        sql_hits: list[RetrievedVehicle],
    ) -> list[RetrievedVehicle]:
        k = self.cfg.rrf_k
        merged: dict[str, RetrievedVehicle] = {}

        for h in vector_hits:
            merged[h.vehicle_id] = h
        for h in sql_hits:
            if h.vehicle_id in merged:
                merged[h.vehicle_id].sql_rank = h.sql_rank
                # keep the richer payload (SQL row has clean columns)
                merged[h.vehicle_id].payload = {**h.payload, **merged[h.vehicle_id].payload}
            else:
                merged[h.vehicle_id] = h

        for h in merged.values():
            score = 0.0
            if h.vector_rank is not None:
                score += 1.0 / (k + h.vector_rank)
            if h.sql_rank is not None:
                score += 1.0 / (k + h.sql_rank)
            h.rrf_score = score

        return sorted(merged.values(), key=lambda h: h.rrf_score, reverse=True)
