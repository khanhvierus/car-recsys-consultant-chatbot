"""Recommendation endpoints — backed by the multi-stage hybrid engine
(app.services.reco): candidate generation → ranking → MMR re-ranking.

The engine is cheap to construct per request (no in-request model fit — the
collaborative signal comes from the precomputed gold.item_similarity table,
refreshed by the Temporal ML workflow).
"""

from __future__ import annotations

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.security import get_current_user_id_optional
from app.schemas.vehicle import (
    RecommendationItem,
    RecommendationResponse,
    VehicleListItem,
)
from app.services.reco import Recommendation, RecommendationEngine

router = APIRouter()
logger = logging.getLogger(__name__)

# Lazy, process-wide Qdrant client for the engine's VectorRecaller.
_qdrant_client = None
_qdrant_tried = False


def _get_qdrant():
    global _qdrant_client, _qdrant_tried
    if not _qdrant_tried:
        _qdrant_tried = True
        try:
            from qdrant_client import QdrantClient
            _qdrant_client = QdrantClient(url=settings.QDRANT_URL)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Qdrant unavailable for vector recall: %s", exc)
            _qdrant_client = None
    return _qdrant_client


def _engine(db: Session) -> RecommendationEngine:
    return RecommendationEngine(
        db,
        qdrant_client=_get_qdrant(),
        qdrant_collection=settings.QDRANT_COLLECTION,
    )


def _fetch_vehicle_details(db: Session, vehicle_ids: List[str]) -> dict:
    """Load VehicleListItem details for a set of vehicle ids (gold.vehicles)."""
    if not vehicle_ids:
        return {}
    rows = db.execute(
        text("""
            SELECT v.vehicle_id, v.title, v.brand, v.car_model, v.price,
                   v.mileage, v.fuel_type, v.transmission, v.exterior_color,
                   v.car_rating, v.vehicle_url, v.condition,
                   COALESCE(v.primary_image_url, '') AS image_url
            FROM gold.vehicles v
            WHERE v.vehicle_id = ANY(:ids)
        """),
        {"ids": vehicle_ids},
    )
    out: dict = {}
    for r in rows:
        out[r[0]] = VehicleListItem(
            vehicle_id=r[0],
            title=r[1],
            brand=r[2],
            car_model=r[3],
            price=float(r[4]) if r[4] is not None else None,
            mileage_str=f"{int(r[5]):,} mi." if r[5] is not None else None,
            fuel_type=r[6],
            transmission=r[7],
            exterior_color=r[8],
            car_rating=float(r[9]) if r[9] is not None else None,
            vehicle_url=r[10],
            condition=r[11],
            image_url=r[12],
        )
    return out


def _to_response(
    db: Session, recs: List[Recommendation], algorithm: str
) -> RecommendationResponse:
    details = _fetch_vehicle_details(db, [r.vehicle_id for r in recs])
    items = [
        RecommendationItem(vehicle=details[r.vehicle_id], score=r.score, reason=r.reason)
        for r in recs
        if r.vehicle_id in details
    ]
    return RecommendationResponse(
        recommendations=items, total=len(items), algorithm=algorithm)


@router.get("/similar/{vehicle_id}", response_model=RecommendationResponse)
async def get_similar_vehicles(
    vehicle_id: str,
    limit: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db),
):
    """'More like this' — CF neighbors + content + semantic similarity, re-ranked."""
    exists = db.execute(
        text("SELECT 1 FROM gold.vehicles WHERE vehicle_id = :id"),
        {"id": vehicle_id},
    ).fetchone()
    if not exists:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Vehicle {vehicle_id} not found",
        )
    recs = _engine(db).similar_to_vehicle(vehicle_id, top_k=limit)
    return _to_response(db, recs, algorithm="hybrid-similar")


@router.get("/personalized", response_model=RecommendationResponse)
async def get_personalized_recommendations(
    limit: int = Query(20, ge=1, le=100),
    user_id: Optional[str] = Depends(get_current_user_id_optional),
    db: Session = Depends(get_db),
):
    """Personalized multi-stage recommendations. Guests get the popularity fallback."""
    engine = _engine(db)
    if user_id:
        recs = engine.recommend_for_user(user_id, top_k=limit)
        algo = "hybrid-personalized"
    else:
        recs = engine.popular(top_k=limit)
        algo = "popularity"
    return _to_response(db, recs, algorithm=algo)


@router.get("/candidate", response_model=RecommendationResponse)
async def get_candidates(
    limit: int = Query(50, ge=1, le=200),
    brand: Optional[str] = Query(None),
    price_min: Optional[float] = Query(None),
    price_max: Optional[float] = Query(None),
    fuel_type: Optional[str] = Query(None),
    user_id: Optional[str] = Depends(get_current_user_id_optional),
    db: Session = Depends(get_db),
):
    """Filtered recommendations — the hybrid engine with hard filters applied."""
    filters = {
        k: v for k, v in (
            ("brand", brand), ("price_min", price_min),
            ("price_max", price_max), ("fuel_type", fuel_type),
        ) if v is not None
    }
    engine = _engine(db)
    if user_id:
        recs = engine.recommend_for_user(user_id, top_k=limit, filters=filters or None)
    else:
        recs = engine.popular(top_k=limit, filters=filters or None)
    return _to_response(db, recs, algorithm="hybrid-filtered")


@router.get("/popular", response_model=RecommendationResponse)
async def get_popular_vehicles(
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """Popular vehicles — homepage / cold-start fallback (gold.mv_popular_vehicles)."""
    recs = _engine(db).popular(top_k=limit)
    return _to_response(db, recs, algorithm="popularity")


@router.get("/hybrid", response_model=RecommendationResponse)
async def get_hybrid_recommendations(
    limit: int = Query(20, ge=1, le=100),
    user_id: Optional[str] = Depends(get_current_user_id_optional),
    db: Session = Depends(get_db),
):
    """Alias of /personalized — the engine is hybrid by construction."""
    engine = _engine(db)
    if user_id:
        recs = engine.recommend_for_user(user_id, top_k=limit)
        algo = "hybrid"
    else:
        recs = engine.popular(top_k=limit)
        algo = "popularity"
    return _to_response(db, recs, algorithm=algo)


@router.post("/refresh")
async def refresh_recommendation_model():
    """No-op kept for API compatibility.

    The engine no longer fits a model in-process — collaborative similarity is
    precomputed into gold.item_similarity by the Temporal `ML` workflow.
    Trigger that workflow to refresh recommendations.
    """
    return {
        "status": "noop",
        "message": "Collaborative similarity is precomputed by the Temporal "
                   "ML workflow (gold.item_similarity). "
                   "Trigger that workflow to refresh.",
    }
