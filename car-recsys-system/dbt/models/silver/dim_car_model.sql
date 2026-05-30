/*
  Dimension: one row per car MODEL (e.g. toyota-4runner-2019).
  Identity only — the rating snapshot lives in fct_model_rating.
*/
select
    md5(car_model_slug)        as car_model_sk,
    car_model_slug,
    brand,
    car_name,
    car_link,
    review_link,
    current_timestamp          as dbt_loaded_at
from {{ ref('stg_car_models') }}
