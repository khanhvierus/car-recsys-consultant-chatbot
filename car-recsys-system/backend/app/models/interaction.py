"""
User interaction tracking models
"""
from sqlalchemy import Column, String, Integer, DateTime, Numeric, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func
from app.core.database import Base


class UserInteraction(Base):
    __tablename__ = "user_interactions"
    __table_args__ = (
        Index('idx_interactions_user', 'user_id'),
        Index('idx_interactions_vehicle', 'vehicle_id'),
        Index('idx_interactions_type', 'interaction_type'),
        {'schema': 'gold'}
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey('gold.users.id', ondelete='CASCADE'), nullable=False)
    # vehicle_id is a plain VIN string — NO FK. gold.vehicles is rebuilt by dbt
    # (DROP/CREATE), so a cross-schema FK into it would break --full-refresh.
    vehicle_id = Column(String, nullable=False)
    interaction_type = Column(String, nullable=False)  # view, click, compare, save, favorite, contact, inquiry
    session_id = Column(String)
    interaction_score = Column(Numeric, default=1.0)
    extra_data = Column(JSONB)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class UserFavorite(Base):
    __tablename__ = "user_favorites"
    __table_args__ = (
        Index('idx_favorites_user_vehicle', 'user_id', 'vehicle_id', unique=True),
        {'schema': 'gold'}
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey('gold.users.id', ondelete='CASCADE'), nullable=False)
    vehicle_id = Column(String, nullable=False)   # plain VIN — no FK (see UserInteraction)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class UserSearch(Base):
    __tablename__ = "user_searches"
    __table_args__ = (
        Index('idx_searches_user', 'user_id'),
        {'schema': 'gold'}
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey('gold.users.id', ondelete='CASCADE'), nullable=False)
    search_query = Column(String)
    filters = Column(JSONB)
    results_count = Column(Integer)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

