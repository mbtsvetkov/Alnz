-- Staging: clean/standardise raw products and attach Data Vault hashes.

with source as (

    select * from {{ ref('raw_products') }}

),

renamed as (

    select
        cast(product_id   as varchar)      as product_id,
        cast(product_name as varchar)      as product_name,
        cast(category     as varchar)      as category,
        cast(price        as number(10,2)) as price
    from source

)

select
    -- business key
    product_id,

    -- data vault hash keys
    {{ generate_hashkey(['product_id']) }}                          as product_hk,
    {{ generate_hashdiff(['product_name', 'category', 'price']) }}  as product_hashdiff,

    -- descriptive attributes
    product_name,
    category,
    price,

    -- data vault metadata
    'seed.raw_products'                        as record_source,
    cast(current_timestamp() as timestamp_ntz) as load_date

from renamed
