-- SATELLITE: sat_product_details (hangs off hub_product)
-- Descriptive product attributes with insert-only history, keyed by product_hk.

{{ config(materialized='incremental') }}

with staged as (

    select
        product_hk,
        product_hashdiff,
        product_name,
        category,
        price,
        load_date,
        record_source
    from {{ ref('stg_products') }}

)

{% if is_incremental() %}
, current_records as (

    select
        product_hk,
        product_hashdiff
    from {{ this }}
    qualify row_number() over (partition by product_hk order by load_date desc) = 1

)
{% endif %}

select s.*
from staged s
{% if is_incremental() %}
left join current_records c
    on  s.product_hk       = c.product_hk
    and s.product_hashdiff = c.product_hashdiff
where c.product_hk is null
{% endif %}
