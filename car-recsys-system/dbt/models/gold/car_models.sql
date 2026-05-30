/*
  Gold mart: one row per car model. Model rating + listing/review aggregates.
  review_count is per MODEL — NOT multiplied by listing count (grain guard).
*/
with listing_agg as (
    select
        car_model_sk,
        count(*)        as listing_count,
        min(price)      as min_price,
        max(price)      as max_price,
        round(avg(price), 0) as avg_price
    from {{ ref('fct_listing') }}
    where car_model_sk is not null
    group by car_model_sk
),

review_agg as (
    select car_model_sk, count(*) as review_count
    from {{ ref('fct_model_review') }}
    group by car_model_sk
)

select
    cm.car_model_sk,
    cm.car_model_slug               as car_model,
    cm.brand,
    cm.car_name,
    cm.car_link,
    cm.review_link,
    mr.car_rating,
    mr.car_rating_count,
    mr.percentage_recommend,
    mr.rating_comfort,
    mr.rating_interior,
    mr.rating_performance,
    mr.rating_value,
    mr.rating_exterior,
    mr.rating_reliability,
    coalesce(la.listing_count, 0)   as listing_count,
    la.min_price,
    la.max_price,
    la.avg_price,
    coalesce(ra.review_count, 0)    as review_count
from {{ ref('dim_car_model') }} cm
left join {{ ref('fct_model_rating') }} mr on cm.car_model_sk = mr.car_model_sk
left join listing_agg la on cm.car_model_sk = la.car_model_sk
left join review_agg  ra on cm.car_model_sk = ra.car_model_sk
