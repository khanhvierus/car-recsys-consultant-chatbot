"""Shared conventions for vehicle vectors in Qdrant.

Both the recommender (VectorRecaller) and the chatbot (RAG retrieval) use the
SAME Qdrant collection of vehicle embeddings, so the point-id convention must
be defined in exactly one place — here.
"""

from __future__ import annotations

import uuid

# Fixed namespace so vehicle_id -> point_id is deterministic across processes.
_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_DNS, "car-recsys.vehicle-vectors")


def vehicle_point_id(vehicle_id: str) -> str:
    """Deterministic Qdrant point id (UUID string) for a vehicle's VIN.

    Qdrant point ids must be uint64 or UUID; a VIN is neither, so we hash it
    into a stable UUID5. Same VIN -> same point id, every time.
    """
    return str(uuid.uuid5(_NAMESPACE, vehicle_id))
