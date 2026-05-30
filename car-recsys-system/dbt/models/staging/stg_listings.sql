/*
  One row per current listing (VIN). Scalar fields from post.* plus the
  basic_desc and user_history_des sub-objects, fully type-cast. This is where
  the legacy "mixed NUMERIC/TEXT" mess gets fixed once and for all.
*/
with raw as (
    select * from {{ ref('stg_raw_latest') }}
)

select
    vin,
    car_model_slug,
    payload->'seller'->>'seller_key'                  as seller_key,

    payload->'post'->'basic_desc'->>'Stock Number'    as stock_number,
    initcap(payload->'post'->>'new_used')             as new_used,
    payload->'post'->>'title'                         as title,

    {{ safe_numeric("payload->'post'->>'price'") }}           as price,
    {{ safe_numeric("payload->'post'->>'monthly_payment'") }} as monthly_payment,
    {{ safe_integer("payload->'post'->>'mileage'") }}         as mileage,

    payload->'post'->'basic_desc'->>'Exterior Color'  as exterior_color,
    payload->'post'->'basic_desc'->>'Interior Color'  as interior_color,
    payload->'post'->'basic_desc'->>'Fuel Type'       as fuel_type,
    payload->'post'->'basic_desc'->>'Engine'          as engine,
    payload->'post'->'basic_desc'->>'MPG'             as mpg,
    payload->'post'->'basic_desc'->>'Drivetrain'      as drivetrain,
    payload->'post'->'basic_desc'->>'Transmission'    as transmission,

    {{ history_to_bool("payload->'post'->'user_history_des'->>'Clean Title'", ['yes']) }}
        as clean_title,
    {{ history_to_bool("payload->'post'->'user_history_des'->>'Accidents or damage'",
                        ['accident', 'damage reported']) }}
        as has_accidents,
    {{ history_to_bool("payload->'post'->'user_history_des'->>'1-owner vehicle'", ['yes']) }}
        as is_one_owner,
    {{ history_to_bool("payload->'post'->'user_history_des'->>'Personal use only'", ['yes']) }}
        as is_personal_use,
    {{ history_to_bool("payload->'post'->'user_history_des'->>'Open recall'",
                        ['at least', 'recall reported']) }}
        as has_open_recall,

    payload->'post'->'warranty_des'                   as warranty,   -- nullable JSONB
    crawl_date,
    source,
    crawled_at,
    gcs_path
from raw
