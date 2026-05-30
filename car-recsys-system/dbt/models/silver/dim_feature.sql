/*
  Dimension: one row per distinct (category, feature) pair across all listings.
*/
with distinct_features as (
    select distinct
        feature_category,
        feature_name
    from {{ ref('stg_listing_features') }}
)

select
    md5(feature_category || '||' || feature_name) as feature_sk,
    feature_category,
    feature_name
from distinct_features
