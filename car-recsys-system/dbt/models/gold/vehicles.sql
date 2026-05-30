{{ config(
    materialized='incremental',
    unique_key='vin',
    incremental_strategy='merge',
    merge_exclude_columns=['first_seen_date']
) }}

/*
  Gold mart: one row per listing — the backend's primary table (replaces the
  legacy raw.used_vehicles). `vehicle_id` is kept as an alias of `vin` so the
  FastAPI repoint from raw.* to gold.* is near-mechanical. The car-MODEL rating
  is COPIED onto each listing (deliberate read optimization — never aggregated).
*/
with img_agg as (
    select
        listing_sk,
        count(*)                                              as image_count,
        max(image_url) filter (where image_order = 1)         as primary_image_url
    from {{ ref('dim_listing_image') }}
    group by listing_sk
),

feat_agg as (
    select listing_sk, count(*) as feature_count
    from {{ ref('bridge_listing_feature') }}
    group by listing_sk
)

select
    fl.vin                          as vehicle_id,      -- backend-compat alias
    fl.vin,
    fl.listing_sk,
    fl.stock_number,
    fl.new_used,
    fl.title,
    cm.brand,
    cm.car_name,
    fl.car_model_slug               as car_model,
    fl.price,
    fl.monthly_payment,
    fl.mileage,
    fl.exterior_color,
    fl.interior_color,
    fl.fuel_type,
    fl.engine,
    fl.mpg,
    fl.drivetrain,
    fl.transmission,
    fl.clean_title,
    fl.has_accidents,
    fl.is_one_owner,
    fl.is_personal_use,
    fl.has_open_recall,
    fl.warranty,
    -- seller (denormalized)
    ds.seller_key,
    ds.seller_name,
    ds.seller_link,
    ds.destination,
    ds.seller_rating,
    ds.seller_rating_count,
    -- car-model rating (copied, not aggregated)
    mr.car_rating,
    mr.car_rating_count,
    mr.percentage_recommend,
    mr.rating_comfort,
    mr.rating_interior,
    mr.rating_performance,
    mr.rating_value,
    mr.rating_exterior,
    mr.rating_reliability,
    cm.car_link,
    cm.review_link,
    -- aggregates
    coalesce(img.image_count, 0)    as image_count,
    img.primary_image_url,
    coalesce(feat.feature_count, 0) as feature_count,
    fl.source,
    fl.last_updated_date,
    coalesce(fl.crawl_date, current_date) as first_seen_date,
    fl.crawled_at,
    fl.dbt_loaded_at,
    -- legacy-compatible aliases — let the FastAPI backend repoint from
    -- raw.used_vehicles to gold.vehicles as a pure schema-name swap.
    fl.new_used                     as condition,
    cm.car_link                     as vehicle_url,
    mr.rating_comfort               as comfort_rating,
    mr.rating_interior              as interior_rating,
    mr.rating_performance           as performance_rating,
    mr.rating_value                 as value_rating,
    mr.rating_exterior              as exterior_rating,
    mr.rating_reliability           as reliability_rating
from {{ ref('fct_listing') }} fl
left join {{ ref('dim_car_model') }}   cm  on fl.car_model_sk = cm.car_model_sk
left join {{ ref('fct_model_rating') }} mr on fl.car_model_sk = mr.car_model_sk
left join {{ ref('dim_seller') }}      ds  on fl.seller_sk    = ds.seller_sk
left join img_agg  img  on fl.listing_sk = img.listing_sk
left join feat_agg feat on fl.listing_sk = feat.listing_sk
{% if is_incremental() %}
where fl.last_updated_date >= (select coalesce(max(last_updated_date), '1900-01-01') from {{ this }})
{% endif %}
