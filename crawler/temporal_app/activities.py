"""Activities — the unit of work Temporal schedules and retries.

Two groups:
  * Crawl   — crawl_links / scrape_details / upload_gcs (SeleniumBase, blocking)
  * Pipeline — load_bronze / dbt_build / refresh_matviews /
               compute_item_similarity / embed_vehicles

All run sync in the worker thread pool — safe for blocking I/O (Selenium,
psycopg2, subprocess). Config comes from env vars (see run_worker.sh).
"""
from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

from temporalio import activity

# crawler.* (seleniumbase/Chrome) is imported lazily inside the crawl activities
# so the Dockerized pipeline worker can import this module without that stack.


@dataclass
class CrawlInput:
    page: int
    crawl_date: str = ""


@dataclass
class CrawlLinksResult:
    page: int
    link_count: int


@dataclass
class ScrapeResult:
    page: int
    done: int
    fail: int
    skip: int


@dataclass
class UploadResult:
    page: int
    json_uploaded: int
    images_uploaded: int


@activity.defn(name="crawl_links")
def crawl_links_activity(inp: CrawlInput) -> CrawlLinksResult:
    """Stage 1: collect listing URLs for the page."""
    from pathlib import Path

    from crawler.config import LINK_FOLDER
    from crawler.link_crawler import crawl_listing_urls

    activity.logger.info("crawl_links page=%s", inp.page)
    crawl_listing_urls(start_page=inp.page, end_page=inp.page)

    page_file = Path(LINK_FOLDER) / f"page_{inp.page}.txt"
    count = (
        len([ln for ln in page_file.read_text().splitlines() if ln.strip()])
        if page_file.exists()
        else 0
    )
    if count == 0:
        raise RuntimeError(f"crawl_links produced 0 URLs for page {inp.page}")
    return CrawlLinksResult(page=inp.page, link_count=count)


@activity.defn(name="scrape_details")
def scrape_details_activity(inp: CrawlInput) -> ScrapeResult:
    """Stage 2: scrape detail JSON for every URL in the page's link file.

    Runs single-worker (MAX_BROWSER_WORKERS=1 set by run_worker.sh) so the
    crawler module's own retry loop handles transient failures inside the
    activity — Temporal retries only kick in for hard exceptions.
    """
    from crawler.detail_scraper import scrape_from_files_parallel

    activity.logger.info("scrape_details page=%s", inp.page)
    result = scrape_from_files_parallel(
        from_page=inp.page, to_page=inp.page, n_workers=1
    )
    if result["done"] == 0 and result["fail"] > 0:
        raise RuntimeError(
            f"scrape_details: all URLs failed for page {inp.page} "
            f"(fail={result['fail']})"
        )
    return ScrapeResult(
        page=inp.page,
        done=result["done"],
        fail=result["fail"],
        skip=result["skip"],
    )


@activity.defn(name="upload_gcs")
def upload_gcs_activity(inp: CrawlInput) -> UploadResult:
    """Stage 3: push JSON + images to gs://incremental_raw/dt=<crawl_date>/."""
    from crawler.gcs_uploader import upload_to_gcs

    activity.logger.info("upload_gcs page=%s dt=%s", inp.page, inp.crawl_date)
    result = upload_to_gcs(
        from_page=inp.page, to_page=inp.page, crawl_date=inp.crawl_date
    )
    return UploadResult(
        page=inp.page,
        json_uploaded=result.get("json_ok", 0),
        images_uploaded=result.get("img_ok", 0),
    )


# ───────────────────────────── Pipeline activities ──────────────────────────
# Transform (Bronze → Postgres → dbt → matviews) and ML (similarity + embeds).
# Config is read from env so the same worker serves every workflow.


def _require_env(name: str) -> str:
    v = os.environ.get(name)
    if not v:
        raise RuntimeError(f"Missing required env var: {name}")
    return v


@dataclass
class LoadBronzeResult:
    scanned: int
    parsed: int
    inserted: int


@dataclass
class SimilarityResult:
    items: int
    pairs: int


@dataclass
class EmbedResult:
    embedded: int
    skipped: bool = False


@activity.defn(name="load_bronze")
def load_bronze_activity(crawl_date: str) -> LoadBronzeResult:
    """GCS dt=<crawl_date> slice → bronze.raw_listings (append-only, idempotent)."""
    from temporal_app.pipeline import BronzeLoaderConfig, load_bronze

    cfg = BronzeLoaderConfig(
        bucket=os.environ.get("GCS_BUCKET", "incremental_raw"),
        crawl_date=crawl_date,
        warehouse_dsn=_require_env("WAREHOUSE_DSN"),
        gcp_project=os.environ.get("GCP_PROJECT_ID"),
    )
    result = load_bronze(cfg, run_id=activity.info().workflow_run_id)
    activity.logger.info("load_bronze(%s): %s", crawl_date, result)
    return LoadBronzeResult(**result)


@activity.defn(name="ensure_partition")
def ensure_partition_activity(crawl_date: str) -> None:
    """Ensure the price-history monthly partition for crawl_date exists."""
    import psycopg2

    dsn = _require_env("WAREHOUSE_DSN")
    conn = psycopg2.connect(dsn)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT gold.ensure_price_history_partition(%s::date)",
                (crawl_date,),
            )
        conn.commit()
    finally:
        conn.close()
    activity.logger.info("ensured price-history partition for %s", crawl_date)


@activity.defn(name="dbt_build")
def dbt_build_activity() -> None:
    """dbt run + test + snapshot. `dbt build` honors the model DAG."""
    dbt_dir = _require_env("DBT_DIR")
    proc = subprocess.run(
        ["dbt", "build", "--profiles-dir", ".", "--project-dir", "."],
        cwd=dbt_dir,
        env={**os.environ},
        capture_output=True,
        text=True,
    )
    activity.logger.info("dbt stdout:\n%s", proc.stdout[-4000:])
    if proc.returncode != 0:
        activity.logger.error("dbt stderr:\n%s", proc.stderr[-4000:])
        raise RuntimeError(f"dbt build failed (exit {proc.returncode})")


@activity.defn(name="refresh_matviews")
def refresh_matviews_activity() -> None:
    """Create (if missing) + REFRESH the popularity / trending matviews."""
    import psycopg2

    dsn = _require_env("WAREHOUSE_DSN")
    sql_path = Path(os.environ.get("MATVIEWS_SQL", ""))
    conn = psycopg2.connect(dsn)
    try:
        with conn.cursor() as cur:
            if sql_path and sql_path.exists():
                cur.execute(sql_path.read_text())
            for mv in ("gold.mv_popular_vehicles", "gold.mv_trending_models"):
                try:
                    cur.execute(f"REFRESH MATERIALIZED VIEW CONCURRENTLY {mv}")
                except Exception as exc:  # first run can't be concurrent
                    activity.logger.warning(
                        "concurrent refresh of %s failed (%s) — plain refresh",
                        mv, exc,
                    )
                    conn.rollback()
                    cur.execute(f"REFRESH MATERIALIZED VIEW {mv}")
        conn.commit()
    finally:
        conn.close()
    activity.logger.info("materialized views refreshed")


@activity.defn(name="compute_item_similarity")
def compute_item_similarity_activity() -> SimilarityResult:
    """gold.user_interactions → gold.item_similarity (item-item CF)."""
    from temporal_app.pipeline import compute_item_similarity

    result = compute_item_similarity(
        warehouse_dsn=_require_env("WAREHOUSE_DSN"),
        top_n=int(os.environ.get("RECO_TOP_N", "50")),
        decay_lambda=float(os.environ.get("RECO_DECAY_LAMBDA", "0.05")),
        lookback_days=int(os.environ.get("RECO_LOOKBACK_DAYS", "180")),
    )
    activity.logger.info("item_similarity: %s", result)
    return SimilarityResult(**result)


@activity.defn(name="embed_vehicles")
def embed_vehicles_activity(crawl_date: str = "") -> EmbedResult:
    """gold.vehicles changed on crawl_date → Qdrant (chatbot + VectorRecaller)."""
    from temporal_app.pipeline import embed_vehicles

    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        activity.logger.warning("OPENAI_API_KEY unset — skipping embedding")
        return EmbedResult(embedded=0, skipped=True)

    result = embed_vehicles(
        warehouse_dsn=_require_env("WAREHOUSE_DSN"),
        qdrant_url=os.environ.get("QDRANT_URL", "http://localhost:6333"),
        openai_api_key=api_key,
        collection=os.environ.get("QDRANT_COLLECTION", "car_chatbot_vectors"),
        embedding_model=os.environ.get(
            "OPENAI_EMBEDDING_MODEL", "text-embedding-3-large"
        ),
        embedding_dim=int(os.environ.get("OPENAI_EMBEDDING_DIM", "3072")),
        since_date=crawl_date or None,
    )
    activity.logger.info("embed_vehicles(since_date=%s): %s", crawl_date, result)
    return EmbedResult(embedded=result.get("embedded", 0))
