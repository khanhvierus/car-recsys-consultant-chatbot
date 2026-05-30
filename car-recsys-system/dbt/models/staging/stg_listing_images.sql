/*
  Explodes post.image[] into one row per (vin, image_order, image_url).
  WITH ORDINALITY preserves the gallery order.
*/
with raw as (
    select vin, payload from {{ ref('stg_raw_latest') }}
)

select
    raw.vin,
    img.ord::int            as image_order,
    img.url                 as image_url
from raw,
     lateral jsonb_array_elements_text(
         coalesce(raw.payload->'post'->'image', '[]'::jsonb)
     ) with ordinality as img(url, ord)
where jsonb_typeof(raw.payload->'post'->'image') = 'array'
  and img.url is not null
  and img.url <> ''
