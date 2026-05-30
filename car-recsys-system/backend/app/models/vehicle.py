"""
Vehicle model (read-only from raw data)
Matches database schema in database/init/02-create-schema.sql
"""
from sqlalchemy import Column, String, Integer, Float, DateTime, Text, Boolean, Numeric
from sqlalchemy.orm import relationship
from app.core.database import Base


class Vehicle(Base):
    """Vehicle listing — the dbt-built gold.vehicles mart (one row per VIN)."""
    __tablename__ = "vehicles"
    __table_args__ = {'schema': 'gold'}

    # Primary key
    vehicle_id = Column(String, primary_key=True)
    stock_number = Column(String, nullable=True)
    condition = Column(String, nullable=True)
    
    # Basic info
    title = Column(String, nullable=True)
    brand = Column(String, nullable=True, index=True)
    car_model = Column(String, nullable=True, index=True)
    car_name = Column(String, nullable=True)
    
    # Pricing
    price = Column(Numeric, nullable=True, index=True)
    monthly_payment = Column(Numeric, nullable=True)
    
    # Vehicle specs
    mileage = Column(Numeric, nullable=True)
    mileage_str = Column(String, nullable=True)
    exterior_color = Column(String, nullable=True)
    interior_color = Column(String, nullable=True)
    drivetrain = Column(String, nullable=True)
    mpg = Column(String, nullable=True)
    fuel_type = Column(String, nullable=True)
    transmission = Column(String, nullable=True)
    engine = Column(String, nullable=True)
    vin = Column(String, unique=True, nullable=True)
    
    # History
    accidents_damage = Column(String, nullable=True)
    one_owner = Column(Boolean, nullable=True)
    personal_use_only = Column(Boolean, nullable=True)
    warranty = Column(String, nullable=True)
    
    # Ratings
    car_rating = Column(Numeric, nullable=True)
    percentage_recommend = Column(Numeric, nullable=True)
    comfort_rating = Column(Numeric, nullable=True)
    interior_rating = Column(Numeric, nullable=True)
    performance_rating = Column(Numeric, nullable=True)
    value_rating = Column(Numeric, nullable=True)
    exterior_rating = Column(Numeric, nullable=True)
    reliability_rating = Column(Numeric, nullable=True)
    
    # URLs
    vehicle_url = Column(String, nullable=True)
    car_review_link = Column(String, nullable=True)
    car_link = Column(String, nullable=True)
    
    # Metadata
    source_file = Column(String, nullable=True)
    total_images = Column(Integer, nullable=True)
    has_ratings = Column(Boolean, nullable=True)
    data_complete = Column(Boolean, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, nullable=True)


class VehicleImage(Base):
    """Vehicle images table"""
    __tablename__ = "vehicle_images"
    __table_args__ = {'schema': 'gold'}
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    vehicle_id = Column(String, nullable=False, index=True)
    image_url = Column(String, nullable=True)
    image_order = Column(Integer, nullable=True)
    created_at = Column(DateTime, nullable=True)


class VehicleFeature(Base):
    """Vehicle features table"""
    __tablename__ = "vehicle_features"
    __table_args__ = {'schema': 'gold'}
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    vehicle_id = Column(String, nullable=False, index=True)
    feature_name = Column(String, nullable=True)
    feature_value = Column(String, nullable=True)
