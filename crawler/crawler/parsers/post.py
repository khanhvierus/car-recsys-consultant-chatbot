"""Parse the listing block of a car detail page (price, basics, features, ...)."""
from __future__ import annotations

import re
from pathlib import Path

from bs4 import BeautifulSoup

from crawler.config import IMG_BASE_DIR
from crawler.utils import attr, download_images, text, to_int


def parse_post(soup: BeautifulSoup) -> dict:
    post: dict = {}

    title_raw = text(soup.select_one("#vehicle-title"))
    if title_raw:
        parts = title_raw.split(" ", 1)
        post["new_used"] = parts[0]
        post["title"] = parts[1] if len(parts) > 1 else None
    else:
        post["new_used"] = post["title"] = None

    post["mileage"] = to_int(text(soup.select_one("div.msrp")))
    post["price"] = to_int(text(soup.select_one(".list-price")))
    post["monthly_payment"] = to_int(
        text(soup.select_one('fuse-stack[data-qa="monthly-payment"] fuse-button'))
    )

    basics: dict = {}
    subtitle = text(
        soup.select_one("section#features-and-specs div.subtitle"), default=""
    )
    for pattern, key in [
        (r"VIN:\s*([A-Z0-9]+)", "VIN"),
        (r"Stock #:\s*([A-Z0-9]+)", "Stock Number"),
    ]:
        m = re.search(pattern, subtitle)
        if m:
            basics[key] = m.group(1)

    for entry in soup.select('div.basics li[data-qa="basics-entry"]'):
        raw = text(entry)
        if not raw:
            continue
        m = re.search(
            r"(?i)(.*)\s+(exterior color|interior color|fuel type|engine|mpg|drivetrain|transmission)$",
            raw,
        )
        if m:
            val, k = m.group(1).strip(), m.group(2).strip().title()
            basics["MPG" if k.lower() == "mpg" else k] = val
    post["basic_desc"] = basics or None

    features: dict = {}
    for block in soup.select("div.highlight-feature"):
        k = text(block.select_one("h3.features-spec-heading"))
        if k:
            features[k] = [text(li) for li in block.select('li[data-qa="spec-value"]')]
    post["feature_des"] = features or None

    history: dict = {}
    for span in soup.select("section#vehicle_history_report fuse-list ul li span"):
        t = text(span, default="").lower()
        if "accident" in t or "damage" in t:
            history["Accidents or damage"] = (
                "None reported" if t.startswith("no ") else "At least 1 reported"
            )
        elif "owner" in t:
            history["1-owner vehicle"] = "Yes" if "1 owner" in t else "No"
        elif "personal use" in t:
            history["Personal use only"] = "Yes"
        elif "recall" in t:
            history["Open recall"] = (
                "None reported" if "no " in t else "At least 1 reported"
            )
        elif "title" in t:
            history["Clean Title"] = "Yes" if "clean" in t else "No"
    post["user_history_des"] = history or None

    warranty: dict = {}
    _DASH = {"-", "–", "—"}
    for dt in soup.select(
        "section.sds-page-section.warranty_section dl.fancy-description-list dt"
    ):
        k, v = text(dt), text(dt.find_next_sibling("dd"))
        if k and v:
            warranty[k] = None if v in _DASH else v
    for dt in soup.select("fuse-popover#cpo-popover dl dt"):
        k = text(dt)
        v = " ".join((text(dt.find_next_sibling("dd"), default="")).split())
        if k and v:
            warranty[k] = None if v in _DASH else v
    post["warranty_des"] = warranty or None

    imgs = [
        attr(img, "src", "").split("?")[0]
        for img in soup.select("fuse-gallery-grid#gallery img")[:5]
        if attr(img, "src")
    ]
    post["image"] = imgs or None
    if imgs:
        vin = basics.get("VIN") or basics.get("Stock Number") or "Unknown"
        download_images(imgs, Path(IMG_BASE_DIR) / "post_images" / vin)

    return post
