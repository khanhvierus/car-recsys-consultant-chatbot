"""Small parsing / IO helpers shared by all parsers."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import requests

from crawler.config import IMAGE_DOWNLOAD_TIMEOUT, SITE_BASE
from crawler.logging_setup import get_logger

log = get_logger(__name__)


def text(el, default: Any = None, strip: bool = True) -> Any:
    """Safely .get_text() from a BeautifulSoup element."""
    if el is None:
        return default
    try:
        return el.get_text(strip=strip)
    except Exception:
        return default


def attr(el, name: str, default: Any = None) -> Any:
    """Safely read an attribute from a BeautifulSoup element."""
    if el is None or not hasattr(el, "get"):
        return default
    try:
        return el.get(name)
    except Exception:
        return default


def to_int(raw: str | None) -> int | None:
    """Strip non-digits and cast to int. None if nothing left."""
    if not isinstance(raw, str) or not raw:
        return None
    cleaned = re.sub(r"\D", "", raw)
    return int(cleaned) if cleaned else None


def absolute_url(href: str | None) -> str | None:
    return urljoin(SITE_BASE, href) if href else None


def download_images(urls: list[str], folder: Path) -> None:
    """Download each URL to folder/{i}.jpg. Best-effort, logs errors."""
    if not urls:
        return
    folder.mkdir(parents=True, exist_ok=True)
    for i, url in enumerate(urls, 1):
        try:
            resp = requests.get(url, timeout=IMAGE_DOWNLOAD_TIMEOUT)
            if resp.status_code == 200:
                (folder / f"{i}.jpg").write_bytes(resp.content)
        except Exception as e:
            log.warning("Image download failed (%s): %s", url, e)
