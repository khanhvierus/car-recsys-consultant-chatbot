"""Upload scraped JSON and downloaded images to GCS, date-partitioned.

Object layout (incremental):
    dt=<crawl_date>/<page>/<file>.json
    dt=<crawl_date>/images/<relative-path>
Each weekly run uses a fresh dt= prefix, so nothing is ever overwritten.
"""
from __future__ import annotations

from pathlib import Path

from crawler.config import (
    CRAWL_DATE,
    GCS_BUCKET,
    GCS_IMAGE_PREFIX,
    IMG_BASE_DIR,
    RAW_DATA_DIR,
)
from crawler.logging_setup import get_logger

log = get_logger(__name__)


def _json_blob_name(crawl_date: str, page: int, filename: str) -> str:
    return f"dt={crawl_date}/{page}/{filename}"


def _image_blob_name(crawl_date: str, relative: str) -> str:
    return f"dt={crawl_date}/{GCS_IMAGE_PREFIX}/{relative}"


def upload_to_gcs(
    from_page: int,
    to_page: int,
    crawl_date: str = CRAWL_DATE,
    raw_data_dir: Path = RAW_DATA_DIR,
    img_base_dir: Path = IMG_BASE_DIR,
    bucket_name: str = GCS_BUCKET,
) -> dict:
    """Upload JSON + images for [from_page, to_page] under dt=<crawl_date>/.

    Returns counts: {'json_ok','json_fail','img_ok','img_fail'}.
    """
    from google.cloud import storage  # type: ignore

    raw_data_dir = Path(raw_data_dir)
    img_base_dir = Path(img_base_dir)
    client = storage.Client()
    bucket = client.bucket(bucket_name)

    json_ok = json_fail = 0
    for page in range(from_page, to_page + 1):
        page_dir = raw_data_dir / str(page)
        if not page_dir.is_dir():
            log.info("[Skip] %s not found", page_dir)
            continue
        for f in sorted(page_dir.glob("*.json")):
            blob_name = _json_blob_name(crawl_date, page, f.name)
            try:
                bucket.blob(blob_name).upload_from_filename(
                    str(f), content_type="application/json"
                )
                json_ok += 1
            except Exception as e:
                log.warning("[!] %s: %s", blob_name, e)
                json_fail += 1
    log.info("JSON: %s uploaded, %s failed (dt=%s)", json_ok, json_fail, crawl_date)

    img_ok = img_fail = 0
    if not img_base_dir.exists():
        log.info("[Skip] No %s folder found", img_base_dir)
    else:
        for img_file in img_base_dir.rglob("*.jpg"):
            relative = img_file.relative_to(img_base_dir).as_posix()
            blob_name = _image_blob_name(crawl_date, relative)
            try:
                bucket.blob(blob_name).upload_from_filename(
                    str(img_file), content_type="image/jpeg"
                )
                img_ok += 1
            except Exception as e:
                log.warning("[!] %s: %s", blob_name, e)
                img_fail += 1
        log.info("Images: %s uploaded, %s failed", img_ok, img_fail)

    log.info("GCS upload complete")
    return {"json_ok": json_ok, "json_fail": json_fail,
            "img_ok": img_ok, "img_fail": img_fail}
