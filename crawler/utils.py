"""Small, dependency-free helpers used by parsers and pipeline."""

from __future__ import annotations

import hashlib
import logging
import re
from typing import Optional

log = logging.getLogger(__name__)


def stable_hash(value: str, length: int = 16) -> str:
    """Deterministic hash for cache filenames. SHA1 — not for security."""
    return hashlib.sha1(value.encode("utf-8")).hexdigest()[:length]


_DIGITS_RE = re.compile(r"\D")


def to_int(text: Optional[str]) -> Optional[int]:
    """Strip non-digits and convert to int. Returns None on failure or empty."""
    if not text:
        return None
    digits = _DIGITS_RE.sub("", text)
    return int(digits) if digits else None


def to_float(text: Optional[str]) -> Optional[float]:
    if not text:
        return None
    try:
        return float(text)
    except (ValueError, TypeError):
        return None


def configure_logging(level: int = logging.INFO) -> None:
    """One-shot logger setup. Idempotent — safe to call repeatedly."""
    root = logging.getLogger()
    if root.handlers:
        return
    handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s", "%H:%M:%S")
    )
    root.addHandler(handler)
    root.setLevel(level)
