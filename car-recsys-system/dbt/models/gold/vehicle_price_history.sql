/*
  Change-event log of price / mileage / availability per VIN, appended to the
  partitioned parent gold.vehicle_price_history (created in init SQL). A row is
  written ONLY when (price, mileage, status) differs from the VIN's latest
  existing history row. Append-only incremental; never updates.

  IMPORTANT — partitioned-table contract
  ======================================
  gold.vehicle_price_history is a Postgres RANGE-partitioned table created by
  database/init/02-create-schema.sql.  dbt's incremental materialization will
  detect the pre-existing relation (existing_relation is not None) and will
  therefore always take the "else" branch: create a temp table → INSERT INTO
  target.  It will NEVER issue CREATE TABLE AS on first run.

  Because the partitioned parent already exists when dbt first runs,
  is_incremental() returns True on every normal `dbt run`.  The only scenario
  where is_incremental() is False is `dbt run --full-refresh`, which must NOT
  be run against this model (it would try to DROP the partitioned parent and
  recreate it as a plain table, destroying the partitioning).

  full_refresh=false: the target gold.vehicle_price_history is a pre-existing
  PARTITIONED parent (created in database/init/02-create-schema.sql). A dbt
  full-refresh would drop/replace it with a plain table and destroy all
  partitions, so full_refresh is permanently disabled at the model level — even
  if `--full-refresh` is passed on the CLI, dbt will skip this model.

  On the very first run the target table is empty, so latest_history returns
  zero rows and all current_listings are inserted as first-ever history rows —
  correct behaviour.

  On subsequent runs only VINs where (price, mileage, status) changed since
  the last crawl_date already in the table are inserted.
*/
{{ config(
    materialized='incremental',
    incremental_strategy='append',
    full_refresh=false
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
    -- Only process rows from crawl dates not yet fully captured in history.
    where crawl_date >= (
        select coalesce(max(crawl_date), '1900-01-01'::date)
        from {{ this }}
    )
    {% endif %}
)

{% if is_incremental() %}

-- Incremental path: detect changes vs. the most recent history row per VIN.
, latest_history as (
    select distinct on (vin)
        vin,
        price,
        mileage,
        status
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
where
    h.vin is null                          -- first time we see this VIN
    or c.price    is distinct from h.price
    or c.mileage  is distinct from h.mileage
    or c.status   is distinct from h.status

{% else %}

-- First-run path (is_incremental() = false only during `dbt parse` or
-- `dbt run --full-refresh`).  No reference to {{ this }} here.
-- Every row in current_listings becomes the initial history entry for its VIN.
select
    vin,
    price,
    mileage,
    status,
    crawl_date,
    now() as inserted_at
from current_listings

{% endif %}
