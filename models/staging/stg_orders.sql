-- Staging: clean/standardise raw orders and derive all hashes needed by the
-- customer-product link and the order satellite.
--
-- The order is modelled as a TRANSACTIONAL link: one row per order connecting a
-- customer hub and a product hub. The link hash therefore includes order_id so each
-- order is a distinct relationship occurrence (two orders of the same customer+product
-- are two link rows).

with source as (

    select * from {{ ref('raw_orders') }}

),

renamed as (

    select
        cast(order_id    as varchar)       as order_id,
        cast(customer_id as varchar)       as customer_id,
        cast(product_id  as varchar)       as product_id,
        cast(order_date  as date)          as order_date,
        cast(quantity    as integer)       as quantity,
        cast(unit_price  as number(10,2))  as unit_price
    from source

)

select
    -- business keys
    order_id,
    customer_id,
    product_id,

    -- hub hash keys (must match the hubs' definitions exactly)
    {{ generate_hashkey(['customer_id']) }}  as customer_hk,
    {{ generate_hashkey(['product_id']) }}   as product_hk,

    -- link hash key (transactional grain: one row per order)
    {{ generate_hashkey(['customer_id', 'product_id', 'order_id']) }} as link_customer_product_hk,

    -- satellite hashdiff over the order's descriptive attributes
    {{ generate_hashdiff(['order_date', 'quantity', 'unit_price']) }} as order_hashdiff,

    -- descriptive attributes
    order_date,
    quantity,
    unit_price,

    -- data vault metadata
    'seed.raw_orders'                          as record_source,
    cast(current_timestamp() as timestamp_ntz) as load_date

from renamed
