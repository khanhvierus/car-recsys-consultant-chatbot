/*
  Fact: one row per car MODEL — the aggregate rating snapshot from cars.com.
  MODEL-level, never per-listing. Joined to listings only by FK in Gold.
*/
select
    md5(car_model_slug)        as car_model_sk,
    car_model_slug,
    car_rating,
    car_rating_count,
    percentage_recommend,
    rating_comfort,
    rating_interior,
    rating_performance,
    rating_value,
    rating_exterior,
    rating_reliability
from {{ ref('stg_car_models') }}
