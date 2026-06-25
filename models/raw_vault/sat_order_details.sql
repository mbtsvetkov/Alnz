-- SATELLITE: sat_order_details (hangs off link_customer_product)
-- Descriptive order attributes (date, quantity, unit_price) with insert-only history,
-- keyed by the link hash. New row only when the order's attributes change.

{{ config(materialized='incremental') }}

with staged as (

    select
        link_customer_product_hk,
        order_hashdiff,
        order_date,
        quantity,
        unit_price,
        load_date,
        record_source
    from {{ ref('stg_orders') }}

)

{% if is_incremental() %}
, current_records as (

    select
        link_customer_product_hk,
        order_hashdiff
    from {{ this }}
    qualify row_number() over (partition by link_customer_product_hk order by load_date desc) = 1

)
{% endif %}

select s.*
from staged s
{% if is_incremental() %}
left join current_records c
    on  s.link_customer_product_hk = c.link_customer_product_hk
    and s.order_hashdiff           = c.order_hashdiff
where c.link_customer_product_hk is null
{% endif %}
