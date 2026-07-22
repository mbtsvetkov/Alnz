-- MART: dim_product — public, contracted product dimension.
-- Current-state view: hub_product joined to the latest sat_product_details row.
-- Columns are cast explicitly so the output types match the enforced contract.

with current_sat as (

    select
        product_hk,
        product_name,
        category,
        price,
        load_date,
        record_source
    from {{ ref('sat_product_details') }}
    qualify row_number() over (partition by product_hk order by load_date desc) = 1

)

select
    cast(h.product_hk    as varchar)        as product_hk,
    cast(h.product_id    as varchar)        as product_id,
    cast(s.product_name  as varchar)        as product_name,
    cast(s.category      as varchar)        as category,
    cast(s.price         as number(10, 2))  as price,
    cast(s.load_date     as timestamp_ntz)  as load_date,
    cast(s.record_source as varchar)        as record_source
from {{ ref('hub_product') }} as h
left join current_sat as s on h.product_hk = s.product_hk
