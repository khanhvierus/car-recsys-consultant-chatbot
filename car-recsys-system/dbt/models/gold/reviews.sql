/*
  Gold mart: one row per consumer review, joined to brand/car_name for display.
*/
select
    r.review_sk,
    r.car_model_slug                as car_model,
    cm.brand,
    cm.car_name,
    r.overall_rating,
    r.review_date,
    r.review_time_raw,
    r.user_name,
    r.reviewer_from,
    r.review_title,
    r.review_text,
    r.rb_comfort,
    r.rb_interior,
    r.rb_performance,
    r.rb_value,
    r.rb_exterior,
    r.rb_reliability
from {{ ref('fct_model_review') }} r
left join {{ ref('dim_car_model') }} cm on r.car_model_sk = cm.car_model_sk
