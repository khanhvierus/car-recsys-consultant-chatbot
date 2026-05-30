/*
  Explodes car.reviews[] into one row per consumer review. Reviews belong to
  the car MODEL, not the listing — keyed on car_model_slug. Deduped here on a
  content hash so re-crawls of the same model don't multiply reviews.
*/
with model_latest as (
    select
        payload->>'car' as _unused,                    -- keep planner happy
        car_model_slug,
        payload->'car'->'reviews' as reviews,
        row_number() over (
            partition by car_model_slug order by ingested_at desc
        ) as rn
    from {{ source('bronze', 'raw_listings') }}
    where car_model_slug is not null
      and car_model_slug <> ''
),

exploded as (
    select
        model_latest.car_model_slug,
        review.value as review
    from model_latest,
         lateral jsonb_array_elements(
             coalesce(model_latest.reviews, '[]'::jsonb)
         ) as review
    where model_latest.rn = 1
      and jsonb_typeof(model_latest.reviews) = 'array'
)

select
    md5(
        car_model_slug
        || coalesce(review->>'user_name', '')
        || coalesce(review->>'time', '')
        || coalesce(review->>'title', '')
        || left(coalesce(review->>'review', ''), 64)
    )                                                  as review_sk,
    car_model_slug,
    {{ safe_numeric("review->>'overall_rating'") }}    as overall_rating,
    {{ parse_review_date("review->>'time'") }}         as review_date,
    review->>'time'                                    as review_time_raw,
    review->>'user_name'                               as user_name,
    review->>'from'                                    as reviewer_from,
    review->>'title'                                   as review_title,
    review->>'review'                                  as review_text,
    {{ safe_numeric("review->'ratings_breakdown'->>'Comfort'") }}     as rb_comfort,
    {{ safe_numeric("review->'ratings_breakdown'->>'Interior'") }}    as rb_interior,
    {{ safe_numeric("review->'ratings_breakdown'->>'Performance'") }} as rb_performance,
    {{ safe_numeric("review->'ratings_breakdown'->>'Value'") }}       as rb_value,
    {{ safe_numeric("review->'ratings_breakdown'->>'Exterior'") }}    as rb_exterior,
    {{ safe_numeric("review->'ratings_breakdown'->>'Reliability'") }} as rb_reliability
from exploded
