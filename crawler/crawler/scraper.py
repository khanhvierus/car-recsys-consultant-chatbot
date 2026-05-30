"""High-level scrapers that compose browser + parsers."""
from __future__ import annotations

from datetime import datetime

from crawler.browser import get_soup
from crawler.logging_setup import get_logger
from crawler.parsers import parse_car, parse_dealer_page, parse_post, parse_seller

log = get_logger(__name__)


def scrape_listing(sb, url: str) -> dict | None:
    """Scrape one car detail page. Reuses the sb session."""
    soup = get_soup(
        sb, url, target_css="div.vehicle-details, #vehicle-title, .list-price"
    )
    if soup is None:
        return None
    return {
        "datetime": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "post": parse_post(soup),
        "seller": parse_seller(soup),
        "car": parse_car(soup),
    }


def scrape_dealer(sb, url: str, data: dict) -> dict:
    """Enrich data with dealer phone/hours. Returns data unchanged on failure."""
    try:
        soup = get_soup(
            sb, url, target_css="div.dealer-contact-section, div.dealer-info"
        )
        return parse_dealer_page(soup, data)
    except Exception as e:
        log.warning("scrape_dealer error: %s", e)
        return data


def scrape_full(sb, url: str) -> dict | None:
    """Scrape listing + dealer page. Returns merged result or None on failure."""
    try:
        data = scrape_listing(sb, url)
        if data:
            seller_url = data.get("seller", {}).get("seller_link")
            if seller_url:
                data = scrape_dealer(sb, seller_url, data)
        return data
    except Exception as e:
        log.error("scrape_full error: %s", e)
        return None
