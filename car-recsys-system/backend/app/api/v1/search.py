"""
Search endpoints - Vehicle search with filters
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import Optional
import math

from app.core.database import get_db
from app.schemas.vehicle import VehicleListItem, VehicleSearchResponse

router = APIRouter()


@router.get("/search", response_model=VehicleSearchResponse)
async def search_vehicles(
    query: Optional[str] = Query(None, description="Search query for title, brand, model"),
    condition: Optional[str] = Query(None, description="Vehicle condition: used or new"),
    brand: Optional[str] = Query(None),
    model: Optional[str] = Query(None),
    year_min: Optional[int] = Query(None),
    year_max: Optional[int] = Query(None),
    price_min: Optional[float] = Query(None),
    price_max: Optional[float] = Query(None),
    mileage_max: Optional[float] = Query(None),
    fuel_type: Optional[str] = Query(None),
    transmission: Optional[str] = Query(None),
    drivetrain: Optional[str] = Query(None),
    exterior_color: Optional[str] = Query(None),
    min_rating: Optional[float] = Query(None),
    sort_by: str = Query("created_at", description="Sort field: price, mileage, car_rating, created_at"),
    sort_order: str = Query("desc", description="Sort order: asc, desc"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """
    Search vehicles with filters
    """
    # Build WHERE conditions
    conditions = ["title IS NOT NULL"]
    params = {}
    
    if query:
        conditions.append("(title ILIKE :query OR brand ILIKE :query OR car_model ILIKE :query)")
        params['query'] = f"%{query}%"
    
    if brand:
        conditions.append("brand ILIKE :brand")
        params['brand'] = f"%{brand}%"
    
    if model:
        conditions.append("car_model ILIKE :model")
        params['model'] = f"%{model}%"
    
    if condition:
        conditions.append("condition ILIKE :condition")
        params['condition'] = f"%{condition}%"
    
    if price_min:
        conditions.append("price >= :price_min")
        params['price_min'] = price_min
    
    if price_max:
        conditions.append("price <= :price_max")
        params['price_max'] = price_max
    
    if mileage_max:
        conditions.append("mileage <= :mileage_max")
        params['mileage_max'] = mileage_max
    
    if fuel_type:
        conditions.append("fuel_type ILIKE :fuel_type")
        params['fuel_type'] = f"%{fuel_type}%"
    
    if transmission:
        conditions.append("transmission ILIKE :transmission")
        params['transmission'] = f"%{transmission}%"
    
    if drivetrain:
        conditions.append("drivetrain ILIKE :drivetrain")
        params['drivetrain'] = f"%{drivetrain}%"
    
    if exterior_color:
        conditions.append("exterior_color ILIKE :exterior_color")
        params['exterior_color'] = f"%{exterior_color}%"
    
    if min_rating:
        conditions.append("car_rating >= :min_rating")
        params['min_rating'] = min_rating
    
    where_clause = " AND ".join(conditions)
    
    # Get total count
    count_sql = f"SELECT COUNT(*) FROM gold.vehicles WHERE {where_clause}"
    total = db.execute(text(count_sql), params).scalar()
    
    # Build ORDER BY
    sort_column_map = {
        'price': 'price',
        'mileage': 'mileage',
        'car_rating': 'car_rating',
        'created_at': 'created_at',
        'rating': 'car_rating',
    }
    sort_column = sort_column_map.get(sort_by, 'created_at')
    order = 'ASC' if sort_order.lower() == 'asc' else 'DESC'
    
    # Get paginated results
    offset = (page - 1) * page_size
    params['limit'] = page_size
    params['offset'] = offset
    
    query_sql = f"""
        SELECT 
            v.vehicle_id,
            v.title,
            v.brand,
            v.car_model,
            v.price,
            v.mileage_str,
            v.fuel_type,
            v.transmission,
            v.exterior_color,
            v.car_rating,
            v.vehicle_url,
            v.condition,
            COALESCE(
                (SELECT image_url FROM gold.vehicle_images vi 
                 WHERE vi.vehicle_id = v.vehicle_id 
                 ORDER BY vi.id LIMIT 1),
                ''
            ) as image_url
        FROM gold.vehicles v
        WHERE {where_clause}
        ORDER BY {sort_column} {order} NULLS LAST
        LIMIT :limit OFFSET :offset
    """
    
    result = db.execute(text(query_sql), params)
    vehicles = []
    
    for row in result:
        vehicles.append(VehicleListItem(
            vehicle_id=row[0],
            title=row[1],
            brand=row[2],
            car_model=row[3],
            price=float(row[4]) if row[4] else None,
            mileage_str=row[5],
            fuel_type=row[6],
            transmission=row[7],
            exterior_color=row[8],
            car_rating=float(row[9]) if row[9] else None,
            vehicle_url=row[10],
            condition=row[11],
            image_url=row[12]
        ))
    
    total_pages = math.ceil(total / page_size) if total > 0 else 0
    
    return VehicleSearchResponse(
        results=vehicles,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages
    )
