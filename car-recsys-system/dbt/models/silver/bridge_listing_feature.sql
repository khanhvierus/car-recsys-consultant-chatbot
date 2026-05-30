/*
  Bridge: listing × feature (many-to-many). Joins exploded listing features to
  the feature dimension, restricted to listings present in fct_listing.
*/
select distinct
    fl.listing_sk,
    df.feature_sk
from {{ ref('stg_listing_features') }} lf
join {{ ref('dim_feature') }} df
    on  lf.feature_category = df.feature_category
    and lf.feature_name     = df.feature_name
join {{ ref('fct_listing') }} fl
    on md5(lf.vin) = fl.listing_sk
