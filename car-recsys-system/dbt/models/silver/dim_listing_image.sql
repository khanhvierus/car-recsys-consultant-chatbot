/*
  Dimension: listing × image. Restricted to listings present in fct_listing.
  image_url is the source cars.com CDN URL (the app serves images from there).
*/
select
    fl.listing_sk,
    li.vin,
    li.image_order,
    li.image_url
from {{ ref('stg_listing_images') }} li
join {{ ref('fct_listing') }} fl
    on md5(li.vin) = fl.listing_sk
