-- HUB: hub_customer
-- One row per unique customer business key. Insert-only: once a key exists it is
-- never updated or removed; new keys are appended on each load.

{{ config(materialized='incremental') }}

with staged as (

    select
        customer_hk,
        customer_id,
        load_date,
        record_source
    from {{ ref('stg_customers') }}

),

-- keep the earliest-seen record per business key (first load wins for the hub)
deduplicated as (

    select
        customer_hk,
        customer_id,
        load_date,
        record_source
    from staged
    qualify row_number() over (partition by customer_hk order by load_date) = 1

)

select * from deduplicated

{% if is_incremental() %}
-- only append business keys not already present in the hub
where customer_hk not in (select customer_hk from {{ this }})
{% endif %}
