# dbt — Car Recsys transformations

Transforms crawled cars.com JSON (`bronze.raw_listings`) into a 3NF Silver
model and app-facing Gold marts, in PostgreSQL.

## Layers

```
bronze.raw_listings        (JSONB landing — loaded by the Temporal load_bronze activity)
        │
        ▼  staging/  (views in schema silver_staging)
stg_raw_latest → stg_listings / stg_sellers / stg_car_models /
                 stg_listing_features / stg_listing_images / stg_model_reviews
        │
        ▼  silver/  (tables in schema silver)
dim_car_model · fct_model_rating · dim_seller · dim_feature ·
fct_listing (incremental) · bridge_listing_feature ·
fct_model_review · dim_listing_image
        │
        ▼  gold/  (tables in schema gold — what the FastAPI backend reads)
vehicles · car_models · sellers · reviews · vehicle_features · vehicle_images
```

Price/mileage change history lives in `gold/vehicle_price_history` — an
append-only change-event log (one row per detected change), written into a
Postgres table RANGE-partitioned by `crawl_date`. (An earlier SCD-2 snapshot
approach was dropped in favor of this lighter model.)

> **Editing models:** the Temporal `pipeline-worker` image BAKES this dbt
> project (`COPY car-recsys-system/dbt` in `crawler/Dockerfile.pipeline`). After
> changing any model, rebuild the image —
> `docker build -f crawler/Dockerfile.pipeline -t car-pipeline-worker:latest .`
> from the repo root — or the worker will run a stale copy.

## Grain rule (important)

`car.*` data (rating, reviews) is **per car MODEL**, shared by every listing
of that model. It lives only in `dim_car_model` / `fct_model_rating` /
`fct_model_review`, keyed on `car_model_slug`. Gold *copies* (never aggregates)
the model rating onto each listing. Never count reviews per listing.

## Running

Connection is via env vars (see `profiles.yml`):
`DBT_PG_HOST DBT_PG_PORT DBT_PG_USER DBT_PG_PASSWORD DBT_PG_DBNAME`.

```bash
export DBT_PG_HOST=localhost DBT_PG_PORT=5432 \
       DBT_PG_USER=admin DBT_PG_PASSWORD=admin123 DBT_PG_DBNAME=car_recsys

dbt parse  --profiles-dir .     # validate project (no DB needed)
dbt build  --profiles-dir .     # run models + tests
dbt docs generate --profiles-dir .   # lineage graph
```

In production this runs as the Temporal Transform workflow (dbt_build activity) —
dbt build runs the whole model DAG in one step.

## Notes

- No external dbt packages — surrogate keys use Postgres-native `md5()`, tests
  are dbt built-ins (`unique`, `not_null`, `relationships`, `accepted_values`).
- `macros/generate_schema_name.sql` makes `+schema` land literally in
  `silver`/`gold` (not the dbt-default `<target>_silver`).
- `fct_listing` is incremental (`delete+insert` on `vin`) — idempotent reruns.
- The `gold.mv_popular_vehicles` / `gold.mv_trending_models` materialized views
  are NOT dbt models (they join app-written tables) — see
  `../database/matviews.sql`, refreshed by the transform DAG.
