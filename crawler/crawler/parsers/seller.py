"""Parsers for the seller block on the detail page and the dealer page."""
from __future__ import annotations

import copy
import re
from pathlib import Path

from bs4 import BeautifulSoup

from crawler.config import IMG_BASE_DIR
from crawler.utils import absolute_url, attr, download_images, text


def parse_seller(soup: BeautifulSoup) -> dict:
    seller: dict = {}
    seller["seller_name"] = text(soup.select_one("div.dealer-info h3"))

    raw_link = attr(
        soup.select_one("div.dealer-info fuse-stack.rating-stack a"), "href"
    )
    if raw_link:
        link = absolute_url(raw_link)
        seller["seller_link"] = link
        parts = [p for p in link.split("#")[0].split("/") if p]
        seller["seller_key"] = parts[-1] if parts else None
    else:
        seller["seller_link"] = seller["seller_key"] = None

    seller["destination"] = text(soup.select_one("div.dealer-info div.map-link a"))
    seller["seller_website"] = attr(
        soup.select_one("div.dealer-info div.website a"), "href"
    )

    rating_tag = soup.select_one("fuse-stack.rating-stack fuse-rating")
    raw_rating = attr(rating_tag, "rating")
    seller["seller_rating"] = float(raw_rating) if raw_rating else None

    review_text = text(rating_tag.find("a") if rating_tag else None)
    if review_text:
        m = re.search(r"[\d,]+", review_text)
        seller["seller_rating_count"] = (
            int(m.group(0).replace(",", "")) if m else None
        )
    else:
        seller["seller_rating_count"] = None

    highlights = [
        text(li) for li in soup.select("div.highlights-tab fuse-list ul li") if text(li)
    ]
    seller["highlights"] = highlights or None
    seller["description"] = text(
        soup.select_one("div.about-tab__carsons-summary-body cars-line-clamp p")
    )

    imgs = [
        attr(img, "src", "").split("?")[0]
        for img in soup.select("card-gallery.dealership-gallery img")[:2]
        if attr(img, "src")
    ]
    seller["image"] = imgs or None
    if imgs:
        folder_name = seller.get("seller_key") or "Unknown_Seller"
        download_images(imgs, Path(IMG_BASE_DIR) / "seller_images" / folder_name)

    return seller


def parse_dealer_page(soup: BeautifulSoup, data: dict) -> dict:
    """Enrich an already-scraped record with phone numbers and opening hours."""
    out = copy.deepcopy(data)
    phones: dict = {}
    for div in soup.select("div.dealer-phone"):
        kind = text(div.select_one("span.phone-number-title"), default="Unknown")
        number = text(div.select_one("a.phone-number"))
        if kind and number:
            phones[kind] = number
    out["seller"]["phone_info"] = phones

    hours: dict = {}
    for row in soup.select("table.dealer-hours tr"):
        cells = row.find_all("td")
        if len(cells) == 2:
            hours[text(cells[0], default="").rstrip(":")] = text(cells[1])
    out["seller"]["hours"] = hours
    return out
