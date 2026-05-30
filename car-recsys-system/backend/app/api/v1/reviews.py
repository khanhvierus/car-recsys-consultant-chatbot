"""Reviews & seller API endpoints.

Repointed to the gold marts:
  * gold.reviews — keyed by car_model (reviews are per car MODEL on cars.com);
    a vehicle's reviews are found via gold.vehicles.car_model.
  * gold.sellers — joined to a vehicle via gold.vehicles.seller_key.
"""

from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.database import get_db

router = APIRouter()


class ReviewResponse(BaseModel):
    vehicle_id: str
    title: Optional[str] = None
    overall_rating: Optional[float] = None
    review_time: Optional[str] = None
    user_name: Optional[str] = None
    user_location: Optional[str] = None
    review_text: Optional[str] = None
    comfort_rating: Optional[float] = None
    interior_rating: Optional[float] = None
    performance_rating: Optional[float] = None
    value_rating: Optional[float] = None
    exterior_rating: Optional[float] = None
    reliability_rating: Optional[float] = None

    class Config:
        from_attributes = True


class SellerResponse(BaseModel):
    seller_key: str
    seller_name: Optional[str] = None
    seller_address: Optional[str] = None
    seller_city: Optional[str] = None
    seller_state: Optional[str] = None
    seller_zip: Optional[str] = None
    seller_phone: Optional[str] = None
    seller_website: Optional[str] = None
    seller_rating: Optional[float] = None
    seller_rating_count: Optional[int] = None
    description: Optional[str] = None
    hours_monday: Optional[str] = None
    hours_tuesday: Optional[str] = None
    hours_wednesday: Optional[str] = None
    hours_thursday: Optional[str] = None
    hours_friday: Optional[str] = None
    hours_saturday: Optional[str] = None
    hours_sunday: Optional[str] = None

    class Config:
        from_attributes = True


@router.get("/reviews/{vehicle_id}", response_model=List[ReviewResponse])
async def get_vehicle_reviews(
    vehicle_id: str,
    limit: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db),
):
    """Consumer reviews for a vehicle's car model (reviews are model-level)."""
    query = text("""
        SELECT r.overall_rating, r.review_title, r.review_time_raw,
               r.user_name, r.reviewer_from, r.review_text,
               r.rb_comfort, r.rb_interior, r.rb_performance,
               r.rb_value, r.rb_exterior, r.rb_reliability
        FROM gold.vehicles v
        JOIN gold.reviews r ON r.car_model = v.car_model
        WHERE v.vehicle_id = :vehicle_id
        ORDER BY r.review_date DESC NULLS LAST
        LIMIT :limit
    """)
    rows = db.execute(query, {"vehicle_id": vehicle_id, "limit": limit}).fetchall()

    def _f(x):
        return float(x) if x is not None else None

    return [
        ReviewResponse(
            vehicle_id=vehicle_id,
            title=r[1],
            overall_rating=_f(r[0]),
            review_time=r[2],
            user_name=r[3],
            user_location=r[4],
            review_text=r[5],
            comfort_rating=_f(r[6]),
            interior_rating=_f(r[7]),
            performance_rating=_f(r[8]),
            value_rating=_f(r[9]),
            exterior_rating=_f(r[10]),
            reliability_rating=_f(r[11]),
        )
        for r in rows
    ]


@router.get("/seller/{vehicle_id}", response_model=Optional[SellerResponse])
async def get_vehicle_seller(
    vehicle_id: str,
    db: Session = Depends(get_db),
):
    """Seller of a given vehicle (gold.vehicles.seller_key -> gold.sellers)."""
    query = text("""
        SELECT s.seller_key, s.seller_name, s.destination, s.seller_website,
               s.seller_rating, s.seller_rating_count, s.description,
               s.phone_new, s.phone_used, s.hours
        FROM gold.vehicles v
        JOIN gold.sellers s ON s.seller_key = v.seller_key
        WHERE v.vehicle_id = :vehicle_id
        LIMIT 1
    """)
    row = db.execute(query, {"vehicle_id": vehicle_id}).fetchone()
    if not row:
        return None

    hours = row[9] or {}

    def _h(day: str) -> Optional[str]:
        return hours.get(day) if isinstance(hours, dict) else None

    return SellerResponse(
        seller_key=row[0],
        seller_name=row[1],
        seller_address=row[2],          # `destination` is a single address string
        seller_city=None,
        seller_state=None,
        seller_zip=None,
        seller_phone=row[7] or row[8],  # prefer New, fall back to Used
        seller_website=row[3],
        seller_rating=float(row[4]) if row[4] is not None else None,
        seller_rating_count=int(row[5]) if row[5] is not None else None,
        description=row[6],
        hours_monday=_h("Monday"),
        hours_tuesday=_h("Tuesday"),
        hours_wednesday=_h("Wednesday"),
        hours_thursday=_h("Thursday"),
        hours_friday=_h("Friday"),
        hours_saturday=_h("Saturday"),
        hours_sunday=_h("Sunday"),
    )
