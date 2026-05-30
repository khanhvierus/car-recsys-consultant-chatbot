/*
  Gold mart: listing images (vehicle_id, image_order, image_url).
  `id` is a synthetic ordering key kept for backend-query compatibility
  (the legacy raw.vehicle_images had an id; queries ORDER BY it).
*/
select
    row_number() over (order by vin, image_order) as id,
    vin          as vehicle_id,
    image_order,
    image_url
from {{ ref('dim_listing_image') }}
