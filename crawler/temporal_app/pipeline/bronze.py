"""Load raw crawl JSON from GCS into Postgres ``bronze.raw_listings``.

Idempotent: each file is keyed by the sha256 of its bytes, inserted with
``ON CONFLICT (file_hash) DO NOTHING``. Re-running a load — or re-crawling the
same VIN — never duplicates a row. Bronze is append-only; the dbt staging
layer resolves the "current" version per VIN.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Optional

log = logging.getLogger(__name__)

_PAGE_RE = re.compile(r"/(?:dt=\d{4}-\d{2}-\d{2}|raw_data)/(\d+)/")
_DATE_RE = re.compile(r"dt=(\d{4}-\d{2}-\d{2})/")


@dataclass(slots=True)
class BronzeLoaderConfig:
    bucket: str = "incremental_raw"
    crawl_date: str = ""                # "" = scan whole bucket (full backfill)
    warehouse_dsn: str = ""             # postgresql://user:pass@host:5432/db
    source: str = "incremental"
    gcp_project: Optional[str] = None
    download_workers: int = 16
    batch_size: int = 500


def _page_from_path(blob_name: str) -> Optional[int]:
    m = _PAGE_RE.search("/" + blob_name)
    return int(m.group(1)) if m else None


def _date_from_path(blob_name: str) -> Optional[str]:
    m = _DATE_RE.search("/" + blob_name)
    return m.group(1) if m else None


def _prefixes_for(config: BronzeLoaderConfig) -> list[str]:
    """The GCS prefixes to scan. A crawl_date restricts to one day's slice."""
    if config.crawl_date:
        return [f"dt={config.crawl_date}/"]
    return [""]   # whole bucket


def _lift_keys(payload: dict) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """Extract vin / car_model_slug / crawled_at out of the nested payload."""
    vin = None
    post = payload.get("post")
    if isinstance(post, dict):
        basics = post.get("basic_desc")
        if isinstance(basics, dict):
            vin = basics.get("VIN")
    slug = None
    car = payload.get("car")
    if isinstance(car, dict):
        slug = car.get("car_model")
    return vin, slug, payload.get("datetime")


def _process_blob(blob) -> Optional[dict]:
    """Download + parse one GCS blob into an insert-ready row dict."""
    try:
        data = blob.download_as_bytes()
    except Exception as exc:  # noqa: BLE001
        log.warning("download failed for %s: %s", blob.name, exc)
        return None
    file_hash = hashlib.sha256(data).hexdigest()
    try:
        payload = json.loads(data)
    except json.JSONDecodeError as exc:
        log.warning("bad JSON in %s: %s", blob.name, exc)
        return None
    if not isinstance(payload, dict):
        return None
    vin, slug, crawled_at = _lift_keys(payload)
    return {
        "file_hash": file_hash,
        "gcs_path": f"gs://{blob.bucket.name}/{blob.name}",
        "page_number": _page_from_path(blob.name),
        "crawl_date": _date_from_path(blob.name),
        "vin": vin,
        "car_model_slug": slug,
        "payload": json.dumps(payload),
        "crawled_at": crawled_at,
    }


def load_bronze(
    config: BronzeLoaderConfig,
    run_id: str = "",
) -> dict[str, int]:
    """List GCS blobs, download/parse in parallel, bulk-insert into Postgres.

    ``config.crawl_date`` restricts to one day's ``dt=`` prefix; empty string
    scans the whole bucket (full backfill).
    """
    from google.cloud import storage

    client = storage.Client(project=config.gcp_project)
    bucket = client.bucket(config.bucket)

    blobs = []
    for prefix in _prefixes_for(config):
        blobs.extend(
            b for b in client.list_blobs(bucket, prefix=prefix)
            if b.name.endswith(".json")
        )
    log.info("found %d JSON blobs (crawl_date=%s)", len(blobs), config.crawl_date or "ALL")
    if not blobs:
        return {"scanned": 0, "parsed": 0, "inserted": 0}

    rows: list[dict] = []
    with ThreadPoolExecutor(max_workers=config.download_workers) as pool:
        for row in pool.map(_process_blob, blobs):
            if row is not None:
                row["run_id"] = run_id
                row["source"] = config.source
                rows.append(row)
    log.info("parsed %d/%d blobs", len(rows), len(blobs))

    inserted = _insert(config.warehouse_dsn, rows, config.batch_size)
    log.info("inserted %d new bronze rows (%d duplicates skipped)",
             inserted, len(rows) - inserted)
    return {"scanned": len(blobs), "parsed": len(rows), "inserted": inserted}


def _insert(dsn: str, rows: list[dict], batch_size: int) -> int:
    if not rows:
        return 0
    import psycopg2
    from psycopg2.extras import execute_values

    sql = """
        INSERT INTO bronze.raw_listings
            (file_hash, gcs_path, page_number, crawl_date, vin,
             car_model_slug, payload, crawled_at, source, run_id)
        VALUES %s
        ON CONFLICT (file_hash) DO NOTHING
    """
    template = ("(%(file_hash)s, %(gcs_path)s, %(page_number)s, %(crawl_date)s::date, "
                "%(vin)s, %(car_model_slug)s, %(payload)s::jsonb, "
                "%(crawled_at)s::timestamptz, %(source)s, %(run_id)s)")

    inserted = 0
    conn = psycopg2.connect(dsn)
    try:
        with conn.cursor() as cur:
            for i in range(0, len(rows), batch_size):
                batch = rows[i:i + batch_size]
                execute_values(cur, sql, batch, template=template,
                               page_size=batch_size)
                inserted += cur.rowcount
        conn.commit()
    finally:
        conn.close()
    return inserted
