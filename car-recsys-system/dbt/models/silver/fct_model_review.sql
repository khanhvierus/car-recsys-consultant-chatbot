/*
  Fact: one row per consumer review. Reviews belong to the car MODEL, keyed on
  car_model_sk — never per-listing. Full table rebuild (review volume is small
  enough; dedup already done in staging via the content hash review_sk).
*/
select
    sr.review_sk,
    md5(sr.car_model_slug)     as car_model_sk,
    sr.car_model_slug,
    sr.overall_rating,
    sr.review_date,
    sr.review_time_raw,
    sr.user_name,
    sr.reviewer_from,
    sr.review_title,
    sr.review_text,
    sr.rb_comfort,
    sr.rb_interior,
    sr.rb_performance,
    sr.rb_value,
    sr.rb_exterior,
    sr.rb_reliability
from {{ ref('stg_model_reviews') }} sr
