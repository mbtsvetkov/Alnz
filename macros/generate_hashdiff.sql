{#
    generate_hashdiff
    -----------------
    Builds a Data Vault hashdiff (MD5) over a satellite's DESCRIPTIVE attributes.

    Purpose: change detection. A satellite stores history insert-only. On each load
    we compare the incoming hashdiff to the current record's hashdiff for the same
    parent hash key:
      - different hashdiff -> attributes changed -> insert a new version
      - same hashdiff      -> nothing changed    -> skip (no duplicate row)

    Mechanically identical to generate_hashkey (same standardisation + MD5). It is
    kept as a separate, intention-revealing macro — "this hash represents attribute
    state, not identity" — while delegating to generate_hashkey to stay DRY.

    Usage:
      {{ generate_hashdiff(['first_name', 'last_name', 'email', 'country']) }}
#}
{% macro generate_hashdiff(columns) %}
    {{ generate_hashkey(columns) }}
{%- endmacro %}
