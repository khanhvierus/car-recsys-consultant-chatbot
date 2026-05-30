# Cars.com crawler

A modular reimplementation of the original Colab notebook. Each run processes
**one** listing page end-to-end:

```
crawl-links  →  scrape-detail  →  upload-gcs
```

Runs on the **host** (not Docker): cars.com's Cloudflare Turnstile needs real
Chrome via Xvfb, which the container can't reliably solve. Orchestration is
Temporal — see [temporal_app/README.md](temporal_app/README.md).

## Repository layout

```
crawler/
├── crawler/                       # the scraper package
│   ├── config.py                  # env-var driven config
│   ├── logging_setup.py
│   ├── utils.py                   # text/attr/to_int/download_images
│   ├── browser.py                 # SeleniumBase UC navigation + Turnstile
│   ├── parsers/                   # post / seller / car HTML → dict
│   ├── scraper.py                 # scrape_listing / dealer / full
│   ├── link_crawler.py            # page-level link crawler
│   ├── detail_scraper.py          # detail-page scraper
│   ├── gcs_uploader.py            # JSON + image upload to GCS
│   └── main.py                    # CLI entrypoint
├── temporal_app/                  # Temporal workflows/activities/worker
│   ├── workflows.py  activities.py  worker.py  client.py
│   ├── pipeline/                  # bronze loader + ML jobs (transform/ML)
│   └── scripts/                   # trigger_once.py  create_schedule.py
├── run_local.sh                   # run one crawl stage standalone (debug)
├── run_worker.sh                  # run the Temporal worker
└── requirements.txt
```

## Run a single stage standalone (debug, no Temporal)

```bash
./run_local.sh crawl-links   --page 1   # URLs → local_data/car_links/page_1.txt
./run_local.sh scrape-detail --page 1   # details → local_data/raw_data/1/<idx>.json
./run_local.sh full          --page 1   # all three in sequence
```

Browser mode (default `xvfb` — no window pops up):

```bash
BROWSER_MODE=gui      ./run_local.sh crawl-links --page 1   # visible window
BROWSER_MODE=headless ./run_local.sh crawl-links --page 1   # no display
```

First run creates `.venv` and installs deps. Requires Google Chrome on the host
and (for `xvfb` mode) the `xvfb` package: `sudo apt install -y xvfb python3-tk`.

## Run via Temporal (scheduled weekly)

See [temporal_app/README.md](temporal_app/README.md). In short:

```bash
cd ../car-recsys-system && docker compose up -d temporal temporal-ui   # server
cd ../crawler && ./run_worker.sh                                       # worker (host)
.venv/bin/python -m temporal_app.scripts.trigger_once crawl           # one run
.venv/bin/python -m temporal_app.scripts.create_schedule              # weekly cron
```

## Configuration (env vars)

All knobs in `crawler/config.py` are env-driven:

| Var                              | Default                  | Notes                            |
| -------------------------------- | ------------------------ | -------------------------------- |
| `PAGE_NUMBER`                    | `1`                      | Single page to process           |
| `DATA_ROOT`                      | `./local_data`           | Root for links, JSON, images     |
| `MAX_BROWSER_WORKERS`            | `1`                      | Detail-scrape threads (host = 1) |
| `RETRY_LIMIT`                    | `3`                      | Per-URL retries                  |
| `INTER_REQUEST_DELAY`            | `1.5`                    | Seconds between detail requests  |
| `BROWSER_MODE`                   | `xvfb`                   | `xvfb` / `gui` / `headless`      |
| `GCS_BUCKET`                     | `bronze-car-recsys`      | Destination bucket               |
| `GCS_PREFIX`                     | `raw_data`               | JSON prefix in bucket            |
| `GOOGLE_APPLICATION_CREDENTIALS` | —                        | Path to service-account JSON     |
| `CHROME_BINARY`                  | `/usr/bin/google-chrome` | Override if using Chromium       |

## Notes vs. the original notebook

- Removed Colab-only code (`google.colab.auth`, `nest_asyncio`).
- `print()` replaced with `logging`.
- One page per run; cadence handled by the Temporal schedule.
- Resumable: existing `page_N.txt` and `<idx>.json` files are skipped, so a
  retried run never redoes finished work.
