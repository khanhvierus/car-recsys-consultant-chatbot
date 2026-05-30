"""Vehicle embeddings → Qdrant, for chatbot RAG retrieval and the recommender's
VectorRecaller (one shared collection).

Self-contained (uses the openai + qdrant-client SDKs directly) so the worker
needs no dependency on the FastAPI backend package. The point-id convention is
duplicated from backend/app/services/vehicle_vectors.py and MUST stay in sync
with it.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Optional

log = logging.getLogger(__name__)

# Must match backend/app/services/vehicle_vectors.py
_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_DNS, "car-recsys.vehicle-vectors")


def _point_id(vehicle_id: str) -> str:
    return str(uuid.uuid5(_NAMESPACE, vehicle_id))


def _build_document(v: dict[str, Any], features: list[str]) -> str:
    parts = [
        f"{v.get('new_used') or ''} {v.get('title') or ''}".strip(),
        f"Brand: {v.get('brand')}." if v.get("brand") else "",
        f"Model: {v.get('car_name')}." if v.get("car_name") else "",
    ]
    if v.get("price"):
        parts.append(f"Price: ${float(v['price']):,.0f}.")
    if v.get("mileage"):
        parts.append(f"Mileage: {int(v['mileage']):,} miles.")
    for col, label in (("fuel_type", "Fuel"), ("transmission", "Transmission"),
                       ("drivetrain", "Drivetrain"), ("engine", "Engine"),
                       ("exterior_color", "Exterior color"), ("mpg", "MPG")):
        if v.get(col):
            parts.append(f"{label}: {v[col]}.")
    if v.get("car_rating"):
        parts.append(f"Owner rating: {v['car_rating']}/5.")
    if features:
        parts.append("Features: " + ", ".join(features[:30]) + ".")
    if v.get("seller_name"):
        parts.append(f"Sold by {v['seller_name']} ({v.get('destination') or ''}).")
    return " ".join(p for p in parts if p)


def _payload(v: dict[str, Any]) -> dict[str, Any]:
    return {
        "vehicle_id": v["vehicle_id"],
        "brand": v.get("brand"),
        "car_model": v.get("car_model"),
        "car_name": v.get("car_name"),
        "title": v.get("title"),
        "new_used": v.get("new_used"),
        "price": float(v["price"]) if v.get("price") is not None else None,
        "mileage": int(v["mileage"]) if v.get("mileage") is not None else None,
        "fuel_type": v.get("fuel_type"),
        "car_rating": float(v["car_rating"]) if v.get("car_rating") else None,
        "primary_image_url": v.get("primary_image_url"),
    }


def embed_vehicles(
    warehouse_dsn: str,
    qdrant_url: str,
    openai_api_key: str,
    collection: str,
    embedding_model: str,
    embedding_dim: int,
    qdrant_api_key: Optional[str] = None,
    since: Optional[str] = None,
    since_date: Optional[str] = None,
    limit: Optional[int] = None,
    batch_size: int = 100,
) -> dict[str, int]:
    """Embed gold.vehicles and upsert into Qdrant.

    ``since_date`` (preferred) filters on ``gold.vehicles.last_updated_date``
    (the incremental watermark added in Task 6) and is used by the ML workflow
    to re-embed only vehicles updated in the current crawl run.

    ``since`` (legacy) filtered on ``crawled_at``; kept for backward
    compatibility but ``since_date`` takes precedence when both are supplied.
    """
    import psycopg2
    import psycopg2.extras
    from openai import OpenAI
    from qdrant_client import QdrantClient
    from qdrant_client.models import Distance, PointStruct, VectorParams

    # Qdrant Cloud requires an api_key; self-hosted local doesn't (pass None).
    qdrant = QdrantClient(url=qdrant_url, api_key=qdrant_api_key or None)
    existing = {c.name for c in qdrant.get_collections().collections}
    if collection not in existing:
        qdrant.create_collection(
            collection_name=collection,
            vectors_config=VectorParams(size=embedding_dim, distance=Distance.COSINE),
        )
        log.info("created Qdrant collection %s", collection)

    conn = psycopg2.connect(warehouse_dsn)
    try:
        params: dict[str, Any] = {"limit": limit}
        if since_date:
            where = "WHERE last_updated_date >= %(since_date)s"
            params["since_date"] = since_date
        elif since:
            where = "WHERE crawled_at > %(since)s"
            params["since"] = since
        else:
            where = ""
        lim = "LIMIT %(limit)s" if limit else ""
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                f"""
                SELECT vehicle_id, title, new_used, brand, car_name, car_model,
                       price, mileage, fuel_type, transmission, drivetrain,
                       exterior_color, engine, mpg, car_rating,
                       seller_name, destination, primary_image_url
                FROM gold.vehicles {where}
                ORDER BY last_updated_date DESC NULLS LAST {lim}
                """,
                params,
            )
            vehicles = [dict(r) for r in cur.fetchall()]

        if not vehicles:
            log.info("no vehicles to embed (since_date=%s since=%s)", since_date, since)
            return {"embedded": 0}

        ids = [v["vehicle_id"] for v in vehicles]
        with conn.cursor() as cur:
            cur.execute(
                "SELECT vehicle_id, feature_name FROM gold.vehicle_features "
                "WHERE vehicle_id = ANY(%s)",
                (ids,),
            )
            feats: dict[str, list[str]] = {}
            for vid, fname in cur.fetchall():
                if fname:
                    feats.setdefault(vid, []).append(fname)
    finally:
        conn.close()

    client = OpenAI(api_key=openai_api_key)
    embedded = 0
    for start in range(0, len(vehicles), batch_size):
        batch = vehicles[start:start + batch_size]
        docs = [_build_document(v, feats.get(v["vehicle_id"], [])) for v in batch]
        resp = client.embeddings.create(model=embedding_model, input=docs)
        vectors = [d.embedding for d in resp.data]
        points = [
            PointStruct(id=_point_id(v["vehicle_id"]), vector=vec,
                        payload={**_payload(v), "document": doc})
            for v, vec, doc in zip(batch, vectors, docs)
        ]
        qdrant.upsert(collection_name=collection, points=points)
        embedded += len(points)
        log.info("embedded %d/%d vehicles", embedded, len(vehicles))
    return {"embedded": embedded}
