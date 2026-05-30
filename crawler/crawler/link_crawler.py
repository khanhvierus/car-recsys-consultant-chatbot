"""
Crawl listing-result pages to collect detail URLs.
Single browser session so the Cloudflare cookie stays alive across pages.
"""
from __future__ import annotations

import random
import time
from pathlib import Path
from urllib.parse import urljoin

from seleniumbase import SB

from crawler.browser import get_soup
from crawler.config import (
    CHROME_BINARY,
    HEADLESS,
    LINK_CRAWL_DELAY,
    LINK_CRAWL_MAX_RETRIES,
    LINK_FOLDER,
    RESULTS_URL_TMPL,
    SITE_BASE,
    USE_XVFB,
)
from crawler.logging_setup import get_logger

log = get_logger(__name__)


def crawl_listing_urls(
    start_page: int,
    end_page: int,
    output_dir: Path = LINK_FOLDER,
    delay: float = LINK_CRAWL_DELAY,
    max_retries: int = LINK_CRAWL_MAX_RETRIES,
) -> None:
    """
    Crawl pages [start_page, end_page] inclusive. Resumable: pages with a
    non-empty link file are skipped.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Mode selection (priority): xvfb (Colab) > headless (Docker/CI) > GUI (host).
    # GUI mode gives the best Cloudflare bypass — use it when HEADLESS=false
    # AND USE_XVFB=false AND a real DISPLAY is available.
    _sb_kwargs = dict(uc=True, locale="en", binary_location=CHROME_BINARY)
    if USE_XVFB:
        _sb_kwargs["xvfb"] = True
    elif HEADLESS:
        _sb_kwargs["headless"] = True
    # else: real GUI — pass nothing, SB attaches to $DISPLAY
    with SB(**_sb_kwargs) as sb:
        for page in range(start_page, end_page + 1):
            page_file = output_dir / f"page_{page}.txt"

            if page_file.exists() and page_file.stat().st_size > 0:
                existing = page_file.read_text().strip().splitlines()
                log.info(
                    "[%s/%s] Already have %d links — skipping",
                    page, end_page, len(existing),
                )
                continue

            url = RESULTS_URL_TMPL.format(page=page)
            success = False

            for attempt in range(1, max_retries + 1):
                try:
                    log.info(
                        "[%s/%s] Attempt %s/%s: %s",
                        page, end_page, attempt, max_retries, url,
                    )
                    soup = get_soup(
                        sb, url, target_css="a[data-card-link]", scroll=True
                    )
                    links = [
                        urljoin(SITE_BASE, tag["href"])
                        for tag in soup.select("a[data-card-link]")
                        if tag.get("href") and "/vehicledetail/" in tag["href"]
                    ]
                    if not links:
                        raise ValueError("No links found — possible block")

                    page_file.write_text("\n".join(links) + "\n", encoding="utf-8")
                    log.info("Saved %d links → %s", len(links), page_file)
                    success = True
                    break

                except Exception as e:
                    wait = (2 ** attempt) + random.uniform(1, 3)
                    log.warning("Error: %s", e)
                    if attempt < max_retries:
                        log.info("Backoff %.1fs before retry...", wait)
                        time.sleep(wait)

            if not success:
                log.error(
                    "Page %s failed after %s attempts — continuing", page, max_retries
                )

            time.sleep(delay + random.uniform(0.5, 1.5))

    log.info('Done. Links saved to "%s"', output_dir)
