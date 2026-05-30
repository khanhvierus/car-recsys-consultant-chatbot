/*
  One row per dealer. A seller appears across many listings; keep the most
  recently ingested version of its details.
*/
with ranked as (
    select
        payload->'seller'                              as seller,
        row_number() over (
            partition by payload->'seller'->>'seller_key'
            order by ingested_at desc
        ) as rn
    from {{ source('bronze', 'raw_listings') }}
    where payload->'seller'->>'seller_key' is not null
      and payload->'seller'->>'seller_key' <> ''
)

select
    seller->>'seller_key'                              as seller_key,
    seller->>'seller_name'                             as seller_name,
    seller->>'seller_link'                             as seller_link,
    seller->>'seller_website'                          as seller_website,
    seller->>'destination'                             as destination,
    {{ safe_numeric("seller->>'seller_rating'") }}     as seller_rating,
    {{ safe_integer("seller->>'seller_rating_count'") }} as seller_rating_count,
    seller->>'description'                             as description,
    seller->'phone_info'->>'New'                       as phone_new,
    seller->'phone_info'->>'Used'                      as phone_used,
    seller->'phone_info'->>'Service'                   as phone_service,
    case when jsonb_typeof(seller->'hours') = 'object'
         then seller->'hours' else null end            as hours,
    case when jsonb_typeof(seller->'highlights') = 'array'
         then seller->'highlights' else null end       as highlights
from ranked
where rn = 1
