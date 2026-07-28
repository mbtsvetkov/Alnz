-- Staging: clean/standardise raw customers and attach Data Vault hashes.
-- Materialized as a view (see dbt_project.yml) — cheap and always fresh.

with source as (

    select * from {{ ref('raw_customers') }}

),

renamed as (

    select
        cast(customer_id as varchar)   as customer_id,
        cast(first_name  as varchar)   as first_name,
        cast(last_name   as varchar)   as last_name,
        cast(email       as varchar)   as email,
        cast(country     as varchar)   as country,
        cast(signup_date as date)      as signup_date
    from source

)

select
    -- business key
    customer_id,

    -- data vault hash keys
    {{ generate_hashkey(['customer_id']) }}                                                  as customer_hk,
    {{ generate_hashdiff(['first_name', 'last_name', 'email', 'country', 'signup_date']) }}   as customer_hashdiff,

    -- descriptive attributes
    first_name,
    last_name,
    email,
    country,
    signup_date,

    -- data vault metadata
    'seed.raw_customers'                       as record_source,
    cast(current_timestamp() as timestamp_ntz) as load_date

from renamed
