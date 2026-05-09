"""End-to-end orchestration: discover URLs → fetch HTML → parse → save JSON.

Two entry points:

* ``discover_listing_urls`` — paginates through Cars.com search results and
  saves one ``page_<n>.txt`` per page (Selenium-only, scroll required).

* ``scrape_listings`` — reads those ``page_<n>.txt`` files, fetches detail /
  seller / review HTML concurrently (httpx, Selenium fallback), parses them,
  and writes one JSON per car. Resumable.
"""

from __future__ import annotations

import json
import logging
import random
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .driver import DriverPool, scroll_to_bottom, wait_for_listings
from .fetcher import HtmlFetcher
from .parsers import (
    classify,
    extract_listing_links,
    parse_listing,
    parse_reviews,
    parse_seller,
)
from .settings import RESULTS_URL_TMPL, CrawlerSettings

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Discovery — search results pagination
# ---------------------------------------------------------------------------

def discover_listing_urls(settings: CrawlerSettings) -> dict[int, list[str]]:
    """Crawl search-result pages [start_page, end_page] and write one .txt per page.

    Returns {page_number: [urls]} for in-process inspection.
    """
    settings.link_dir.mkdir(parents=True, exist_ok=True)

    results: dict[int, list[str]] = {}
    with DriverPool(settings, size=1) as pool:
        with pool.borrow() as driver:
            for page in range(settings.start_page, settings.end_page + 1):
                out_file = settings.link_dir / f"page_{page}.txt"
                if settings.resume and out_file.exists() and out_file.stat().st_size > 0:
                    log.info("Page %d already discovered — skipping", page)
                    results[page] = out_file.read_text("utf-8").splitlines()
                    continue

                url = RESULTS_URL_TMPL.format(page=page)
                log.info("Discovering page %d", page)
                try:
                    driver.get(url)
                    wait_for_listings(driver, timeout=settings.wait_timeout)
                except Exception as exc:  # noqa: BLE001
                    log.warning("Page %d navigation failed: %s", page, exc)
                    continue

                scroll_to_bottom(
                    driver,
                    pause=settings.scroll_pause,
                    max_rounds=settings.scroll_max_rounds,
                )

                links = list(dict.fromkeys(extract_listing_links(driver.page_source)))
                if not links:
                    log.warning("No vehicle links on page %d", page)
                    continue

                out_file.write_text("\n".join(links), encoding="utf-8")
                results[page] = links
                log.info("Page %d → %d links saved", page, len(links))

                lo, hi = settings.page_delay
                time.sleep(random.uniform(lo, hi))

    return results


# ---------------------------------------------------------------------------
# Scraping
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class _PageContext:
    page: int
    page_dir: Path
    listings_dir: Path
    sellers_dir: Path
    reviews_dir: Path


def scrape_listings(settings: CrawlerSettings) -> None:
    """Main batch scraper. Iterates pages, fetches concurrently, writes JSON."""
    settings.output_dir.mkdir(parents=True, exist_ok=True)

    with DriverPool(settings, size=settings.selenium_workers) as pool, HtmlFetcher(
        settings, driver_pool=pool
    ) as fetcher:
        for page in range(settings.start_page, settings.end_page + 1):
            link_file = settings.link_dir / f"page_{page}.txt"
            if not link_file.exists():
                log.warning("Missing %s — skipping", link_file)
                continue

            urls = [u for u in link_file.read_text("utf-8").splitlines() if u.strip()]
            urls = list(dict.fromkeys(urls))  # in-page dedup
            if not urls:
                log.warning("Page %d has no URLs", page)
                continue

            ctx = _build_page_context(settings, page)
            _process_page(settings, fetcher, ctx, urls)


def _build_page_context(settings: CrawlerSettings, page: int) -> _PageContext:
    page_dir = settings.output_dir / str(page)
    page_dir.mkdir(parents=True, exist_ok=True)
    cache = settings.html_cache_dir / f"page_{page}"
    return _PageContext(
        page=page,
        page_dir=page_dir,
        listings_dir=cache / "listings",
        sellers_dir=cache / "sellers",
        reviews_dir=cache / "reviews",
    )


def _process_page(
    settings: CrawlerSettings,
    fetcher: HtmlFetcher,
    ctx: _PageContext,
    urls: list[str],
) -> None:
    log.info("=== page %d: %d URLs ===", ctx.page, len(urls))

    # 1. Identify which cars still need work; honor resume mode.
    pending = [(idx, url) for idx, url in enumerate(urls, start=1)
               if not (settings.resume and (ctx.page_dir / f"{idx}.json").exists())]
    if not pending:
        log.info("Page %d: all %d cars already scraped — skipping", ctx.page, len(urls))
        return

    # 2. Fetch listing HTML concurrently.
    listing_paths = _parallel_fetch(fetcher, pending, ctx.listings_dir, settings.http_workers)

    # 3. Parse listings → collect secondary URLs.
    listing_data: dict[int, dict] = {}
    secondary: list[tuple[int, Optional[str], Optional[str]]] = []
    for idx, url in pending:
        path = listing_paths.get((idx, url))
        if not path:
            continue
        data = parse_listing(path.read_text("utf-8"), url=url)
        if not data:
            continue
        listing_data[idx] = data
        secondary.append(
            (idx, data["seller"].get("seller_link"), data["car"].get("review_link"))
        )

    # 4. Fetch seller + review HTML concurrently (deduped by URL).
    seller_jobs = list({s for _, s, _ in secondary if s})
    review_jobs = list({r for _, _, r in secondary if r})
    seller_paths = _parallel_fetch_unique(fetcher, seller_jobs, ctx.sellers_dir, settings.http_workers)
    review_paths = _parallel_fetch_unique(fetcher, review_jobs, ctx.reviews_dir, settings.http_workers)

    # 5. Merge + save JSON (parsing in a small thread pool, I/O bound but cheap).
    saved = 0
    with ThreadPoolExecutor(max_workers=settings.parser_workers) as pool:
        futures = []
        for idx, seller_url, review_url in secondary:
            data = listing_data.get(idx)
            if data is None:
                continue
            futures.append(
                pool.submit(
                    _merge_and_save,
                    idx=idx,
                    data=data,
                    seller_html_path=seller_paths.get(seller_url) if seller_url else None,
                    review_html_path=review_paths.get(review_url) if review_url else None,
                    out_path=ctx.page_dir / f"{idx}.json",
                )
            )
        for future in as_completed(futures):
            try:
                if future.result():
                    saved += 1
            except Exception:  # noqa: BLE001
                log.exception("Merge/save failed")

    log.info("Page %d done: %d JSON files written", ctx.page, saved)


def _parallel_fetch(
    fetcher: HtmlFetcher,
    items: list[tuple[int, str]],
    cache_dir: Path,
    workers: int,
) -> dict[tuple[int, str], Path]:
    out: dict[tuple[int, str], Path] = {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        future_map = {pool.submit(fetcher.fetch, url, cache_dir): (idx, url) for idx, url in items}
        for future in as_completed(future_map):
            key = future_map[future]
            try:
                path = future.result()
            except Exception:  # noqa: BLE001
                log.exception("Fetch raised for %s", key[1])
                continue
            if path:
                out[key] = path
    return out


def _parallel_fetch_unique(
    fetcher: HtmlFetcher,
    urls: list[str],
    cache_dir: Path,
    workers: int,
) -> dict[str, Path]:
    out: dict[str, Path] = {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        future_map = {pool.submit(fetcher.fetch, url, cache_dir): url for url in urls}
        for future in as_completed(future_map):
            url = future_map[future]
            try:
                path = future.result()
            except Exception:  # noqa: BLE001
                log.exception("Fetch raised for %s", url)
                continue
            if path:
                out[url] = path
    return out


def _merge_and_save(
    *,
    idx: int,
    data: dict,
    seller_html_path: Optional[Path],
    review_html_path: Optional[Path],
    out_path: Path,
) -> bool:
    if seller_html_path:
        data = parse_seller(seller_html_path.read_text("utf-8"), data)
    if review_html_path:
        data = parse_reviews(review_html_path.read_text("utf-8"), data)

    out_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    log.debug("[%s] %s → %s", classify(data), idx, out_path)
    return True
