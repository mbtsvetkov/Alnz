-- MART: dim_customer (v2, latest) — public, contracted customer dimension.
-- Additive change over v1: adds email_domain (an additive column is a MINOR
-- version — v1 consumers are unaffected; v1 is deprecated on a published date).
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
    cast(h.customer_hk               as varchar)        as customer_hk,
    cast(h.customer_id               as varchar)        as customer_id,
    cast(s.first_name                as varchar)        as first_name,
    cast(s.last_name                 as varchar)        as last_name,
    cast(s.email                     as varchar)        as email,
    cast(split_part(s.email, '@', 2) as varchar)        as email_domain,
    cast(s.country                   as varchar)        as country,
    cast(s.signup_date               as date)           as signup_date,
    cast(s.load_date                 as timestamp_ntz)  as load_date,
    cast(s.record_source             as varchar)        as record_source
from {{ ref('hub_customer') }} as h
left join current_sat as s on h.customer_hk = s.customer_hk
