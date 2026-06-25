{#
    generate_hashkey
    ----------------
    Builds a Data Vault hash key (MD5) from one or more business-key columns.

    Data Vault standardisation applied to every column before hashing:
      - cast to varchar   -> consistent typing
      - trim              -> remove leading/trailing whitespace
      - upper             -> case-insensitive keys ("ABC" == "abc")
      - null handling     -> NULL/'' become a fixed sentinel so keys stay deterministic

    Columns are concatenated with a '||' delimiter (prevents accidental collisions
    such as 'a' + 'bc' == 'ab' + 'c') and hashed with MD5, producing a stable,
    32-char, source-independent surrogate key.

    Usage:
      {{ generate_hashkey(['customer_id']) }}
      {{ generate_hashkey(['customer_id', 'product_id', 'order_id']) }}
#}
{% macro generate_hashkey(columns) %}
    md5(
        concat_ws('||'
        {%- for column in columns %}
            , coalesce(nullif(upper(trim(cast({{ column }} as varchar))), ''), '^^NULL^^')
        {%- endfor %}
        )
    )
{%- endmacro %}
