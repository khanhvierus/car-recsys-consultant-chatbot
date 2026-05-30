# Temporal orchestration — car-recsys data platform

Self-hosted Temporal replaces the three old Airflow DAGs. There are **two
workers on two task queues**:

| Worker | Runs in | Task queue | Serves |
|---|---|---|---|
| **pipeline-worker** | Docker (compose) | `car-pipeline-tq` | Transform, ML |
| **crawler worker** | the host (`run_worker.sh`) | `car-crawler-tq` | WeeklyCrawl |

The crawler can't run in Docker — cars.com's Turnstile needs real Chrome via
Xvfb (verified). Everything else (load_bronze, dbt, similarity, embeddings) has
no browser dependency, so it runs in the container and comes up with
`docker compose up`.

## Workflows

| Workflow | Activities | Replaces |
|---|---|---|
| `WeeklyCrawl` | crawl_links → scrape_details → upload_gcs | `car_crawler_weekly` |
| `Transform`   | load_bronze → dbt_build → refresh_matviews | `car_recsys_transform` |
| `ML`          | compute_item_similarity ∥ embed_vehicles | `car_recsys_ml` |

Pipeline logic lives in [pipeline/](pipeline/) as plain functions; activities in
[activities.py](activities.py) wrap them (crawler imports are lazy so the
pipeline worker doesn't need seleniumbase); workflows in
[workflows.py](workflows.py) add retries/timeouts.

## Architecture

```
Docker (car-recsys-system/docker-compose.yml)  ← `docker compose up`
  ├── temporal          gRPC localhost:7233   (server, history, schedules)
  ├── temporal-ui       http localhost:8233
  ├── postgres          5432  (warehouse + temporal's own DBs)
  ├── qdrant            6333  (vehicle vectors)
  ├── redis             6379
  ├── backend           8000  (FastAPI)
  └── pipeline-worker   ──► car-pipeline-tq: Transform + ML
        ▲
        │ both connect to temporal:7233 (no TLS)
        ▼
Host (crawler/.venv, only when crawling)  ← `./run_worker.sh`
  └── temporal_app.worker  ──► car-crawler-tq: WeeklyCrawl → Chrome via Xvfb
```

## Setup

1. **Start the whole backend stack (incl. pipeline-worker):**
   ```bash
   cd car-recsys-system
   docker compose up -d
   ```
   `temporalio/auto-setup` creates Temporal's databases in the shared Postgres
   on first boot. UI: <http://localhost:8233>. Frontend stays on the host
   (`npm run dev`); bytebase is opt-in (`--profile tools`).

   Secrets come from `car-recsys-system/.env` (OPENAI_API_KEY, GCS_*). GCS ADC
   at `~/.config/gcloud/application_default_credentials.json` is mounted into
   the pipeline-worker for `load_bronze`.

2. **(Crawler only) configure + run the host worker:**
   ```bash
   cd crawler
   cp temporal_app/.env.example temporal_app/.env   # TEMPORAL_ADDRESS=localhost:7233
   ./run_worker.sh                                  # installs deps, then connects
   ```
   Look for: `Connected. Crawler worker on task queue car-crawler-tq`.

## Trigger / schedule

Run scripts from the host venv (`cd crawler`):

```bash
# Transform / ML — served by the Dockerized pipeline-worker (always up):
.venv/bin/python -m temporal_app.scripts.trigger_once transform
.venv/bin/python -m temporal_app.scripts.trigger_once ml

# Crawl — needs the host worker running (./run_worker.sh):
.venv/bin/python -m temporal_app.scripts.trigger_once crawl

# Register all weekly cron schedules (Mon 02:00 crawl / 06:00 transform / 08:00 ml):
.venv/bin/python -m temporal_app.scripts.create_schedule
```

Watch progress live in the UI → *Workflows* / *Schedules*. Pause or delete a
schedule from *Schedules → … → Pause/Delete*. (Crawl schedules only fire when
the host worker is online.)

## Notes

- **Two task queues** — `car-pipeline-tq` (Docker) and `car-crawler-tq` (host).
  A workflow's activities run on the queue the workflow was started on, so the
  right worker always picks them up.
- **No TLS / no certs** — local self-host uses a plaintext gRPC connection.
- **Single Chrome** — the host worker caps activities at 1 concurrent so two
  browsers never launch at once.
- **Crawler must run on the host, not in Docker** — Xvfb-in-container can't solve
  cars.com's Turnstile (verified).

## Troubleshooting

- **`Failed connecting ... 7233`** — `docker compose ps` the `temporal` service;
  wait for healthy (auto-setup takes ~30 s on first boot).
- **Transform/ML stuck in Running** — `docker compose logs -f pipeline-worker`;
  it must log `Pipeline worker on task queue car-pipeline-tq`.
- **Crawl stuck in Running** — the host worker isn't up. Run `./run_worker.sh`.
- **`scrape_details: all URLs failed`** — cars.com blocking; Temporal retries
  after backoff. Debug standalone: `./run_local.sh crawl-links --page 1`.
- **dbt_build fails** — check the activity log in the UI; the last 4000 chars of
  dbt stderr are captured there.
