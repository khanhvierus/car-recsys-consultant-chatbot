/*
  Gold mart: one row per dealer + inventory aggregates.
*/
with inventory as (
    select
        seller_sk,
        count(*)             as inventory_count,
        round(avg(price), 0) as avg_listing_price
    from {{ ref('fct_listing') }}
    where seller_sk is not null
    group by seller_sk
)

select
    ds.seller_sk,
    ds.seller_key,
    ds.seller_name,
    ds.seller_link,
    ds.seller_website,
    ds.destination,
    ds.seller_rating,
    ds.seller_rating_count,
    ds.description,
    ds.phone_new,
    ds.phone_used,
    ds.phone_service,
    ds.hours,
    ds.highlights,
    coalesce(inv.inventory_count, 0) as inventory_count,
    inv.avg_listing_price
from {{ ref('dim_seller') }} ds
left join inventory inv on ds.seller_sk = inv.seller_sk
