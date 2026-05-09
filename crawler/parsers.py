"""HTML → dict parsers. Pure functions: HTML in, dict out, no I/O.

The output schema matches the legacy notebook exactly so downstream
``transform_raw_data.ipynb`` keeps working.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from bs4 import BeautifulSoup, Tag

from .settings import SITE_BASE, Selectors as S
from .utils import to_float, to_int

log = logging.getLogger(__name__)

_PARSER = "lxml"  # ~2× faster than html.parser


# ---------------------------------------------------------------------------
# Shared low-level helpers — replace the inline duplicates in the legacy code.
# ---------------------------------------------------------------------------

def make_soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, _PARSER)


def _text(node: Optional[Tag], default: Optional[str] = None) -> Optional[str]:
    if node is None:
        return default
    value = node.get_text(strip=True)
    return value if value else default


def _attr(node: Optional[Tag], name: str, default: Any = None) -> Any:
    if node is None or not hasattr(node, "get"):
        return default
    return node.get(name, default)


def _parse_dl(section: Optional[Tag], list_values: bool = False) -> dict:
    """Parse a <dl class='fancy-description-list'> into {dt: dd} pairs.

    Handles MPG specially (nested span), splits multi-value lists when asked.
    """
    out: dict = {}
    if section is None:
        return out
    for dt in section.find_all("dt", recursive=False):
        key = _text(dt)
        dd = dt.find_next_sibling("dd")
        if not key or dd is None:
            continue
        if key == "MPG":
            mpg = dd.find("span", attrs={"slot": "trigger"})
            out[key] = _text(mpg)
            continue
        raw = _text(dd, default="")
        if list_values:
            tokens = raw.replace("\n\n", "").replace("\n", ",").split(",")
            out[key] = [t.strip() for t in tokens if t.strip()]
        else:
            out[key] = raw if raw else None
    return out


# ---------------------------------------------------------------------------
# Listing detail page
# ---------------------------------------------------------------------------

def parse_listing(html: str, url: str = "") -> Optional[dict]:
    """Parse a vehicle detail page. Returns the canonical {post, seller, car, _metadata}."""
    if not html:
        return None
    try:
        soup = make_soup(html)
    except Exception as exc:
        log.warning("Failed to parse listing HTML for %s: %s", url, exc)
        return None

    post = _parse_post_section(soup)
    seller_stub = _parse_seller_stub(soup)
    car_stub = _parse_car_stub(soup)

    return {
        "post": post,
        "seller": seller_stub,
        "car": car_stub,
        "_metadata": {
            "url": url,
            "has_car_link": bool(car_stub.get("car_link")),
            "has_ratings": car_stub.get("car_rating") is not None,
            "has_percentage": car_stub.get("percentage_recommend") is not None,
            "is_complete": bool(
                post.get("title") and seller_stub.get("seller_name") and post.get("price")
            ),
        },
    }


def _parse_post_section(soup: BeautifulSoup) -> dict:
    payment_btn = soup.select_one(S.PAYMENT_BUTTON)
    gallery = soup.select_one(S.GALLERY)
    images = (
        [src for src in (img.get("src") for img in gallery.find_all("img", recursive=False)) if src]
        if gallery
        else None
    )

    return {
        "new_used": _text(soup.select_one(S.NEW_USED)),
        "title": _text(soup.select_one(S.TITLE)),
        "mileage": to_int(_text(soup.select_one(S.MILEAGE))),
        "price": to_int(_text(soup.select_one(S.PRICE))),
        "monthly_payment": to_int(_attr(payment_btn, "phx-value-monthly-payment")),
        "basics_des": _parse_dl(soup.select_one(S.BASICS_DL)) or None,
        "feature_des": _parse_dl(soup.select_one(S.FEATURES_DL), list_values=True) or None,
        "user_history_des": _parse_dl(soup.select_one(S.HISTORY_DL)) or None,
        "warranty_des": _normalize_warranty(_parse_dl(soup.select_one(S.WARRANTY_DL))) or None,
        "image": images,
    }


def _normalize_warranty(d: dict) -> dict:
    """Convert dash placeholders to None to match legacy output."""
    return {k: (None if v in {"–", "—"} else v) for k, v in d.items()}


def _parse_seller_stub(soup: BeautifulSoup) -> dict:
    link_tag = soup.select_one(S.SELLER_LINK)
    href = _attr(link_tag, "href")
    seller_link = SITE_BASE + href if href else None
    seller_key = seller_link.split("/")[-2] if seller_link and "/" in seller_link else None
    return {
        "seller_name": _text(soup.select_one(S.SELLER_NAME)),
        "seller_link": seller_link,
        "seller_key": seller_key,
    }


def _parse_car_stub(soup: BeautifulSoup) -> dict:
    car_link_tag = soup.select_one(S.CAR_LINK)
    car_model = _attr(car_link_tag, "data-slugs")
    href = _attr(car_link_tag, "href")
    car_link = SITE_BASE + href if href else None
    review_link = car_link + "consumer-reviews/?page_size=200" if car_link else None

    rating_tag = soup.select_one(S.CAR_RATING)
    car_rating = _attr(rating_tag, "rating")

    ratings: dict[str, float | str] = {}
    breakdown = soup.select_one(S.REVIEW_BREAKDOWN)
    if breakdown:
        for li in breakdown.select("li"):
            name = _text(li.select_one(".sds-definition-list__display-name"))
            raw = _text(li.select_one(".sds-definition-list__value"))
            if not name or raw is None:
                continue
            ratings[name] = to_float(raw) if to_float(raw) is not None else raw

    pct_text = _text(soup.select_one(S.PERCENTAGE_RECOMMEND), default="")
    pct = None
    if pct_text:
        head = pct_text.split(" ", 1)[0].rstrip("%")
        pct = to_float(head)

    return {
        "car_model": car_model,
        "car_link": car_link,
        "review_link": review_link,
        "car_rating": car_rating,
        "ratings": ratings or None,
        "percentage_recommend": pct,
    }


# ---------------------------------------------------------------------------
# Seller page — merges into existing dict
# ---------------------------------------------------------------------------

def parse_seller(html: str, data: dict) -> dict:
    """Enrich `data` with seller details. Mutates a shallow copy of seller dict."""
    if not html:
        return data
    try:
        soup = make_soup(html)
    except Exception as exc:
        log.warning("Failed to parse seller HTML: %s", exc)
        return data

    seller = dict(data.get("seller") or {})
    seller["phone_info"] = _parse_phones(soup)
    seller["destination"] = _text(soup.select_one(S.DEALER_ADDRESS))
    seller["hours"] = _parse_hours(soup)
    seller["seller_rating"], seller["seller_rating_count"] = _parse_seller_rating(soup)
    seller["description"] = _text(soup.select_one(S.DEALER_DESCRIPTION))
    seller["images"] = _parse_seller_images(soup)

    return {**data, "seller": seller}


def _parse_phones(soup: BeautifulSoup) -> dict[str, str]:
    out: dict[str, str] = {}
    for phone in soup.select(S.DEALER_PHONES):
        ptype = _text(phone.select_one(S.DEALER_PHONE_TITLE), default="Unknown")
        number = _text(phone.select_one(S.DEALER_PHONE_NUMBER))
        if ptype and number:
            out[ptype] = number
    return out


def _parse_hours(soup: BeautifulSoup) -> dict[str, str]:
    out: dict[str, str] = {}
    for row in soup.select(S.DEALER_HOURS_ROWS):
        cells = row.find_all("td")
        if len(cells) == 2:
            key = cells[0].get_text(strip=True).rstrip(":")
            value = cells[1].get_text(strip=True)
            if key:
                out[key] = value
    return out


def _parse_seller_rating(soup: BeautifulSoup) -> tuple[Optional[float], Optional[int]]:
    rating_tag = soup.select_one(S.DEALER_RATING)
    if not rating_tag:
        return None, None
    rating = to_float(rating_tag.get("rating"))
    count_node = rating_tag.select_one(S.DEALER_RATING_COUNT)
    count = to_int(_text(count_node))
    return rating, count


def _parse_seller_images(soup: BeautifulSoup) -> Optional[list[str]]:
    imgs = [img.get("src") for img in soup.select(S.DEALER_IMAGES)]
    imgs = [src for src in imgs if src]
    return imgs or None


# ---------------------------------------------------------------------------
# Reviews page — merges into existing dict's car{}
# ---------------------------------------------------------------------------

def parse_reviews(html: str, data: dict) -> dict:
    if not html:
        return data
    try:
        soup = make_soup(html)
    except Exception as exc:
        log.warning("Failed to parse reviews HTML: %s", exc)
        return data

    car = dict(data.get("car") or {})

    title = _text(soup.select_one(S.REVIEW_PAGE_TITLE))
    car["car_name"] = title.replace(" consumer reviews", "") if title else None
    car["brand"] = _text(soup.select_one(S.REVIEW_BRAND))

    reviews: list[dict] = []
    for container in soup.select(S.REVIEW_CONTAINERS):
        review = _parse_one_review(container)
        if review is not None:
            reviews.append(review)
    car["reviews"] = reviews or None

    return {**data, "car": car}


def _parse_one_review(container: Tag) -> Optional[dict]:
    body = container.select_one(S.REVIEW_BODY)
    if body is None:
        return None

    rating_tag = container.select_one(S.REVIEW_RATING)
    overall = to_float(_attr(rating_tag, "rating"))

    byline = container.select_one(S.REVIEW_BYLINE)
    user_name: Optional[str] = None
    from_loc: Optional[str] = None
    if byline:
        text = byline.get_text(strip=True)
        # Format observed: "By <username> from <location>"
        try:
            user_name = text.split("By ", 1)[1].split(" from ", 1)[0]
            from_loc = text.split(" from ", 1)[1].strip()
        except IndexError:
            user_name = text or None

    breakdown: dict = {}
    list_node = container.select_one(S.REVIEW_BREAKDOWN_LIST)
    if list_node:
        for li in list_node.select("li"):
            key = _text(li.select_one(".sds-definition-list__display-name"))
            raw = _text(li.select_one(".sds-definition-list__value"))
            if not key:
                continue
            breakdown[key] = to_float(raw) if to_float(raw) is not None else raw

    return {
        "overall_rating": overall,
        "time": _text(container.select_one(S.REVIEW_TIME)),
        "user_name": user_name,
        "from": from_loc,
        "review": _text(body),
        "ratings_breakdown": breakdown,
    }


# ---------------------------------------------------------------------------
# Search results page — for URL discovery
# ---------------------------------------------------------------------------

def extract_listing_links(html: str) -> list[str]:
    soup = make_soup(html)
    out: list[str] = []
    for a in soup.select(S.VEHICLE_CARD_LINK):
        href = a.get("href")
        if href and "/vehicledetail/" in href:
            out.append(href if href.startswith("http") else SITE_BASE + href)
    return out


# ---------------------------------------------------------------------------
# Result classification
# ---------------------------------------------------------------------------

def classify(data: Optional[dict]) -> str:
    if not data:
        return "failed"
    meta = data.get("_metadata") or {}
    if meta.get("is_complete"):
        return "complete" if (meta.get("has_car_link") and meta.get("has_ratings")) else "partial_no_reviews"
    return "partial"
