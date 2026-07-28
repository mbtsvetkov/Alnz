-- HUB: hub_product
-- One row per unique product business key. Insert-only.

{{ config(materialized='incremental') }}

with staged as (

    select
        product_hk,
        product_id,
        load_date,
        record_source
    from {{ ref('stg_products') }}

),

deduplicated as (

    select
        product_hk,
        product_id,
        load_date,
        record_source
    from staged
    qualify row_number() over (partition by product_hk order by load_date) = 1

)

select * from deduplicated

{% if is_incremental() %}
where product_hk not in (select product_hk from {{ this }})
{% endif %}
