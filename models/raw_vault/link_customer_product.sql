-- LINK: link_customer_product
-- Connects hub_customer and hub_product. Transactional grain: one row per order
-- (the relationship occurrence). Insert-only: each unique link hash is appended once.

{{ config(materialized='incremental') }}

with staged as (

    select
        link_customer_product_hk,
        customer_hk,
        product_hk,
        order_id,
        load_date,
        record_source
    from {{ ref('stg_orders') }}

),

deduplicated as (

    select
        link_customer_product_hk,
        customer_hk,
        product_hk,
        order_id,
        load_date,
        record_source
    from staged
    qualify row_number() over (partition by link_customer_product_hk order by load_date) = 1

)

select * from deduplicated

{% if is_incremental() %}
where link_customer_product_hk not in (select link_customer_product_hk from {{ this }})
{% endif %}
