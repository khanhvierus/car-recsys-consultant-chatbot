"""
Read link files and scrape each car detail page in parallel,
saving one JSON per car. Safe to resume — skips already-scraped files.
"""
from __future__ import annotations

import json
import random
import threading
import time
from pathlib import Path

from seleniumbase import SB

from crawler.config import (
    CHROME_BINARY,
    HEADLESS,
    INTER_REQUEST_DELAY,
    LINK_FOLDER,
    MAX_BROWSER_WORKERS,
    RAW_DATA_DIR,
    RETRY_LIMIT,
    USE_XVFB,
)
from crawler.logging_setup import get_logger
from crawler.scraper import scrape_full

log = get_logger(__name__)


def _scrape_worker(
    worker_id: int,
    urls_with_index: list[tuple[int, str]],
    page_dir: Path,
    results: dict,
    lock: threading.Lock,
) -> None:
    done = fail = skip = 0

    # See link_crawler.py for the mode-selection rationale.
    _sb_kwargs = dict(uc=True, locale="en", binary_location=CHROME_BINARY)
    if USE_XVFB:
        _sb_kwargs["xvfb"] = True
    elif HEADLESS:
        _sb_kwargs["headless"] = True
    # else: real GUI
    with SB(**_sb_kwargs) as sb:
        for idx, url in urls_with_index:
            out_file = page_dir / f"{idx}.json"

            if out_file.exists():
                log.info("[W%s] [%s] Skip (already done)", worker_id, idx)
                skip += 1
                continue

            success = False
            for attempt in range(1, RETRY_LIMIT + 1):
                try:
                    log.info("[W%s] [%s/%s] %s", worker_id, idx, attempt, url)
                    data = scrape_full(sb, url)

                    if data:
                        out_file.write_text(
                            json.dumps(data, ensure_ascii=False, indent=2),
                            encoding="utf-8",
                        )
                        log.info("[W%s] [%s] Saved", worker_id, idx)
                        done += 1
                        success = True
                        break
                    else:
                        log.warning(
                            "[W%s] [%s] No data — retry %s/%s",
                            worker_id, idx, attempt, RETRY_LIMIT,
                        )

                except Exception as e:
                    log.warning(
                        "[W%s] [%s] Error (attempt %s): %s",
                        worker_id, idx, attempt, e,
                    )
                    time.sleep(random.uniform(2, 4))

            if not success:
                fail += 1
                log.error(
                    "[W%s] [%s] Failed after %s attempts",
                    worker_id, idx, RETRY_LIMIT,
                )

            time.sleep(INTER_REQUEST_DELAY + random.uniform(0.3, 1.0))

    with lock:
        results[worker_id] = {"done": done, "fail": fail, "skip": skip}
        log.info(
            "[W%s] Finished — done=%s, fail=%s, skip=%s",
            worker_id, done, fail, skip,
        )


def _split_urls(urls_with_index: list, n_workers: int) -> list[list]:
    buckets = [[] for _ in range(n_workers)]
    for i, item in enumerate(urls_with_index):
        buckets[i % n_workers].append(item)
    return buckets


def scrape_from_files_parallel(
    from_page: int,
    to_page: int,
    link_folder: Path = LINK_FOLDER,
    output_root: Path = RAW_DATA_DIR,
    n_workers: int = MAX_BROWSER_WORKERS,
    delay_between_pages: float = 2.0,
) -> dict:
    """
    For each page in [from_page, to_page], read its link file and spawn
    up to n_workers parallel browser sessions to scrape detail pages.

    Returns aggregate counters: {'done': int, 'fail': int, 'skip': int}.
    """
    link_folder = Path(link_folder)
    root = Path(output_root)
    root.mkdir(parents=True, exist_ok=True)
    lock = threading.Lock()

    total_done = total_fail = total_skip = 0

    for page in range(from_page, to_page + 1):
        link_file = link_folder / f"page_{page}.txt"
        if not link_file.exists():
            log.warning("[Skip] %s not found", link_file)
            continue

        urls = [
            u.strip()
            for u in link_file.read_text(encoding="utf-8").splitlines()
            if u.strip()
        ]
        page_dir = root / str(page)
        page_dir.mkdir(exist_ok=True)

        pending = [
            (i, u) for i, u in enumerate(urls, 1)
            if not (page_dir / f"{i}.json").exists()
        ]
        already = len(urls) - len(pending)

        log.info(
            "[Page %s] Total: %s | Pending: %s | Already done: %s",
            page, len(urls), len(pending), already,
        )

        if not pending:
            log.info("All URLs already scraped — skipping page %s", page)
            continue

        actual_workers = min(n_workers, len(pending))
        buckets = _split_urls(pending, actual_workers)
        log.info("[Page %s] Using %s workers", page, actual_workers)
        results: dict = {}

        threads = []
        for wid, bucket in enumerate(buckets):
            t = threading.Thread(
                target=_scrape_worker,
                args=(wid + 1, bucket, page_dir, results, lock),
                daemon=True,
            )
            threads.append(t)
            t.start()
            time.sleep(random.uniform(3, 6))  # stagger worker launches

        for t in threads:
            t.join()

        page_done = sum(r["done"] for r in results.values())
        page_fail = sum(r["fail"] for r in results.values())
        page_skip = sum(r["skip"] for r in results.values())
        total_done += page_done
        total_fail += page_fail
        total_skip += page_skip

        log.info(
            "[Page %s] Done=%s | Failed=%s | Skipped=%s",
            page, page_done, page_fail, page_skip,
        )

        if page < to_page:
            log.info("Waiting %ss before next page...", delay_between_pages)
            time.sleep(delay_between_pages)

    log.info(
        "ALL DONE — Scraped=%s | Failed=%s | Skipped=%s",
        total_done, total_fail, total_skip,
    )
    return {"done": total_done, "fail": total_fail, "skip": total_skip}
