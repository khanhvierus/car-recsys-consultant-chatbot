/*
  Fact: one row per CURRENT listing (VIN). Incremental — a re-crawled VIN with
  a newer crawled_at replaces its row (delete+insert on vin), so the table is
  both idempotent and incremental. car_model_sk / seller_sk are NULL-safe
  (md5(null) = null) so listings with a missing model/seller still land.
*/
{{ config(
    materialized='incremental',
    unique_key='vin',
    incremental_strategy='delete+insert'
) }}

select
    md5(vin)                   as listing_sk,
    vin,
    stock_number,
    new_used,
    title,
    md5(car_model_slug)        as car_model_sk,
    md5(seller_key)            as seller_sk,
    car_model_slug,
    seller_key,
    price,
    monthly_payment,
    mileage,
    crawl_date,
    source,
    crawl_date                  as last_updated_date,
    exterior_color,
    interior_color,
    fuel_type,
    engine,
    mpg,
    drivetrain,
    transmission,
    clean_title,
    has_accidents,
    is_one_owner,
    is_personal_use,
    has_open_recall,
    warranty,
    crawled_at,
    current_timestamp          as dbt_loaded_at
from {{ ref('stg_listings') }}

{% if is_incremental() %}
where crawled_at > (select coalesce(max(crawled_at), '1900-01-01'::timestamptz) from {{ this }})
{% endif %}
