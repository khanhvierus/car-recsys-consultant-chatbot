"""Centralized configuration: URLs, selectors, runtime settings."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

SITE_BASE = "https://www.cars.com"

RESULTS_URL_TMPL = (
    "https://www.cars.com/shopping/results/?"
    "list_price_max=&makes[]=&maximum_distance=all&models[]=&"
    "page={page}&stock_type=all&zip=60606"
)

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


class Selectors:
    """Single source of truth for CSS selectors. Update here when site changes."""

    # --- Search results ---
    VEHICLE_CARD_LINK = "a.vehicle-card-link"

    # --- Listing detail ---
    NEW_USED = "p.new-used"
    TITLE = "h1.listing-title"
    MILEAGE = "p.listing-mileage"
    PRICE = "span.primary-price"
    PAYMENT_BUTTON = "spark-button.monthly-payment-est-link"
    BASICS_DL = "section.sds-page-section.basics-section dl.fancy-description-list"
    FEATURES_DL = "section.sds-page-section.features-section dl.fancy-description-list"
    HISTORY_DL = "section.sds-page-section.vehicle-history-section dl.fancy-description-list"
    WARRANTY_DL = "section.sds-page-section.warranty_section dl.fancy-description-list"
    GALLERY = "gallery-slides"

    # --- Listing → seller ---
    SELLER_NAME = "h3.spark-heading-5.heading.seller-name"
    SELLER_LINK = "a.sds-rating__link.sds-button-link"

    # --- Listing → car model ---
    CAR_LINK = "div.mmy-page-link a"
    CAR_RATING = "div.vehicle-reviews spark-rating"
    REVIEW_BREAKDOWN = "div.review-breakdown ul.sds-definition-list.review-breakdown--list"
    PERCENTAGE_RECOMMEND = "div.reviews-recommended"

    # --- Seller page ---
    DEALER_PHONES = "div.dealer-phone"
    DEALER_PHONE_TITLE = "span.phone-number-title"
    DEALER_PHONE_NUMBER = "a.phone-number"
    DEALER_ADDRESS = "div.dealer-address"
    DEALER_HOURS_ROWS = "table.dealer-hours tr"
    DEALER_RATING = "div.dealer-info-section spark-rating"
    DEALER_RATING_COUNT = "span.test1.sds-rating__link.sds-button-link"
    DEALER_DESCRIPTION = "div.dealer-description.scrubbed-html"
    DEALER_IMAGES = "div.media-gallery-section img"

    # --- Reviews page ---
    REVIEW_PAGE_TITLE = "div.sds-page-section.vehicle-reviews-page h1"
    REVIEW_BRAND = 'a[data-linkname="research-make"]'
    REVIEW_CONTAINERS = "div.sds-container.consumer-review-container"
    REVIEW_BODY = "p.review-body"
    REVIEW_RATING = "spark-rating"
    REVIEW_TIME = ".review-byline.review-section > div:nth-child(1)"
    REVIEW_BYLINE = ".review-byline.review-section > div:nth-child(2)"
    REVIEW_BREAKDOWN_LIST = ".review-breakdown--list"


@dataclass(slots=True)
class CrawlerSettings:
    """Runtime configuration. Override per-invocation, not via globals."""

    # Paths
    link_dir: Path = Path("car_links")
    output_dir: Path = Path("raw_data")
    html_cache_dir: Path = Path("html_cache")

    # Range
    start_page: int = 1
    end_page: int = 10

    # Concurrency
    http_workers: int = 16          # for httpx fetcher (detail/seller/review)
    selenium_workers: int = 2       # for results-page driver pool
    parser_workers: int = 8

    # Politeness
    request_timeout: float = 30.0
    inter_request_delay: tuple[float, float] = (0.2, 0.6)
    page_delay: tuple[float, float] = (1.5, 3.0)
    max_retries: int = 3
    backoff_base: float = 1.5

    # Selenium — chrome_binary=None lets Selenium Manager (built into
    # selenium 4.43+) auto-install Chrome-for-Testing on first run.
    # Set to "/usr/bin/google-chrome" if you want to pin a system Chrome.
    headless: bool = True
    chrome_binary: str | None = None
    scroll_pause: float = 0.6
    scroll_max_rounds: int = 12
    wait_timeout: int = 20

    # Behavior
    resume: bool = True             # skip already-scraped JSON
    user_agent: str = DEFAULT_USER_AGENT
    extra_headers: dict[str, str] = field(default_factory=dict)
