-- MART: dim_customer (v1) — public, contracted customer dimension.
-- Current-state view: hub_customer joined to the latest sat_customer_details row.
-- Kept alive during the deprecation window so consumers on
-- ref('dim_customer', version=1) keep working while they migrate to v2.
-- Columns are cast explicitly so the output types match the enforced contract.

with current_sat as (

    select
        customer_hk,
        first_name,
        last_name,
        email,
        country,
        signup_date,
        load_date,
        record_source
    from {{ ref('sat_customer_details') }}
    qualify row_number() over (partition by customer_hk order by load_date desc) = 1

)

select
    cast(h.customer_hk   as varchar)        as customer_hk,
    cast(h.customer_id   as varchar)        as customer_id,
    cast(s.first_name    as varchar)        as first_name,
    cast(s.last_name     as varchar)        as last_name,
    cast(s.email         as varchar)        as email,
    cast(s.country       as varchar)        as country,
    cast(s.signup_date   as date)           as signup_date,
    cast(s.load_date     as timestamp_ntz)  as load_date,
    cast(s.record_source as varchar)        as record_source
from {{ ref('hub_customer') }} as h
left join current_sat as s on h.customer_hk = s.customer_hk
