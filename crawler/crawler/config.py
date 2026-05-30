"""
Centralized configuration. All values can be overridden via env vars
(set by run_local.sh / run_worker.sh) — page numbers, paths, GCS bucket, etc.
"""
from __future__ import annotations

import datetime as _dt
import os
from pathlib import Path

# ── Target site ──────────────────────────────────────────────────────────────
SITE_BASE: str = os.getenv("SITE_BASE", "https://www.cars.com")
RESULTS_URL_TMPL: str = os.getenv(
    "RESULTS_URL_TMPL",
    "https://www.cars.com/shopping/results/"
    "?deal_ratings%5B%5D=good&zip=60606"
    "&maximum_distance=9999&sort=best_match_desc&page={page}",
)
USER_AGENT: str = os.getenv(
    "USER_AGENT",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
)

# ── Page range ───────────────────────────────────────────────────────────────
# The weekly Temporal run sets PAGE_NUMBER for a single page; START_PAGE/END_PAGE
# are kept for ad-hoc local back-fill runs.
PAGE_NUMBER: int = int(os.getenv("PAGE_NUMBER", "1"))
START_PAGE: int = int(os.getenv("START_PAGE", str(PAGE_NUMBER)))
END_PAGE: int = int(os.getenv("END_PAGE", str(PAGE_NUMBER)))

# ── Local filesystem layout ──────────────────────────────────────────────────
# In Docker we default everything under /data so it can be mounted as a volume.
DATA_ROOT: Path = Path(os.getenv("DATA_ROOT", "/data"))
LINK_FOLDER: Path = Path(os.getenv("LINK_FOLDER", str(DATA_ROOT / "car_links")))
RAW_DATA_DIR: Path = Path(os.getenv("RAW_DATA_DIR", str(DATA_ROOT / "raw_data")))
IMG_BASE_DIR: Path = Path(os.getenv("IMG_BASE_DIR", str(DATA_ROOT / "downloaded_images")))

# ── Browser ──────────────────────────────────────────────────────────────────
CHROME_BINARY: str = os.getenv("CHROME_BINARY", "/usr/bin/google-chrome")
HEADLESS: bool = os.getenv("HEADLESS", "true").lower() == "true"
USE_XVFB: bool = os.getenv("USE_XVFB", "true").lower() == "true"

# ── Concurrency / rate limiting ──────────────────────────────────────────────
MAX_BROWSER_WORKERS: int = int(os.getenv("MAX_BROWSER_WORKERS", "5"))
RETRY_LIMIT: int = int(os.getenv("RETRY_LIMIT", "3"))
INTER_REQUEST_DELAY: float = float(os.getenv("INTER_REQUEST_DELAY", "1.5"))
LINK_CRAWL_DELAY: float = float(os.getenv("LINK_CRAWL_DELAY", "2.0"))
LINK_CRAWL_MAX_RETRIES: int = int(os.getenv("LINK_CRAWL_MAX_RETRIES", "3"))

# ── GCS ──────────────────────────────────────────────────────────────────────
# Weekly incremental crawls write to a SEPARATE bucket, date-partitioned, so a
# new run never overwrites a prior one and never touches the initial-load bucket.
GCS_BUCKET: str = os.getenv("GCS_BUCKET", "incremental_raw")
GCS_IMAGE_PREFIX: str = os.getenv("GCS_IMAGE_PREFIX", "images")
# Crawl date = the dt= partition. Defaults to today (UTC).
CRAWL_DATE: str = os.getenv("CRAWL_DATE", _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%d"))
# Path to GCP service account JSON (or use ADC).
GOOGLE_APPLICATION_CREDENTIALS: str | None = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")

# ── Misc ─────────────────────────────────────────────────────────────────────
IMAGE_DOWNLOAD_TIMEOUT: int = int(os.getenv("IMAGE_DOWNLOAD_TIMEOUT", "10"))
