/*
  Explodes post.feature_des — a {category: [feature, ...]} object — into one
  row per (vin, category, feature). jsonb_each over the categories, then
  jsonb_array_elements_text over each feature list.
*/
with raw as (
    select vin, payload from {{ ref('stg_raw_latest') }}
),

categories as (
    select
        raw.vin,
        cat.key                      as feature_category,
        cat.value                    as feature_list
    from raw,
         lateral jsonb_each(coalesce(raw.payload->'post'->'feature_des', '{}'::jsonb)) as cat
    where jsonb_typeof(raw.payload->'post'->'feature_des') = 'object'
)

select distinct
    categories.vin,
    trim(categories.feature_category)        as feature_category,
    trim(feature.value)                      as feature_name
from categories,
     lateral jsonb_array_elements_text(categories.feature_list) as feature
where jsonb_typeof(categories.feature_list) = 'array'
  and trim(feature.value) <> ''
