"""Vehicle embedding pipeline — gold.vehicles → structured document → embedding
→ Qdrant. Incremental (only re-embeds vehicles crawled since the last run).

Shared by the chatbot RAG retriever and the recommender's VectorRecaller (same
Qdrant collection, same point-id convention). Driven either by the
Temporal ML workflow or run standalone.
"""

from __future__ import annotations

import logging
from typing import Any, Iterable, Optional

from sqlalchemy import text
from sqlalchemy.engine import Engine

from ..vehicle_vectors import vehicle_point_id
from .config import CHATBOT_CONFIG

log = logging.getLogger(__name__)


def build_document(vehicle: dict[str, Any], features: list[str]) -> str:
    """Render a vehicle row into the natural-language text that gets embedded.

    Embedding structured prose (not raw columns) makes semantic search match
    the way users actually phrase questions.
    """
    parts = [
        f"{vehicle.get('new_used') or ''} {vehicle.get('title') or ''}".strip(),
        f"Brand: {vehicle.get('brand')}." if vehicle.get("brand") else "",
        f"Model: {vehicle.get('car_name')}." if vehicle.get("car_name") else "",
    ]
    if vehicle.get("price"):
        parts.append(f"Price: ${float(vehicle['price']):,.0f}.")
    if vehicle.get("mileage"):
        parts.append(f"Mileage: {int(vehicle['mileage']):,} miles.")
    for col, label in (
        ("fuel_type", "Fuel"), ("transmission", "Transmission"),
        ("drivetrain", "Drivetrain"), ("exterior_color", "Exterior color"),
        ("engine", "Engine"), ("mpg", "MPG"),
    ):
        if vehicle.get(col):
            parts.append(f"{label}: {vehicle[col]}.")
    if vehicle.get("car_rating"):
        parts.append(f"Owner rating: {vehicle['car_rating']}/5.")
    if features:
        parts.append("Features: " + ", ".join(features[:30]) + ".")
    if vehicle.get("seller_name"):
        parts.append(f"Sold by {vehicle['seller_name']} ({vehicle.get('destination') or ''}).")
    return " ".join(p for p in parts if p)


def _payload(vehicle: dict[str, Any]) -> dict[str, Any]:
    """Qdrant payload — kept small but rich enough to drive filtered search."""
    return {
        "vehicle_id": vehicle["vehicle_id"],
        "brand": vehicle.get("brand"),
        "car_model": vehicle.get("car_model"),
        "car_name": vehicle.get("car_name"),
        "title": vehicle.get("title"),
        "new_used": vehicle.get("new_used"),
        "price": float(vehicle["price"]) if vehicle.get("price") is not None else None,
        "mileage": int(vehicle["mileage"]) if vehicle.get("mileage") is not None else None,
        "fuel_type": vehicle.get("fuel_type"),
        "car_rating": float(vehicle["car_rating"]) if vehicle.get("car_rating") else None,
        "primary_image_url": vehicle.get("primary_image_url"),
    }


class VehicleEmbeddingIngestor:
    def __init__(self, db_engine: Engine, embeddings: Any, qdrant_client: Any):
        self.db = db_engine
        self.embeddings = embeddings
        self.qdrant = qdrant_client
        self.cfg = CHATBOT_CONFIG

    def ensure_collection(self) -> None:
        from qdrant_client.models import Distance, VectorParams
        existing = {c.name for c in self.qdrant.get_collections().collections}
        if self.cfg.qdrant_collection not in existing:
            self.qdrant.create_collection(
                collection_name=self.cfg.qdrant_collection,
                vectors_config=VectorParams(
                    size=self.cfg.embedding_dim, distance=Distance.COSINE),
            )
            log.info("Created Qdrant collection %s", self.cfg.qdrant_collection)

    def _fetch_vehicles(self, since: Optional[str], limit: Optional[int]) -> list[dict]:
        clause = "WHERE crawled_at > :since" if since else ""
        rows = self.db.connect().execute(
            text(f"""
                SELECT vehicle_id, title, new_used, brand, car_name, car_model,
                       price, mileage, fuel_type, transmission, drivetrain,
                       exterior_color, engine, mpg, car_rating,
                       seller_name, destination, primary_image_url
                FROM gold.vehicles
                {clause}
                ORDER BY crawled_at DESC NULLS LAST
                {'LIMIT :limit' if limit else ''}
            """),
            {k: v for k, v in (("since", since), ("limit", limit)) if v is not None},
        ).mappings().all()
        return [dict(r) for r in rows]

    def _features_by_vehicle(self, vehicle_ids: list[str]) -> dict[str, list[str]]:
        if not vehicle_ids:
            return {}
        rows = self.db.connect().execute(
            text("""
                SELECT vehicle_id, feature_name
                FROM gold.vehicle_features
                WHERE vehicle_id = ANY(:ids)
            """),
            {"ids": vehicle_ids},
        ).fetchall()
        out: dict[str, list[str]] = {}
        for vid, fname in rows:
            if fname:
                out.setdefault(vid, []).append(fname)
        return out

    def run(self, since: Optional[str] = None, limit: Optional[int] = None,
            batch_size: int = 100) -> dict[str, int]:
        """Embed + upsert vehicles. `since` = ISO timestamp watermark for the
        incremental run; None = full re-embed."""
        from qdrant_client.models import PointStruct

        self.ensure_collection()
        vehicles = self._fetch_vehicles(since, limit)
        if not vehicles:
            log.info("No vehicles to embed (since=%s).", since)
            return {"embedded": 0}

        feats = self._features_by_vehicle([v["vehicle_id"] for v in vehicles])
        embedded = 0
        for start in range(0, len(vehicles), batch_size):
            batch = vehicles[start:start + batch_size]
            docs = [build_document(v, feats.get(v["vehicle_id"], [])) for v in batch]
            vectors = self.embeddings.embed_documents(docs)
            points = [
                PointStruct(
                    id=vehicle_point_id(v["vehicle_id"]),
                    vector=vec,
                    payload={**_payload(v), "document": doc},
                )
                for v, vec, doc in zip(batch, vectors, docs)
            ]
            self.qdrant.upsert(
                collection_name=self.cfg.qdrant_collection, points=points)
            embedded += len(points)
            log.info("Embedded %d/%d vehicles", embedded, len(vehicles))
        return {"embedded": embedded}
