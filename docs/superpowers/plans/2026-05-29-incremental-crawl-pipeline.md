# Incremental Crawl Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the weekly Temporal pipeline land crawl output in a separate `incremental_raw` bucket partitioned by crawl date, transform only that day's data via dbt (VIN-deduped upsert + day-partitioned price history), and re-embed only changed vehicles.

**Architecture:** Crawler writes to `gs://incremental_raw/dt=YYYY-MM-DD/`. `load_bronze(dt)` ingests only that prefix into `bronze.raw_listings` (now carrying `crawl_date` + `source` + `run_id`). dbt parses/dedups by VIN into `gold.vehicles` (merge) and appends change-events to the day-range-partitioned `gold.vehicle_price_history`. A partition-ensure step runs before dbt. ML embeds only VINs with `last_updated_date = dt`.

**Tech Stack:** Python 3.11, Temporal (temporalio), SeleniumBase, google-cloud-storage, psycopg2, dbt-postgres, PostgreSQL 15, pytest.

**Reference spec:** `docs/superpowers/specs/2026-05-29-incremental-crawl-pipeline-design.md`

---

## File Structure

**Crawler / GCS layer:**
- `crawler/crawler/config.py` (modify) — add `CRAWL_DATE`, default bucket `incremental_raw`, date-partition prefix.
- `crawler/crawler/gcs_uploader.py` (modify) — `dt=<date>/<page>/` object keys.
- `crawler/tests/test_gcs_paths.py` (create) — unit-test object-key construction.

**Bronze loader:**
- `crawler/temporal_app/pipeline/bronze.py` (modify) — `crawl_date`/`source`/`run_id`, day-prefix listing, `crawl_date` lifted from path.
- `crawler/tests/test_bronze_paths.py` (create) — unit-test prefix + page/date parsing.

**Temporal activities/workflows:**
- `crawler/temporal_app/activities.py` (modify) — thread `crawl_date`, add `ensure_partition_activity`.
- `crawler/temporal_app/workflows.py` (modify) — pass `crawl_date`; insert `ensure_partition` before `dbt_build`.

**Schema:**
- `car-recsys-system/database/init/02-create-schema.sql` (modify) — bronze cols, `vehicle_price_history` parent + `ensure_price_history_partition` function.

**dbt:**
- `car-recsys-system/dbt/models/staging/stg_listings.sql` (modify) — expose `crawl_date`, `source`.
- `car-recsys-system/dbt/models/staging/stg_raw_latest.sql` (modify) — carry `crawl_date`, `source`, filter by run date.
- `car-recsys-system/dbt/models/silver/fct_listing.sql` (modify) — carry `crawl_date`, `source`, `first_seen`/`last_updated`.
- `car-recsys-system/dbt/models/gold/vehicles.sql` (modify) — merge strategy, new columns.
- `car-recsys-system/dbt/models/gold/vehicle_price_history.sql` (create) — incremental append, change-only.
- `car-recsys-system/dbt/models/gold/_gold__models.yml` (modify) — document/test new model + columns.

**ML:**
- `crawler/temporal_app/pipeline/embeddings.py` (modify) — `since_date` watermark on `last_updated_date`.
- `crawler/temporal_app/activities.py` (modify) — `embed_vehicles_activity` passes `crawl_date`.

**Docs/config:**
- `crawler/temporal_app/.env.example` + `car-recsys-system/.env.example` (modify) — `GCS_BUCKET=incremental_raw`.

---

## Task 1: Crawler GCS date-partitioned paths

**Files:**
- Modify: `crawler/crawler/config.py`
- Modify: `crawler/crawler/gcs_uploader.py`
- Test: `crawler/tests/test_gcs_paths.py`

- [ ] **Step 1: Write the failing test**

Create `crawler/tests/test_gcs_paths.py`:

```python
from crawler.gcs_uploader import _json_blob_name, _image_blob_name


def test_json_blob_name_is_date_partitioned():
    assert (
        _json_blob_name("2026-05-29", page=1, filename="3.json")
        == "dt=2026-05-29/1/3.json"
    )


def test_image_blob_name_is_date_partitioned():
    assert (
        _image_blob_name("2026-05-29", relative="ABC123/0.jpg")
        == "dt=2026-05-29/images/ABC123/0.jpg"
    )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd crawler && PYTHONPATH=. .venv/bin/python -m pytest tests/test_gcs_paths.py -v`
Expected: FAIL with `ImportError: cannot import name '_json_blob_name'`.

- [ ] **Step 3: Add config knobs**

In `crawler/crawler/config.py`, change the GCS section (the `GCS_BUCKET`/`GCS_PREFIX` block near line 51) to:

```python
# ── GCS ──────────────────────────────────────────────────────────────────────
# Weekly incremental crawls write to a SEPARATE bucket, date-partitioned, so a
# new run never overwrites a prior one and never touches the initial-load bucket.
import datetime as _dt

GCS_BUCKET: str = os.getenv("GCS_BUCKET", "incremental_raw")
GCS_IMAGE_PREFIX: str = os.getenv("GCS_IMAGE_PREFIX", "images")
# Crawl date = the dt= partition. Defaults to today (UTC).
CRAWL_DATE: str = os.getenv("CRAWL_DATE", _dt.datetime.utcnow().strftime("%Y-%m-%d"))
# Path to GCP service account JSON (or use ADC).
GOOGLE_APPLICATION_CREDENTIALS: str | None = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
```

(Delete the old `GCS_PREFIX` line — date partitioning replaces it.)

- [ ] **Step 4: Rewrite gcs_uploader for date paths**

Replace `crawler/crawler/gcs_uploader.py` entirely with:

```python
"""Upload scraped JSON and downloaded images to GCS, date-partitioned.

Object layout (incremental):
    dt=<crawl_date>/<page>/<file>.json
    dt=<crawl_date>/images/<relative-path>
Each weekly run uses a fresh dt= prefix, so nothing is ever overwritten.
"""
from __future__ import annotations

from pathlib import Path

from crawler.config import (
    CRAWL_DATE,
    GCS_BUCKET,
    GCS_IMAGE_PREFIX,
    IMG_BASE_DIR,
    RAW_DATA_DIR,
)
from crawler.logging_setup import get_logger

log = get_logger(__name__)


def _json_blob_name(crawl_date: str, page: int, filename: str) -> str:
    return f"dt={crawl_date}/{page}/{filename}"


def _image_blob_name(crawl_date: str, relative: str) -> str:
    return f"dt={crawl_date}/{GCS_IMAGE_PREFIX}/{relative}"


def upload_to_gcs(
    from_page: int,
    to_page: int,
    crawl_date: str = CRAWL_DATE,
    raw_data_dir: Path = RAW_DATA_DIR,
    img_base_dir: Path = IMG_BASE_DIR,
    bucket_name: str = GCS_BUCKET,
) -> dict:
    """Upload JSON + images for [from_page, to_page] under dt=<crawl_date>/.

    Returns counts: {'json_ok','json_fail','img_ok','img_fail'}.
    """
    from google.cloud import storage  # type: ignore

    raw_data_dir = Path(raw_data_dir)
    img_base_dir = Path(img_base_dir)
    client = storage.Client()
    bucket = client.bucket(bucket_name)

    json_ok = json_fail = 0
    for page in range(from_page, to_page + 1):
        page_dir = raw_data_dir / str(page)
        if not page_dir.is_dir():
            log.info("[Skip] %s not found", page_dir)
            continue
        for f in sorted(page_dir.glob("*.json")):
            blob_name = _json_blob_name(crawl_date, page, f.name)
            try:
                bucket.blob(blob_name).upload_from_filename(
                    str(f), content_type="application/json"
                )
                json_ok += 1
            except Exception as e:
                log.warning("[!] %s: %s", blob_name, e)
                json_fail += 1
    log.info("JSON: %s uploaded, %s failed (dt=%s)", json_ok, json_fail, crawl_date)

    img_ok = img_fail = 0
    if not img_base_dir.exists():
        log.info("[Skip] No %s folder found", img_base_dir)
    else:
        for img_file in img_base_dir.rglob("*.jpg"):
            relative = img_file.relative_to(img_base_dir).as_posix()
            blob_name = _image_blob_name(crawl_date, relative)
            try:
                bucket.blob(blob_name).upload_from_filename(
                    str(img_file), content_type="image/jpeg"
                )
                img_ok += 1
            except Exception as e:
                log.warning("[!] %s: %s", blob_name, e)
                img_fail += 1
        log.info("Images: %s uploaded, %s failed", img_ok, img_fail)

    log.info("GCS upload complete")
    return {"json_ok": json_ok, "json_fail": json_fail,
            "img_ok": img_ok, "img_fail": img_fail}
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd crawler && PYTHONPATH=. .venv/bin/python -m pytest tests/test_gcs_paths.py -v`
Expected: PASS (2 passed).

- [ ] **Step 6: Commit**

```bash
git add crawler/crawler/config.py crawler/crawler/gcs_uploader.py crawler/tests/test_gcs_paths.py
git commit -m "feat(crawler): date-partitioned GCS layout in incremental_raw bucket"
```

---

## Task 2: Bronze loader reads one day's prefix + lifts crawl_date/source

**Files:**
- Modify: `crawler/temporal_app/pipeline/bronze.py`
- Test: `crawler/tests/test_bronze_paths.py`

- [ ] **Step 1: Write the failing test**

Create `crawler/tests/test_bronze_paths.py`:

```python
from temporal_app.pipeline.bronze import (
    BronzeLoaderConfig,
    _date_from_path,
    _page_from_path,
    _prefixes_for,
)


def test_prefixes_for_a_single_day():
    cfg = BronzeLoaderConfig(bucket="incremental_raw", crawl_date="2026-05-29")
    assert _prefixes_for(cfg) == ["dt=2026-05-29/"]


def test_page_parsed_from_dt_path():
    assert _page_from_path("dt=2026-05-29/1/3.json") == 1


def test_date_parsed_from_dt_path():
    assert _date_from_path("dt=2026-05-29/1/3.json") == "2026-05-29"


def test_date_none_when_absent():
    assert _date_from_path("raw_data/1/3.json") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd crawler && PYTHONPATH=. .venv/bin/python -m pytest tests/test_bronze_paths.py -v`
Expected: FAIL with `ImportError` for `_date_from_path` / `_prefixes_for`.

- [ ] **Step 3: Modify bronze.py**

In `crawler/temporal_app/pipeline/bronze.py`:

Replace the regex line near the top (`_PAGE_RE = re.compile(r"/raw_data/(\d+)/")`) with:

```python
_PAGE_RE = re.compile(r"/(?:dt=\d{4}-\d{2}-\d{2}|raw_data)/(\d+)/")
_DATE_RE = re.compile(r"dt=(\d{4}-\d{2}-\d{2})/")
```

Replace the `BronzeLoaderConfig` dataclass with:

```python
@dataclass(slots=True)
class BronzeLoaderConfig:
    bucket: str = "incremental_raw"
    crawl_date: str = ""                # "" = scan whole bucket (full backfill)
    warehouse_dsn: str = ""             # postgresql://user:pass@host:5432/db
    source: str = "incremental"
    gcp_project: Optional[str] = None
    download_workers: int = 16
    batch_size: int = 500
    extra: dict[str, Any] = field(default_factory=dict)
```

Add this helper after `_page_from_path`:

```python
def _date_from_path(blob_name: str) -> Optional[str]:
    m = _DATE_RE.search("/" + blob_name)
    return m.group(1) if m else None


def _prefixes_for(config: BronzeLoaderConfig) -> list[str]:
    """The GCS prefixes to scan. A crawl_date restricts to one day's slice."""
    if config.crawl_date:
        return [f"dt={config.crawl_date}/"]
    return [""]   # whole bucket
```

In `_process_blob`, after computing `vin, slug, crawled_at = _lift_keys(payload)`, add `crawl_date` to the returned dict and rename `dag_run_id`→`run_id`. Change the return dict to:

```python
    return {
        "file_hash": file_hash,
        "gcs_path": f"gs://{blob.bucket.name}/{blob.name}",
        "page_number": _page_from_path(blob.name),
        "crawl_date": _date_from_path(blob.name),
        "vin": vin,
        "car_model_slug": slug,
        "payload": json.dumps(payload),
        "crawled_at": crawled_at,
    }
```

Replace the body of `load_bronze` that builds `prefixes` and `blobs` with:

```python
    client = storage.Client(project=config.gcp_project)
    bucket = client.bucket(config.bucket)

    blobs = []
    for prefix in _prefixes_for(config):
        blobs.extend(
            b for b in client.list_blobs(bucket, prefix=prefix)
            if b.name.endswith(".json")
        )
    log.info("found %d JSON blobs (crawl_date=%s)", len(blobs), config.crawl_date or "ALL")
    if not blobs:
        return {"scanned": 0, "parsed": 0, "inserted": 0}
```

In the parallel-parse loop, replace `row["dag_run_id"] = dag_run_id` with `row["run_id"] = run_id` and rename the `load_bronze` parameter `dag_run_id` → `run_id` and add `source`:

```python
def load_bronze(
    config: BronzeLoaderConfig,
    run_id: str = "",
) -> dict[str, int]:
```

```python
        for row in pool.map(_process_blob, blobs):
            if row is not None:
                row["run_id"] = run_id
                row["source"] = config.source
                rows.append(row)
```

Replace the `_insert` SQL + template with the new columns:

```python
    sql = """
        INSERT INTO bronze.raw_listings
            (file_hash, gcs_path, page_number, crawl_date, vin,
             car_model_slug, payload, crawled_at, source, run_id)
        VALUES %s
        ON CONFLICT (file_hash) DO NOTHING
    """
    template = ("(%(file_hash)s, %(gcs_path)s, %(page_number)s, %(crawl_date)s::date, "
                "%(vin)s, %(car_model_slug)s, %(payload)s::jsonb, "
                "%(crawled_at)s::timestamptz, %(source)s, %(run_id)s)")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd crawler && PYTHONPATH=. .venv/bin/python -m pytest tests/test_bronze_paths.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add crawler/temporal_app/pipeline/bronze.py crawler/tests/test_bronze_paths.py
git commit -m "feat(bronze): load one crawl_date slice, lift crawl_date/source/run_id"
```

---

## Task 3: Bronze schema columns + price-history partitioned table

**Files:**
- Modify: `car-recsys-system/database/init/02-create-schema.sql`
- Test: `car-recsys-system/database/tests/test_schema.sql` (create — plain SQL asserts run via psql)

- [ ] **Step 1: Write the failing test**

Create `car-recsys-system/database/tests/test_schema.sql`:

```sql
-- Fails (raises) if expected columns / tables are missing.
DO $$
BEGIN
  -- bronze new columns
  PERFORM 1 FROM information_schema.columns
    WHERE table_schema='bronze' AND table_name='raw_listings' AND column_name='crawl_date';
  IF NOT FOUND THEN RAISE EXCEPTION 'bronze.raw_listings.crawl_date missing'; END IF;

  PERFORM 1 FROM information_schema.columns
    WHERE table_schema='bronze' AND table_name='raw_listings' AND column_name='source';
  IF NOT FOUND THEN RAISE EXCEPTION 'bronze.raw_listings.source missing'; END IF;

  PERFORM 1 FROM information_schema.columns
    WHERE table_schema='bronze' AND table_name='raw_listings' AND column_name='run_id';
  IF NOT FOUND THEN RAISE EXCEPTION 'bronze.raw_listings.run_id missing'; END IF;

  -- price history partitioned parent
  PERFORM 1 FROM pg_partitioned_table pt
    JOIN pg_class c ON c.oid = pt.partrelid
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname='gold' AND c.relname='vehicle_price_history';
  IF NOT FOUND THEN RAISE EXCEPTION 'gold.vehicle_price_history not partitioned'; END IF;

  -- ensure-partition function
  PERFORM 1 FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
    WHERE n.nspname='gold' AND p.proname='ensure_price_history_partition';
  IF NOT FOUND THEN RAISE EXCEPTION 'gold.ensure_price_history_partition missing'; END IF;

  RAISE NOTICE 'schema test passed';
END $$;
```

- [ ] **Step 2: Run test to verify it fails**

Run (DB must be up — `docker compose up -d postgres`):
```bash
docker compose -f car-recsys-system/docker-compose.yml exec -T postgres \
  psql -U admin -d car_recsys -v ON_ERROR_STOP=1 \
  -f - < car-recsys-system/database/tests/test_schema.sql
```
Expected: ERROR `bronze.raw_listings.crawl_date missing` (columns not added yet).

- [ ] **Step 3: Modify the init SQL — bronze columns**

In `car-recsys-system/database/init/02-create-schema.sql`, replace the `bronze.raw_listings` CREATE TABLE (the block with `dag_run_id`) with:

```sql
CREATE TABLE IF NOT EXISTS bronze.raw_listings (
    raw_id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    file_hash       TEXT NOT NULL,                 -- sha256 of file bytes — idempotency key
    gcs_path        TEXT NOT NULL,                 -- gs://incremental_raw/dt=YYYY-MM-DD/<page>/<f>.json
    page_number     INTEGER,                       -- parsed from the GCS path
    crawl_date      DATE,                          -- dt= partition lifted from the path
    vin             TEXT,                          -- payload->post->basic_desc->VIN, lifted out
    car_model_slug  TEXT,                          -- payload->car->car_model, lifted out
    payload         JSONB NOT NULL,                -- the entire crawled file, untouched
    crawled_at      TIMESTAMPTZ,                   -- payload->>'datetime'
    ingested_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    source          TEXT NOT NULL DEFAULT 'incremental',  -- 'initial' | 'incremental'
    run_id          TEXT,                          -- Temporal workflow run that loaded this row
    CONSTRAINT uq_raw_listings_file_hash UNIQUE (file_hash)
);

CREATE INDEX IF NOT EXISTS idx_raw_listings_vin        ON bronze.raw_listings (vin);
CREATE INDEX IF NOT EXISTS idx_raw_listings_model      ON bronze.raw_listings (car_model_slug);
CREATE INDEX IF NOT EXISTS idx_raw_listings_ingested   ON bronze.raw_listings (ingested_at);
CREATE INDEX IF NOT EXISTS idx_raw_listings_crawl_date ON bronze.raw_listings (crawl_date);
CREATE INDEX IF NOT EXISTS idx_raw_listings_payload    ON bronze.raw_listings USING GIN (payload jsonb_path_ops);

COMMENT ON TABLE bronze.raw_listings IS 'Raw crawled cars.com JSON, one row per file. Append-only, idempotent via file_hash.';
```

- [ ] **Step 4: Add price-history parent + ensure-partition function**

Append to the GOLD section of `02-create-schema.sql` (after the gold user-domain tables):

```sql
-- ============================================================================
-- GOLD price/mileage history — change-event log, partitioned by crawl_date.
-- dbt's gold.vehicle_price_history model APPENDS into this parent; Postgres
-- routes each row to the monthly partition. Partitions are created on demand by
-- gold.ensure_price_history_partition(), called by the Temporal ensure_partition
-- activity before dbt runs.
-- ============================================================================
CREATE TABLE IF NOT EXISTS gold.vehicle_price_history (
    vin           TEXT        NOT NULL,
    price         NUMERIC,
    mileage       INTEGER,
    status        TEXT,
    crawl_date    DATE        NOT NULL,
    inserted_at   TIMESTAMPTZ NOT NULL DEFAULT now()
) PARTITION BY RANGE (crawl_date);

CREATE INDEX IF NOT EXISTS idx_price_history_vin_date
    ON gold.vehicle_price_history (vin, crawl_date);

-- Idempotently create the monthly partition covering `d`.
CREATE OR REPLACE FUNCTION gold.ensure_price_history_partition(d DATE)
RETURNS void LANGUAGE plpgsql AS $$
DECLARE
    start_m DATE := date_trunc('month', d)::date;
    end_m   DATE := (date_trunc('month', d) + interval '1 month')::date;
    part    TEXT := format('vehicle_price_history_%s', to_char(start_m, 'YYYY_MM'));
BEGIN
    EXECUTE format(
        'CREATE TABLE IF NOT EXISTS gold.%I PARTITION OF gold.vehicle_price_history '
        'FOR VALUES FROM (%L) TO (%L)', part, start_m, end_m
    );
END $$;
```

- [ ] **Step 5: Recreate the DB and run the schema test**

```bash
docker compose -f car-recsys-system/docker-compose.yml down -v
docker compose -f car-recsys-system/docker-compose.yml up -d postgres
sleep 20
docker compose -f car-recsys-system/docker-compose.yml exec -T postgres \
  psql -U admin -d car_recsys -v ON_ERROR_STOP=1 \
  -f - < car-recsys-system/database/tests/test_schema.sql
```
Expected: `NOTICE: schema test passed`.

- [ ] **Step 6: Commit**

```bash
git add car-recsys-system/database/init/02-create-schema.sql car-recsys-system/database/tests/test_schema.sql
git commit -m "feat(schema): bronze crawl_date/source/run_id + partitioned price history"
```

---

## Task 4: dbt staging carries crawl_date + source

**Files:**
- Modify: `car-recsys-system/dbt/models/staging/stg_raw_latest.sql`
- Modify: `car-recsys-system/dbt/models/staging/stg_listings.sql`

- [ ] **Step 1: Add crawl_date/source to stg_raw_latest**

In `car-recsys-system/dbt/models/staging/stg_raw_latest.sql`, add `crawl_date` and `source` to both the `ranked` CTE select and the final select. The `ranked` CTE select becomes:

```sql
    select
        vin,
        car_model_slug,
        payload,
        crawled_at,
        crawl_date,
        source,
        gcs_path,
        row_number() over (
            partition by vin
            order by ingested_at desc
        ) as rn
    from {{ source('bronze', 'raw_listings') }}
    where vin is not null
      and vin <> ''
```

and the final select becomes:

```sql
select
    vin,
    car_model_slug,
    payload,
    crawled_at,
    crawl_date,
    source,
    gcs_path
from ranked
where rn = 1
```

- [ ] **Step 2: Surface crawl_date/source in stg_listings**

In `car-recsys-system/dbt/models/staging/stg_listings.sql`, add to the final select (just before `crawled_at,`):

```sql
    crawl_date,
    source,
```

- [ ] **Step 3: Verify dbt parses**

Run (dbt lives in the pipeline image; mount the live dbt dir to parse it):
```bash
docker run --rm -v "$PWD/car-recsys-system/dbt:/app/dbt" \
  -e DBT_PG_HOST=x -e DBT_PG_USER=admin -e DBT_PG_PASSWORD=admin123 -e DBT_PG_DBNAME=car_recsys \
  car-pipeline-worker:latest dbt parse --profiles-dir /app/dbt --project-dir /app/dbt
```
Expected: `Wrote manifest`, no compile errors. (Run from repo root. Build the image first if needed: Task 10 Step 3.)

- [ ] **Step 4: Commit**

```bash
git add car-recsys-system/dbt/models/staging/stg_raw_latest.sql car-recsys-system/dbt/models/staging/stg_listings.sql
git commit -m "feat(dbt): carry crawl_date + source through staging"
```

---

## Task 5: fct_listing carries crawl_date/source + first_seen/last_updated

**Files:**
- Modify: `car-recsys-system/dbt/models/silver/fct_listing.sql`

- [ ] **Step 1: Add columns to fct_listing select**

In `car-recsys-system/dbt/models/silver/fct_listing.sql`, add to the select list (after `mileage,` or near the other scalar columns):

```sql
    crawl_date,
    source,
    crawl_date as last_updated_date,
```

`first_seen_date` is resolved at the gold layer (merge-preserving), so fct_listing only needs `crawl_date`/`source`/`last_updated_date`. The `delete+insert` on `vin` already keeps fct_listing as the current row per VIN.

- [ ] **Step 2: Verify dbt parses**

Run (dbt lives in the pipeline image; mount the live dbt dir to parse it):
```bash
docker run --rm -v "$PWD/car-recsys-system/dbt:/app/dbt" \
  -e DBT_PG_HOST=x -e DBT_PG_USER=admin -e DBT_PG_PASSWORD=admin123 -e DBT_PG_DBNAME=car_recsys \
  car-pipeline-worker:latest dbt parse --profiles-dir /app/dbt --project-dir /app/dbt
```
Expected: `Wrote manifest`, no compile errors. (Run from repo root.)

- [ ] **Step 3: Commit**

```bash
git add car-recsys-system/dbt/models/silver/fct_listing.sql
git commit -m "feat(dbt): fct_listing carries crawl_date/source/last_updated_date"
```

---

## Task 6: gold.vehicles → merge with source + first_seen/last_updated

**Files:**
- Modify: `car-recsys-system/dbt/models/gold/vehicles.sql`
- Modify: `car-recsys-system/dbt/models/gold/_gold__models.yml`

- [ ] **Step 1: Switch gold.vehicles to incremental merge**

In `car-recsys-system/dbt/models/gold/vehicles.sql`, add a config block at the very top (before the `with img_agg as (` line), and select the new columns. Add at top:

```sql
{{ config(
    materialized='incremental',
    unique_key='vin',
    incremental_strategy='merge',
    merge_exclude_columns=['first_seen_date']
) }}
```

In the final `select`, add these columns (alongside `fl.crawled_at`):

```sql
    fl.source,
    fl.last_updated_date,
    coalesce(fl.crawl_date, current_date) as first_seen_date,
```

Add an incremental guard at the end of the model (after the joins) so only the
current day's listings are merged on incremental runs:

```sql
{% if is_incremental() %}
where fl.last_updated_date >= (select coalesce(max(last_updated_date), '1900-01-01') from {{ this }})
{% endif %}
```

`merge_exclude_columns=['first_seen_date']` keeps the original first-seen value
on update (only inserts set it).

- [ ] **Step 2: Document the new columns**

In `car-recsys-system/dbt/models/gold/_gold__models.yml`, under the `vehicles` model's `columns:`, add:

```yaml
      - name: source
        description: "'initial' (Colab bulk load) or 'incremental' (weekly crawl)."
      - name: first_seen_date
        description: First crawl_date this VIN was seen (preserved on merge).
      - name: last_updated_date
        description: Most recent crawl_date this VIN was (re)crawled.
```

- [ ] **Step 3: Verify dbt parses**

Run (dbt lives in the pipeline image; mount the live dbt dir to parse it):
```bash
docker run --rm -v "$PWD/car-recsys-system/dbt:/app/dbt" \
  -e DBT_PG_HOST=x -e DBT_PG_USER=admin -e DBT_PG_PASSWORD=admin123 -e DBT_PG_DBNAME=car_recsys \
  car-pipeline-worker:latest dbt parse --profiles-dir /app/dbt --project-dir /app/dbt
```
Expected: `Wrote manifest`, no compile errors. (Run from repo root.)

- [ ] **Step 4: Commit**

```bash
git add car-recsys-system/dbt/models/gold/vehicles.sql car-recsys-system/dbt/models/gold/_gold__models.yml
git commit -m "feat(dbt): gold.vehicles merge-by-VIN with source + first/last seen"
```

---

## Task 7: gold.vehicle_price_history change-event model

**Files:**
- Create: `car-recsys-system/dbt/models/gold/vehicle_price_history.sql`
- Modify: `car-recsys-system/dbt/models/gold/_gold__models.yml`

- [ ] **Step 1: Create the model**

Create `car-recsys-system/dbt/models/gold/vehicle_price_history.sql`:

```sql
/*
  Change-event log of price / mileage / availability per VIN, appended to the
  partitioned parent gold.vehicle_price_history (created in init SQL). A row is
  written ONLY when (price, mileage, status) differs from the VIN's latest
  existing history row. Append-only incremental; never updates.
*/
{{ config(
    materialized='incremental',
    incremental_strategy='append'
) }}

with current_listings as (
    select
        vin,
        price,
        mileage,
        new_used as status,
        crawl_date
    from {{ ref('fct_listing') }}
    {% if is_incremental() %}
    where crawl_date >= (select coalesce(max(crawl_date), '1900-01-01') from {{ this }})
    {% endif %}
),

latest_history as (
    select distinct on (vin) vin, price, mileage, status
    from {{ this }}
    order by vin, crawl_date desc
)

select
    c.vin,
    c.price,
    c.mileage,
    c.status,
    c.crawl_date,
    now() as inserted_at
from current_listings c
left join latest_history h on c.vin = h.vin
where h.vin is null   -- first time we see this VIN
   or c.price is distinct from h.price
   or c.mileage is distinct from h.mileage
   or c.status is distinct from h.status
```

Note: on the very first run `{{ this }}` does not exist yet, so dbt skips the
`is_incremental()` branch and `latest_history` is empty — every current listing
gets one history row. Subsequent runs only append changes.

- [ ] **Step 2: Document + test the model**

In `car-recsys-system/dbt/models/gold/_gold__models.yml`, add a new model entry:

```yaml
  - name: vehicle_price_history
    description: >
      Append-only change-event log of price/mileage/status per VIN, partitioned
      by crawl_date in Postgres. One row per detected change.
    columns:
      - name: vin
        tests: [not_null]
      - name: crawl_date
        tests: [not_null]
```

- [ ] **Step 3: Verify dbt parses**

Run:
```bash
cd car-recsys-system/dbt && DBT_PG_HOST=localhost DBT_PG_PORT=5432 \
  DBT_PG_USER=admin DBT_PG_PASSWORD=admin123 DBT_PG_DBNAME=car_recsys \
  ../../crawler/.venv/bin/dbt parse --profiles-dir . --project-dir .
```
Expected: no errors; `vehicle_price_history` appears in the manifest.

- [ ] **Step 4: Commit**

```bash
git add car-recsys-system/dbt/models/gold/vehicle_price_history.sql car-recsys-system/dbt/models/gold/_gold__models.yml
git commit -m "feat(dbt): vehicle_price_history change-event model"
```

---

## Task 8: ensure_partition activity + Transform/Crawl workflow wiring

**Files:**
- Modify: `crawler/temporal_app/activities.py`
- Modify: `crawler/temporal_app/workflows.py`

- [ ] **Step 1: Add the ensure_partition activity**

In `crawler/temporal_app/activities.py`, add a new dataclass near the other pipeline results and a new activity. Add the activity after `load_bronze_activity`:

```python
@activity.defn(name="ensure_partition")
def ensure_partition_activity(crawl_date: str) -> None:
    """Ensure the price-history monthly partition for crawl_date exists."""
    import psycopg2

    dsn = _require_env("WAREHOUSE_DSN")
    conn = psycopg2.connect(dsn)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT gold.ensure_price_history_partition(%s::date)",
                (crawl_date,),
            )
        conn.commit()
    finally:
        conn.close()
    activity.logger.info("ensured price-history partition for %s", crawl_date)
```

Modify `load_bronze_activity` to accept and use `crawl_date`:

```python
@activity.defn(name="load_bronze")
def load_bronze_activity(crawl_date: str) -> LoadBronzeResult:
    """GCS dt=<crawl_date> slice → bronze.raw_listings (append-only, idempotent)."""
    from temporal_app.pipeline import BronzeLoaderConfig, load_bronze

    cfg = BronzeLoaderConfig(
        bucket=os.environ.get("GCS_BUCKET", "incremental_raw"),
        crawl_date=crawl_date,
        warehouse_dsn=_require_env("WAREHOUSE_DSN"),
        gcp_project=os.environ.get("GCP_PROJECT_ID"),
    )
    result = load_bronze(cfg, run_id=activity.info().workflow_run_id)
    activity.logger.info("load_bronze(%s): %s", crawl_date, result)
    return LoadBronzeResult(**result)
```

Modify the three crawl activities to accept `crawl_date` where they need it.
`upload_gcs_activity` becomes:

```python
@activity.defn(name="upload_gcs")
def upload_gcs_activity(inp: CrawlInput) -> UploadResult:
    """Stage 3: push JSON + images to gs://incremental_raw/dt=<crawl_date>/."""
    from crawler.gcs_uploader import upload_to_gcs

    activity.logger.info("upload_gcs page=%s dt=%s", inp.page, inp.crawl_date)
    result = upload_to_gcs(
        from_page=inp.page, to_page=inp.page, crawl_date=inp.crawl_date
    )
    return UploadResult(
        page=inp.page,
        json_uploaded=result.get("json_ok", 0),
        images_uploaded=result.get("img_ok", 0),
    )
```

Extend the `CrawlInput` dataclass to carry the date:

```python
@dataclass
class CrawlInput:
    page: int
    crawl_date: str = ""
```

The crawler reads `CRAWL_DATE` from env; set it from the workflow (Step 3) so the
uploaded `dt=` matches what `load_bronze` later reads. In `upload_gcs_activity`,
also export it so `crawler.config.CRAWL_DATE` (already imported at module load)
is overridden — simplest is to pass `crawl_date` explicitly as done above (no env
needed for upload).

- [ ] **Step 2: Wire crawl_date through WeeklyCrawlWorkflow**

In `crawler/temporal_app/workflows.py`, in `WeeklyCrawlWorkflow.run`, derive a
deterministic date from `workflow.now()` and pass it into the activities. Replace
the `act_in = CrawlInput(page=page)` construction with:

```python
        crawl_date = workflow.now().strftime("%Y-%m-%d")
        act_in = CrawlInput(page=page, crawl_date=crawl_date)
```

(`crawl_links` and `scrape_details` ignore `crawl_date`; `upload_gcs` uses it.)

- [ ] **Step 3: Insert ensure_partition into TransformWorkflow**

In `crawler/temporal_app/workflows.py`, change `TransformWorkflow.run` to take a
`crawl_date` and call the activities in order. Replace its body with:

```python
    @workflow.run
    async def run(self, crawl_date: str = "") -> TransformResult:
        dt = crawl_date or workflow.now().strftime("%Y-%m-%d")
        workflow.logger.info("Transform starting dt=%s", dt)

        bronze: LoadBronzeResult = await workflow.execute_activity(
            load_bronze_activity,
            dt,
            start_to_close_timeout=timedelta(minutes=30),
            retry_policy=_DB_RETRY,
        )

        await workflow.execute_activity(
            ensure_partition_activity,
            dt,
            start_to_close_timeout=timedelta(minutes=2),
            retry_policy=_DB_RETRY,
        )

        await workflow.execute_activity(
            dbt_build_activity,
            start_to_close_timeout=timedelta(hours=1),
            retry_policy=RetryPolicy(maximum_attempts=2),
        )

        await workflow.execute_activity(
            refresh_matviews_activity,
            start_to_close_timeout=timedelta(minutes=15),
            retry_policy=_DB_RETRY,
        )

        return TransformResult(
            bronze_inserted=bronze.inserted,
            bronze_scanned=bronze.scanned,
        )
```

Add the import for the new activity to the `with workflow.unsafe.imports_passed_through():` block:

```python
        ensure_partition_activity,
```

- [ ] **Step 4: Register the new activity in both workers**

In `crawler/temporal_app/pipeline_worker.py`, add `ensure_partition_activity` to
the imports from `temporal_app.activities` and to the `activities=[...]` list.

- [ ] **Step 5: Verify imports + workflow sandbox**

Run:
```bash
cd crawler && PYTHONPATH=. .venv/bin/python -c "
import asyncio
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker
from concurrent.futures import ThreadPoolExecutor
from temporal_app.workflows import WeeklyCrawlWorkflow, TransformWorkflow, MLWorkflow
from temporal_app import activities as A
from temporal_app.shared import PIPELINE_TASK_QUEUE
async def main():
    async with await WorkflowEnvironment.start_time_skipping() as env:
        with ThreadPoolExecutor(max_workers=2) as ex:
            Worker(env.client, task_queue=PIPELINE_TASK_QUEUE,
                   workflows=[TransformWorkflow, MLWorkflow],
                   activities=[A.load_bronze_activity, A.ensure_partition_activity,
                               A.dbt_build_activity, A.refresh_matviews_activity,
                               A.compute_item_similarity_activity, A.embed_vehicles_activity],
                   activity_executor=ex)
    print('sandbox OK')
asyncio.run(main())
"
```
Expected: `sandbox OK`.

- [ ] **Step 6: Commit**

```bash
git add crawler/temporal_app/activities.py crawler/temporal_app/workflows.py crawler/temporal_app/pipeline_worker.py
git commit -m "feat(temporal): crawl_date threading + ensure_partition step"
```

---

## Task 9: Incremental embeddings watermark

**Files:**
- Modify: `crawler/temporal_app/pipeline/embeddings.py`
- Modify: `crawler/temporal_app/activities.py`

- [ ] **Step 1: Filter embed_vehicles by last_updated_date**

In `crawler/temporal_app/pipeline/embeddings.py`, the `embed_vehicles` function
already accepts `since` (ISO timestamp on `crawled_at`). Add a `since_date`
parameter that filters on `gold.vehicles.last_updated_date` instead, which is the
correct incremental watermark. Change the signature to add `since_date: Optional[str] = None`
and change the WHERE construction:

```python
    where = ""
    params: dict[str, Any] = {"limit": limit}
    if since_date:
        where = "WHERE last_updated_date >= %(since_date)s"
        params["since_date"] = since_date
    lim = "LIMIT %(limit)s" if limit else ""
```

Then use `params` in `cur.execute(... , params)` and replace `crawled_at` in the
`ORDER BY` with `last_updated_date` (the column now exists on gold.vehicles).

- [ ] **Step 2: Pass crawl_date from the activity**

In `crawler/temporal_app/activities.py`, change `embed_vehicles_activity` to take
the date and forward it:

```python
@activity.defn(name="embed_vehicles")
def embed_vehicles_activity(crawl_date: str = "") -> EmbedResult:
    """gold.vehicles changed on crawl_date → Qdrant (chatbot + VectorRecaller)."""
    from temporal_app.pipeline import embed_vehicles

    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        activity.logger.warning("OPENAI_API_KEY unset — skipping embedding")
        return EmbedResult(embedded=0, skipped=True)

    result = embed_vehicles(
        warehouse_dsn=_require_env("WAREHOUSE_DSN"),
        qdrant_url=os.environ.get("QDRANT_URL", "http://localhost:6333"),
        openai_api_key=api_key,
        collection=os.environ.get("QDRANT_COLLECTION", "car_chatbot_vectors"),
        embedding_model=os.environ.get("OPENAI_EMBEDDING_MODEL", "text-embedding-3-large"),
        embedding_dim=int(os.environ.get("OPENAI_EMBEDDING_DIM", "3072")),
        since_date=crawl_date or None,
    )
    activity.logger.info("embed_vehicles(since_date=%s): %s", crawl_date, result)
    return EmbedResult(embedded=result.get("embedded", 0))
```

- [ ] **Step 3: Pass crawl_date in MLWorkflow**

In `crawler/temporal_app/workflows.py`, `MLWorkflow.run` — change the `embed_task`
activity call to pass a date and accept an optional `crawl_date` arg:

```python
    @workflow.run
    async def run(self, crawl_date: str = "") -> MLResult:
        dt = crawl_date or workflow.now().strftime("%Y-%m-%d")
        workflow.logger.info("ML starting dt=%s", dt)

        sim_task = workflow.execute_activity(
            compute_item_similarity_activity,
            start_to_close_timeout=timedelta(minutes=30),
            retry_policy=_DB_RETRY,
        )
        embed_task = workflow.execute_activity(
            embed_vehicles_activity,
            dt,
            start_to_close_timeout=timedelta(hours=1),
            retry_policy=RetryPolicy(maximum_attempts=3),
        )
        sim, embed = await asyncio.gather(sim_task, embed_task)
        return MLResult(
            similarity_items=sim.items,
            similarity_pairs=sim.pairs,
            embedded=embed.embedded,
        )
```

- [ ] **Step 4: Verify sandbox**

Run:
```bash
cd crawler && PYTHONPATH=. .venv/bin/python -c "
import asyncio
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker
from concurrent.futures import ThreadPoolExecutor
from temporal_app.workflows import MLWorkflow, TransformWorkflow
from temporal_app import activities as A
from temporal_app.shared import PIPELINE_TASK_QUEUE
async def main():
    async with await WorkflowEnvironment.start_time_skipping() as env:
        with ThreadPoolExecutor(max_workers=2) as ex:
            Worker(env.client, task_queue=PIPELINE_TASK_QUEUE,
                   workflows=[TransformWorkflow, MLWorkflow],
                   activities=[A.load_bronze_activity, A.ensure_partition_activity,
                               A.dbt_build_activity, A.refresh_matviews_activity,
                               A.compute_item_similarity_activity, A.embed_vehicles_activity],
                   activity_executor=ex)
    print('sandbox OK')
asyncio.run(main())
"
```
Expected: `sandbox OK`.

- [ ] **Step 5: Commit**

```bash
git add crawler/temporal_app/pipeline/embeddings.py crawler/temporal_app/activities.py crawler/temporal_app/workflows.py
git commit -m "feat(ml): incremental embeddings via last_updated_date watermark"
```

---

## Task 10: Default-bucket config + rebuild pipeline image + docs

**Files:**
- Modify: `crawler/temporal_app/.env.example`
- Modify: `car-recsys-system/.env.example`
- Modify: `car-recsys-system/docker-compose.yml`

- [ ] **Step 1: Update env examples to the new bucket**

In `crawler/temporal_app/.env.example` and `car-recsys-system/.env.example`,
change the GCS bucket line to:

```
GCS_BUCKET=incremental_raw
```

(Remove any `GCS_PREFIX=raw_data` line — date partitioning replaces it.)

- [ ] **Step 2: Point compose pipeline-worker at the new bucket default**

In `car-recsys-system/docker-compose.yml`, in the `pipeline-worker` service
`environment:` list, change:

```yaml
      - GCS_BUCKET=${GCS_BUCKET:-incremental_raw}
```

(Remove the `GCS_PREFIX` env line if present.)

- [ ] **Step 3: Rebuild the pipeline image (gets the bronze.py + embeddings changes)**

```bash
cd /home/duc-nguyen16/car-recsys-consultant-chatbot
docker build -f crawler/Dockerfile.pipeline -t car-pipeline-worker:latest . 2>&1 | tail -3
```
Expected: `naming to docker.io/library/car-pipeline-worker:latest`.

- [ ] **Step 4: Validate compose**

```bash
docker compose -f car-recsys-system/docker-compose.yml config --quiet && echo "COMPOSE VALID"
```
Expected: `COMPOSE VALID`.

- [ ] **Step 5: Commit**

```bash
git add crawler/temporal_app/.env.example car-recsys-system/.env.example car-recsys-system/docker-compose.yml
git commit -m "chore: default to incremental_raw bucket across env + compose"
```

---

## Task 11: End-to-end dbt build verification (DB up)

**Files:** none (verification only)

- [ ] **Step 1: Bring up DB + temporal + pipeline-worker**

```bash
cd car-recsys-system && docker compose up -d postgres temporal pipeline-worker
sleep 25
```

- [ ] **Step 2: Seed two crawl-dates of bronze data by hand**

Insert two minimal rows for the same VIN with a price change, simulating two
weekly crawls (this avoids needing a live crawl for the transform test):

```bash
docker compose exec -T postgres psql -U admin -d car_recsys <<'SQL'
INSERT INTO bronze.raw_listings (file_hash, gcs_path, page_number, crawl_date, vin, car_model_slug, payload, crawled_at, source, run_id)
VALUES
('h1','gs://incremental_raw/dt=2026-05-22/1/1.json',1,'2026-05-22','VIN_TEST_1','toyota-camry-2020',
 '{"post":{"new_used":"Used","title":"2020 Toyota Camry","price":"25000","mileage":"30000","basic_desc":{"VIN":"VIN_TEST_1"}},"car":{"car_model":"toyota-camry-2020"}}'::jsonb,
 now(),'incremental','seed1'),
('h2','gs://incremental_raw/dt=2026-05-29/1/1.json',1,'2026-05-29','VIN_TEST_1','toyota-camry-2020',
 '{"post":{"new_used":"Used","title":"2020 Toyota Camry","price":"23000","mileage":"31000","basic_desc":{"VIN":"VIN_TEST_1"}},"car":{"car_model":"toyota-camry-2020"}}'::jsonb,
 now(),'incremental','seed2')
ON CONFLICT (file_hash) DO NOTHING;
SQL
```

- [ ] **Step 3: Ensure partitions for both months, then run dbt build inside the worker image**

```bash
docker compose exec -T postgres psql -U admin -d car_recsys -c \
  "SELECT gold.ensure_price_history_partition('2026-05-22'); SELECT gold.ensure_price_history_partition('2026-05-29');"

docker compose exec -T pipeline-worker dbt build --profiles-dir . --project-dir /app/dbt 2>&1 | tail -20
```
Expected: dbt build completes; models including `vehicle_price_history` succeed.

- [ ] **Step 4: Assert current = 1 row, history = 2 change events**

```bash
docker compose exec -T postgres psql -U admin -d car_recsys <<'SQL'
SELECT vin, price, first_seen_date, last_updated_date
  FROM gold.vehicles WHERE vin='VIN_TEST_1';
-- expect ONE row, price 23000, first_seen 2026-05-22, last_updated 2026-05-29
SELECT vin, price, crawl_date FROM gold.vehicle_price_history
  WHERE vin='VIN_TEST_1' ORDER BY crawl_date;
-- expect TWO rows: (25000, 2026-05-22), (23000, 2026-05-29)
SQL
```
Expected: gold.vehicles has 1 row with the latest price and preserved first_seen;
history has 2 rows. If history shows only 1, the change-detection WHERE is wrong —
revisit Task 7 Step 1.

- [ ] **Step 5: Idempotency — rerun dbt build, history unchanged**

```bash
docker compose exec -T pipeline-worker dbt build --profiles-dir . --project-dir /app/dbt 2>&1 | tail -5
docker compose exec -T postgres psql -U admin -d car_recsys -c \
  "SELECT count(*) FROM gold.vehicle_price_history WHERE vin='VIN_TEST_1';"
```
Expected: count still `2` (no new change → no new rows).

- [ ] **Step 6: Clean up seed rows**

```bash
docker compose exec -T postgres psql -U admin -d car_recsys -c \
  "DELETE FROM bronze.raw_listings WHERE run_id IN ('seed1','seed2');"
```

- [ ] **Step 7: Commit (verification notes, if any docs changed)**

No code changes here. If you adjusted any model to make the asserts pass, commit
those under the relevant task's message.

---

## Self-Review Notes

- **Spec coverage:** bucket isolation (T1,T2,T10), bronze cols (T3), VIN upsert (T6), day-partitioned history (T3,T7), change-only history (T7,T11), dbt-driven dedup (T4–T7), partition mgmt (T3,T8), incremental embed (T9), e2e verification (T11). All spec sections mapped.
- **Type consistency:** `crawl_date` is a `str` ("YYYY-MM-DD") everywhere it crosses Temporal boundaries; cast to `::date` only in SQL. `load_bronze(config, run_id)` matches the activity call. `CrawlInput(page, crawl_date)` matches all three crawl activities. `embed_vehicles(..., since_date=...)` matches the activity call.
- **No placeholders:** every code step shows full code or exact SQL/commands.
