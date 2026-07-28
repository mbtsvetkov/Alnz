-- SATELLITE: sat_customer_details (hangs off hub_customer)
-- Stores descriptive customer attributes with full history (insert-only).
-- A new row is inserted only when the hashdiff changes for a given customer_hk,
-- so unchanged loads add no duplicate rows.

{{ config(materialized='incremental') }}

with staged as (

    select
        customer_hk,
        customer_hashdiff,
        first_name,
        last_name,
        email,
        country,
        signup_date,
        load_date,
        record_source
    from {{ ref('stg_customers') }}

)

{% if is_incremental() %}
, current_records as (

    -- latest stored version per customer_hk
    select
        customer_hk,
        customer_hashdiff
    from {{ this }}
    qualify row_number() over (partition by customer_hk order by load_date desc) = 1

)
{% endif %}

select s.*
from staged s
{% if is_incremental() %}
left join current_records c
    on  s.customer_hk       = c.customer_hk
    and s.customer_hashdiff = c.customer_hashdiff
-- insert when the customer is new (no current row) or its attributes changed
where c.customer_hk is null
{% endif %}
