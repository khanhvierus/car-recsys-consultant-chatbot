"""
Listing endpoints - Vehicle details and featured listings
"""
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import List

from app.core.database import get_db
from app.schemas.vehicle import VehicleResponse, VehicleListItem

router = APIRouter()


@router.get("/listing/{vehicle_id}", response_model=VehicleResponse)
async def get_listing(vehicle_id: str, db: Session = Depends(get_db)):
    """Get detailed vehicle listing by vehicle_id (VIN)"""
    
    # Get vehicle details
    vehicle_query = text("""
        SELECT 
            v.vehicle_id,
            v.title,
            v.brand,
            v.car_model,
            v.car_name,
            v.price,
            v.monthly_payment,
            v.mileage,
            v.mileage_str,
            v.exterior_color,
            v.interior_color,
            v.drivetrain,
            v.mpg,
            v.fuel_type,
            v.transmission,
            v.engine,
            v.condition,
            v.accidents_damage,
            v.one_owner,
            v.car_rating,
            v.percentage_recommend,
            v.comfort_rating,
            v.interior_rating,
            v.performance_rating,
            v.value_rating,
            v.exterior_rating,
            v.reliability_rating,
            v.vehicle_url,
            v.total_images
        FROM gold.vehicles v
        WHERE v.vehicle_id = :vehicle_id
    """)
    
    result = db.execute(vehicle_query, {'vehicle_id': vehicle_id}).fetchone()
    
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vehicle not found"
        )
    
    # Get vehicle images
    images_query = text("""
        SELECT image_url 
        FROM gold.vehicle_images 
        WHERE vehicle_id = :vehicle_id 
        ORDER BY id
        LIMIT 20
    """)
    images_result = db.execute(images_query, {'vehicle_id': vehicle_id})
    images = [row[0] for row in images_result if row[0]]
    
    # Get vehicle features
    features_query = text("""
        SELECT feature_name 
        FROM gold.vehicle_features 
        WHERE vehicle_id = :vehicle_id
    """)
    features_result = db.execute(features_query, {'vehicle_id': vehicle_id})
    features = [row[0] for row in features_result if row[0]]
    
    # Build response
    vehicle_data = {
        'vehicle_id': result[0],
        'title': result[1],
        'brand': result[2],
        'car_model': result[3],
        'car_name': result[4],
        'price': float(result[5]) if result[5] else None,
        'monthly_payment': float(result[6]) if result[6] else None,
        'mileage': float(result[7]) if result[7] else None,
        'mileage_str': result[8],
        'exterior_color': result[9],
        'interior_color': result[10],
        'drivetrain': result[11],
        'mpg': result[12],
        'fuel_type': result[13],
        'transmission': result[14],
        'engine': result[15],
        'condition': result[16],
        'accidents_damage': result[17],
        'one_owner': result[18],
        'car_rating': float(result[19]) if result[19] else None,
        'percentage_recommend': float(result[20]) if result[20] else None,
        'comfort_rating': float(result[21]) if result[21] else None,
        'interior_rating': float(result[22]) if result[22] else None,
        'performance_rating': float(result[23]) if result[23] else None,
        'value_rating': float(result[24]) if result[24] else None,
        'exterior_rating': float(result[25]) if result[25] else None,
        'reliability_rating': float(result[26]) if result[26] else None,
        'vehicle_url': result[27],
        'total_images': result[28],
        'image_url': images[0] if images else None,
        'images': images,
        'features': features,
    }
    
    return VehicleResponse(**vehicle_data)


@router.get("/listings", response_model=List[VehicleListItem])
async def get_listings(
    limit: int = Query(10, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db)
):
    """Get featured/latest vehicle listings"""
    
    query = text("""
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
        WHERE v.title IS NOT NULL
        ORDER BY v.car_rating DESC NULLS LAST, v.created_at DESC
        LIMIT :limit OFFSET :offset
    """)
    
    result = db.execute(query, {'limit': limit, 'offset': offset})
    
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
    
    return vehicles


@router.get("/listings/similar/{vehicle_id}", response_model=List[VehicleListItem])
async def get_similar_vehicles_simple(
    vehicle_id: str,
    limit: int = Query(6, ge=1, le=20),
    db: Session = Depends(get_db)
):
    """
    Get similar vehicles based on brand and price range.
    For full recommendation algorithm, use /api/v1/reco/similar/{vehicle_id}
    """
    # Get the reference vehicle
    ref_query = text("""
        SELECT brand, price FROM gold.vehicles WHERE vehicle_id = :id
    """)
    ref_result = db.execute(ref_query, {'id': vehicle_id}).fetchone()
    
    if not ref_result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vehicle not found"
        )
    
    ref_brand, ref_price = ref_result
    price_min = float(ref_price) * 0.7 if ref_price else 0
    price_max = float(ref_price) * 1.3 if ref_price else 999999999
    
    # Find similar vehicles
    query = text("""
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
        WHERE v.vehicle_id != :vehicle_id
          AND v.brand = :brand
          AND v.price BETWEEN :price_min AND :price_max
        ORDER BY v.car_rating DESC NULLS LAST
        LIMIT :limit
    """)
    
    result = db.execute(query, {
        'vehicle_id': vehicle_id,
        'brand': ref_brand,
        'price_min': price_min,
        'price_max': price_max,
        'limit': limit
    })
    
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
    
    return vehicles


@router.get("/filters")
async def get_filters(db: Session = Depends(get_db)):
    """Get available filter options"""
    
    # Get unique brands
    brands_query = text("SELECT DISTINCT brand FROM gold.vehicles WHERE brand IS NOT NULL ORDER BY brand")
    brands = [row[0] for row in db.execute(brands_query)]
    
    # Get unique fuel types
    fuel_query = text("SELECT DISTINCT fuel_type FROM gold.vehicles WHERE fuel_type IS NOT NULL ORDER BY fuel_type")
    fuel_types = [row[0] for row in db.execute(fuel_query)]
    
    # Get unique transmissions
    trans_query = text("SELECT DISTINCT transmission FROM gold.vehicles WHERE transmission IS NOT NULL ORDER BY transmission")
    transmissions = [row[0] for row in db.execute(trans_query)]
    
    # Get unique drivetrains
    drive_query = text("SELECT DISTINCT drivetrain FROM gold.vehicles WHERE drivetrain IS NOT NULL ORDER BY drivetrain")
    drivetrains = [row[0] for row in db.execute(drive_query)]
    
    # Get price range
    price_query = text("SELECT MIN(price), MAX(price) FROM gold.vehicles WHERE price IS NOT NULL")
    price_result = db.execute(price_query).fetchone()
    
    # Get mileage range
    mileage_query = text("SELECT MIN(mileage), MAX(mileage) FROM gold.vehicles WHERE mileage IS NOT NULL")
    mileage_result = db.execute(mileage_query).fetchone()
    
    return {
        "brands": brands,
        "fuel_types": fuel_types,
        "transmissions": transmissions,
        "drivetrains": drivetrains,
        "colors": [],  # Can be populated later
        "conditions": ["Used", "New"],
        "price_range": {
            "min": float(price_result[0]) if price_result[0] else 0,
            "max": float(price_result[1]) if price_result[1] else 0
        },
        "mileage_range": {
            "min": float(mileage_result[0]) if mileage_result[0] else 0,
            "max": float(mileage_result[1]) if mileage_result[1] else 0
        }
    }
