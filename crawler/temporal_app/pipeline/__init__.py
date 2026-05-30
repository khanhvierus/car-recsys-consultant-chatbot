"""Pure data-pipeline functions, called from Temporal activities.

  bronze.load_bronze              GCS raw JSON → Postgres bronze.raw_listings
  similarity.compute_item_similarity  gold.user_interactions → gold.item_similarity
  embeddings.embed_vehicles       gold.vehicles → Qdrant car-vector collection

No Temporal / Airflow imports here — these are plain functions so they can be
unit-tested and reused. Orchestration (retries, scheduling) lives in the
workflows/activities layer.
"""

from .bronze import BronzeLoaderConfig, load_bronze
from .embeddings import embed_vehicles
from .similarity import compute_item_similarity

__all__ = [
    "BronzeLoaderConfig",
    "load_bronze",
    "compute_item_similarity",
    "embed_vehicles",
]
