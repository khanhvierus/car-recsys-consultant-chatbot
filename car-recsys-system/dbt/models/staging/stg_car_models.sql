/*
  One row per car MODEL (e.g. toyota-4runner-2019). car.* data is model-level
  and shared across every listing of that model — deduped here on car_model.
  Carries both the model identity AND its rating snapshot (split later into
  dim_car_model + fct_model_rating).
*/
with ranked as (
    select
        payload->'car'                                 as car,
        row_number() over (
            partition by payload->'car'->>'car_model'
            order by ingested_at desc
        ) as rn
    from {{ source('bronze', 'raw_listings') }}
    where payload->'car'->>'car_model' is not null
      and payload->'car'->>'car_model' <> ''
)

select
    car->>'car_model'                                  as car_model_slug,
    car->>'brand'                                      as brand,
    car->>'car_name'                                   as car_name,
    car->>'car_link'                                   as car_link,
    car->>'review_link'                                as review_link,
    {{ safe_numeric("car->>'car_rating'") }}           as car_rating,
    {{ safe_integer("car->>'car_rating_count'") }}     as car_rating_count,
    {{ safe_numeric("car->>'percentage_recommend'") }} as percentage_recommend,
    {{ safe_numeric("car->'ratings'->>'Comfort'") }}     as rating_comfort,
    {{ safe_numeric("car->'ratings'->>'Interior'") }}    as rating_interior,
    {{ safe_numeric("car->'ratings'->>'Performance'") }} as rating_performance,
    {{ safe_numeric("car->'ratings'->>'Value'") }}       as rating_value,
    {{ safe_numeric("car->'ratings'->>'Exterior'") }}    as rating_exterior,
    {{ safe_numeric("car->'ratings'->>'Reliability'") }} as rating_reliability
from ranked
where rn = 1
