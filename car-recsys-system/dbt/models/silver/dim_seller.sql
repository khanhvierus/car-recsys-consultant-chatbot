/*
  Dimension: one row per dealer. hours/highlights kept as JSONB (variable shape).
*/
select
    md5(seller_key)            as seller_sk,
    seller_key,
    seller_name,
    seller_link,
    seller_website,
    destination,
    seller_rating,
    seller_rating_count,
    description,
    phone_new,
    phone_used,
    phone_service,
    hours,
    highlights,
    current_timestamp          as dbt_loaded_at
from {{ ref('stg_sellers') }}
