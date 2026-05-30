/*
  The latest raw payload per VIN. Bronze is append-only — a re-crawled VIN
  has multiple rows; here we keep only the most recently ingested one.
  All listing-grained staging models build on this so they agree on "current".
*/
with ranked as (
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
            -- crawl_date is the true crawl recency; ingested_at only breaks ties
            -- within the same crawl day (and guards a backfill loading old data
            -- after new data — DB-insert time must NOT decide "latest").
            order by crawl_date desc nulls last, ingested_at desc
        ) as rn
    from {{ source('bronze', 'raw_listings') }}
    where vin is not null
      and vin <> ''
)

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
