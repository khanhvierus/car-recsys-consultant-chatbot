# crawler/

Optimized cars.com crawler. Replaces the monolithic `Carscrawling_raw.ipynb` notebook
with a modular, resumable, concurrent Python package.

## Why this exists

The legacy notebook had:
- `init_driver()` defined twice (~80 lines duplicated).
- `safe_get_text` / `safe_get_attr` re-defined inside three different parsers.
- A non-deterministic `hash(url)` cache key — broke resume across runs.
- Sequential HTML collection inside an otherwise-parallel pipeline.
- Bare `except:` clauses everywhere, no retries, no 429 handling.
- Selenium for *every* page even when `httpx` would work in 1/20th the time.

This package fixes all of that.

## Architecture at a glance

```
discover_listing_urls(settings)        scrape_listings(settings)
        │                                       │
        ▼                                       ▼
   DriverPool ── (scroll, wait)           HtmlFetcher
   results pages → page_<n>.txt           ├─ httpx (HTTP/2, retries)  ← fast path
                                          └─ DriverPool fallback      ← only on block
                                                  │
                                                  ▼
                                          parsers.py (lxml + shared helpers)
                                                  │
                                                  ▼
                                          raw_data/<page>/<idx>.json
```

| Layer        | Module          | Responsibility                                  |
|--------------|-----------------|-------------------------------------------------|
| Config       | `settings.py`   | URL templates, CSS selectors, runtime settings  |
| Helpers      | `utils.py`      | `stable_hash`, int/float coercion, logging      |
| Parsing      | `parsers.py`    | HTML → dict (pure functions, no I/O)            |
| Browser      | `driver.py`     | Single `init_driver` + thread-safe `DriverPool` |
| Fetching     | `fetcher.py`    | `httpx` first, Selenium fallback, on-disk cache |
| Orchestration| `pipeline.py`   | `discover_listing_urls`, `scrape_listings`      |
| CLI          | `__main__.py`   | `python -m crawler discover|scrape …`           |

## Install

```bash
pip install -r crawler/requirements.txt
```

Pinned versions (verified 2026-04):

| Package            | Version  | Notes                                                                |
|--------------------|----------|----------------------------------------------------------------------|
| selenium           | 4.43.0   | bumped from 3.x. Built-in **Selenium Manager** auto-discovers and downloads Chrome + ChromeDriver — no manual `apt install`, no `webdriver-manager`. |
| beautifulsoup4     | 4.12.3   | now pinned                                                           |
| lxml               | 5.3.0    | new — drop-in fast parser (~2× over html.parser)                     |
| httpx[http2]       | 0.27.2   | new — replaces Selenium for static pages                             |
| tenacity           | 9.0.0    | new — production-grade retries with backoff                          |

**Removed:** `webdriver-manager` (superseded by Selenium Manager in selenium ≥ 4.11; production-mature in 4.43).

## CLI

```bash
# Discover URLs across pages 1-10 of search results
python -m crawler discover --from 1 --to 10

# Full scrape, parallel fetching, resumable
python -m crawler scrape --from 1 --to 10 --http-workers 16

# Disable resume / cache (force re-fetch)
python -m crawler scrape --from 1 --to 10 --no-resume

# Visible browser (debugging)
python -m crawler discover --from 1 --to 1 --no-headless -v
```

## Programmatic use

```python
from pathlib import Path
from crawler import CrawlerSettings, discover_listing_urls, scrape_listings

settings = CrawlerSettings(
    link_dir=Path("car_links"),
    output_dir=Path("raw_data"),
    html_cache_dir=Path("html_cache"),
    start_page=1, end_page=10,
    http_workers=16, selenium_workers=2,
)
discover_listing_urls(settings)
scrape_listings(settings)
```

## Output schema (unchanged from legacy)

```jsonc
{
  "post":   { "title", "price", "mileage", "monthly_payment", "basics_des", "feature_des", "user_history_des", "warranty_des", "image", "new_used" },
  "seller": { "seller_name", "seller_link", "seller_key", "phone_info", "destination", "hours", "seller_rating", "seller_rating_count", "description", "images" },
  "car":    { "car_model", "car_link", "review_link", "car_rating", "ratings", "percentage_recommend", "car_name", "brand", "reviews" },
  "_metadata": { "url", "has_car_link", "has_ratings", "has_percentage", "is_complete" }
}
```

`transform_raw_data.ipynb` consumes this format unchanged.

## Performance notes

- `--blink-settings=imagesEnabled=false` saves ~30% on Selenium page loads.
- `page_load_strategy = "eager"` skips waiting for sub-resources.
- `http2=True` halves connection overhead on `httpx`.
- Connection pool reuses keepalive connections across worker threads.

For a typical run (1 search page = ~50 cars), expect:
- Legacy notebook: ~6–8 min/page (all Selenium, sequential collection).
- This package: ~30–60 sec/page (httpx primary path, parallel).

## Tuning

If you start hitting 429s:
- Lower `http_workers` (default 16 → try 8).
- Increase `inter_request_delay` in `CrawlerSettings`.
- The fetcher already honors `Retry-After` headers automatically.

If httpx is being blocked (you'll see the "falling back to Selenium" log line):
- Increase `selenium_workers` (default 2 → 4).
- Consider adding an outbound proxy in `CrawlerSettings.extra_headers` /
  the `httpx.Client` constructor in `fetcher.py`.
