/*
  Gold mart: denormalized listing features (vehicle_id, category, name) — keeps
  the backend's existing feature query working with a one-line table swap.
*/
select
    fl.vin              as vehicle_id,
    df.feature_category,
    df.feature_name
from {{ ref('bridge_listing_feature') }} b
join {{ ref('fct_listing') }} fl on b.listing_sk = fl.listing_sk
join {{ ref('dim_feature') }} df on b.feature_sk = df.feature_sk
