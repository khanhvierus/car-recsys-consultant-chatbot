"""Cars.com crawler — modular, fast, resumable."""

from .pipeline import discover_listing_urls, scrape_listings
from .settings import CrawlerSettings

__all__ = ["discover_listing_urls", "scrape_listings", "CrawlerSettings"]
__version__ = "1.0.0"
