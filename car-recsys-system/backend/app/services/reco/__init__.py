"""Multi-stage hybrid recommendation engine.

Public API:
    from app.services.reco import RecommendationEngine, Recommendation

    engine = RecommendationEngine(db, qdrant_client=qc)
    engine.recommend_for_user(user_id)      # personalized
    engine.similar_to_vehicle(vehicle_id)   # "more like this"
    engine.popular()                        # guest / cold-start
"""

from .config import get_reco_config
from .engine import Recommendation, RecommendationEngine
from .features import Candidate

__all__ = ["RecommendationEngine", "Recommendation", "Candidate", "get_reco_config"]
