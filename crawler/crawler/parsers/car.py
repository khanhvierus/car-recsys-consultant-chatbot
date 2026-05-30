"""Parser for the car-model section: rating breakdowns and consumer reviews."""
from __future__ import annotations

import re

from bs4 import BeautifulSoup

from crawler.utils import absolute_url, attr, text


def parse_car(soup: BeautifulSoup) -> dict:
    car: dict = {}

    rating_text = text(
        soup.select_one(
            "section#consumer-reviews div.rating-out-of span.rating-count"
        )
    )
    car["car_rating"] = float(rating_text) if rating_text else None

    rating_div = soup.select_one(".rating-out-of")
    count_text = text(rating_div.find_next_sibling("div") if rating_div else None)
    m = re.search(r"Based on ([\d,]+) reviews", count_text) if count_text else None
    car["car_rating_count"] = int(m.group(1).replace(",", "")) if m else None

    breakdown: dict = {}
    for div in soup.select(
        "section#consumer-reviews div.ratings-breakdown div.review-text"
    ):
        strong = text(div.find("strong"))
        if strong:
            cat = text(div).replace(strong, "").strip()
            try:
                breakdown[cat] = float(strong)
            except ValueError:
                breakdown[cat] = strong
    car["ratings"] = breakdown or None

    subtitle = text(soup.select_one("section#consumer-reviews div.subtitle"))
    m = re.search(r"(\d+(?:\.\d+)?)%", subtitle) if subtitle else None
    car["percentage_recommend"] = float(m.group(1)) if m else None

    raw_url = attr(
        soup.select_one('fuse-button.review-btn-secondary[href*="write-a-review"]'),
        "href",
    )
    if raw_url:
        full_url = absolute_url(raw_url)
        car["car_link"] = full_url.replace("write-a-review/", "")
        parts = [p for p in full_url.split("/") if p]
        if "write-a-review" in parts:
            idx = parts.index("write-a-review")
            slug = parts[idx - 1]
            car["car_model"] = slug
            car["brand"] = slug.split("-")[0].replace("_", " ").title()
            slug_parts = slug.split("-")
            if slug_parts[-1].isdigit() and len(slug_parts[-1]) == 4:
                year = slug_parts.pop()
                car["car_name"] = f'{year} {" ".join(slug_parts).title()}'
            else:
                car["car_name"] = " ".join(slug_parts).title()
        car["review_link"] = (
            car["car_link"] + "consumer-reviews/?page_size=40"
            if car.get("car_link")
            else None
        )
    else:
        car.update(
            car_model=None, car_link=None, review_link=None, brand=None, car_name=None
        )

    reviews = []
    for block in soup.select("div.consumer-review-container"):
        r: dict = {}
        rating_el = block.select_one("fuse-rating, spark-rating")
        r["overall_rating"] = (
            float(attr(rating_el, "rating")) if attr(rating_el, "rating") else None
        )

        time_el = block.select_one(".review-date") or block.select_one(
            ".review-byline > div:nth-child(1)"
        )
        r["time"] = text(time_el)

        author_el = block.select_one(
            ".author-details > div:first-child, .review-byline > div:nth-child(2)"
        )
        byline = text(author_el, default="")
        if byline.startswith("By "):
            byline = byline[3:]
        if " from " in byline:
            name, loc = byline.split(" from ", 1)
            r["user_name"], r["from"] = name.strip(), loc.strip()
        elif " on " in byline:
            name, loc = byline.split(" on ", 1)
            r["user_name"], r["from"] = name.strip(), loc.strip()
        else:
            r["user_name"], r["from"] = byline.strip(), None

        r["title"] = text(block.select_one("h3.title"))

        rb: dict = {}
        for stack in block.select(".ratings-breakdown fuse-stack"):
            div = stack.select_one(".review-text")
            sv = text(div.find("strong") if div else None)
            if sv:
                k = text(div).replace(sv, "").strip()
                try:
                    rb[k] = float(sv)
                except ValueError:
                    rb[k] = sv
        if not rb:
            for li in block.select(".review-breakdown--list li"):
                k = text(li.select_one(".sds-definition-list__display-name"))
                v = text(li.select_one(".sds-definition-list__value"))
                if k and v:
                    try:
                        rb[k] = float(v)
                    except ValueError:
                        rb[k] = v
        r["ratings_breakdown"] = rb or None

        clamp = block.select_one("cars-line-clamp")
        if clamp:
            fb = clamp.select_one(".review-feedback")
            if fb:
                fb.extract()
            r["review"] = text(clamp)
        else:
            r["review"] = text(block.select_one("p.review-body"))

        if r.get("review") or r.get("title"):
            reviews.append(r)

    car["reviews"] = reviews or None
    return car
