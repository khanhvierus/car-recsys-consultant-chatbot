"""HTTP fetching with retry, backoff, and Selenium fallback.

Strategy
--------
Detail / seller / review pages on cars.com are server-rendered HTML, so we
fetch them with ``httpx`` (HTTP/2, keep-alive, ~10–20× faster than Selenium).
If the response looks like a bot-block (403/429/captcha body), we fall through
to a Selenium driver.

Search-results pages are NOT fetched here — they need scrolling, so the
pipeline drives them through ``DriverPool`` directly.
"""

from __future__ import annotations

import logging
import random
import threading
import time
from pathlib import Path
from typing import Optional

import httpx
from tenacity import (
    RetryError,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
    wait_random,
)

from .driver import DriverPool
from .settings import CrawlerSettings
from .utils import stable_hash

log = logging.getLogger(__name__)

# Heuristic markers for bot-blocked responses.
_BLOCK_MARKERS = ("captcha", "Access Denied", "Pardon Our Interruption")


class _Retryable(Exception):
    """Raised to signal tenacity that this attempt should be retried."""


class HtmlFetcher:
    """Hybrid HTTP-first / Selenium-fallback fetcher with on-disk caching.

    Thread-safe: uses a single ``httpx.Client`` (httpx clients are thread-safe)
    and per-call locking is unnecessary because the cache is content-addressed.
    """

    def __init__(self, settings: CrawlerSettings, driver_pool: Optional[DriverPool] = None):
        self._settings = settings
        self._driver_pool = driver_pool
        self._delay_lock = threading.Lock()
        self._last_request_at = 0.0

        headers = {"User-Agent": settings.user_agent, **settings.extra_headers}
        self._client = httpx.Client(
            http2=True,
            headers=headers,
            timeout=settings.request_timeout,
            follow_redirects=True,
            limits=httpx.Limits(
                max_connections=settings.http_workers * 2,
                max_keepalive_connections=settings.http_workers,
            ),
        )

    # ------------------------------------------------------------------ API

    def fetch(self, url: str, cache_dir: Path) -> Optional[Path]:
        """Fetch ``url`` to ``cache_dir`` and return the saved file path.

        - Resumable: returns the cached path immediately if the file exists
          and ``settings.resume`` is True.
        - Falls back to Selenium on bot-block.
        """
        cache_dir.mkdir(parents=True, exist_ok=True)
        path = cache_dir / f"{stable_hash(url)}.html"
        if self._settings.resume and path.exists() and path.stat().st_size > 0:
            return path

        html = self._try_httpx(url) or self._try_selenium(url)
        if not html:
            return None

        path.write_text(html, encoding="utf-8")
        return path

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "HtmlFetcher":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    # --------------------------------------------------------------- httpx

    def _try_httpx(self, url: str) -> Optional[str]:
        self._respect_delay()

        @retry(
            stop=stop_after_attempt(self._settings.max_retries),
            wait=wait_exponential(multiplier=self._settings.backoff_base, min=1, max=20)
            + wait_random(0, 1),
            retry=retry_if_exception_type((_Retryable, httpx.TransportError)),
            reraise=False,
        )
        def _do() -> str:
            resp = self._client.get(url)
            if resp.status_code == 429:
                # Honor Retry-After if provided.
                wait = float(resp.headers.get("Retry-After", "5"))
                log.warning("429 from %s — sleeping %.1fs before retry", url, wait)
                time.sleep(wait)
                raise _Retryable("rate limited")
            if 500 <= resp.status_code < 600:
                raise _Retryable(f"server {resp.status_code}")
            if resp.status_code != 200:
                # 4xx other than 429 = give up on httpx, let Selenium try.
                raise httpx.HTTPStatusError("non-200", request=resp.request, response=resp)
            text = resp.text
            if any(marker in text for marker in _BLOCK_MARKERS):
                raise httpx.HTTPStatusError("blocked", request=resp.request, response=resp)
            return text

        try:
            return _do()
        except RetryError:
            log.warning("httpx exhausted retries for %s", url)
        except httpx.HTTPStatusError as exc:
            log.info("httpx %s on %s — falling back to Selenium", exc, url)
        except Exception as exc:  # noqa: BLE001 — log and try fallback
            log.warning("httpx error on %s: %s", url, exc)
        return None

    # ------------------------------------------------------------ selenium

    def _try_selenium(self, url: str) -> Optional[str]:
        if self._driver_pool is None:
            return None
        try:
            with self._driver_pool.borrow() as driver:
                driver.get(url)
                # Tiny dwell so dynamic content settles.
                time.sleep(random.uniform(0.4, 1.0))
                return driver.page_source
        except Exception as exc:  # noqa: BLE001
            log.warning("Selenium fallback failed for %s: %s", url, exc)
            return None

    # ---------------------------------------------------------- politeness

    def _respect_delay(self) -> None:
        lo, hi = self._settings.inter_request_delay
        with self._delay_lock:
            now = time.monotonic()
            wait = max(0.0, lo - (now - self._last_request_at)) + random.uniform(0, hi - lo)
            self._last_request_at = now + wait
        if wait > 0:
            time.sleep(wait)
