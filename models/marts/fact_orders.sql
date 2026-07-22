-- MART: fact_orders — public, contracted order fact (one row per order).
-- Grain matches the link: one row per order (customer x product occurrence).
-- Joins the link to the latest sat_order_details row and derives total_amount.
-- Columns are cast explicitly so the output types match the enforced contract.

with current_sat as (

    select
        link_customer_product_hk,
        order_date,
        quantity,
        unit_price,
        load_date,
        record_source
    from {{ ref('sat_order_details') }}
    qualify row_number() over (partition by link_customer_product_hk order by load_date desc) = 1

)

select
    cast(l.link_customer_product_hk       as varchar)        as link_customer_product_hk,
    cast(l.order_id                       as varchar)        as order_id,
    cast(l.customer_hk                    as varchar)        as customer_hk,
    cast(l.product_hk                     as varchar)        as product_hk,
    cast(s.order_date                     as date)           as order_date,
    cast(s.quantity                       as number(38, 0))  as quantity,
    cast(s.unit_price                     as number(10, 2))  as unit_price,
    cast(s.quantity * s.unit_price        as number(38, 2))  as total_amount,
    cast(s.load_date                      as timestamp_ntz)  as load_date,
    cast(s.record_source                  as varchar)        as record_source
from {{ ref('link_customer_product') }} as l
left join current_sat as s on l.link_customer_product_hk = s.link_customer_product_hk
