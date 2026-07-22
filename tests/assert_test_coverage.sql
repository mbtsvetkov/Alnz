{#
    Coverage gate — turns the per-layer "minimum bar" from a convention into an
    automated check (generalises the assert_no_orphan_links idea to the whole
    project). Fails (returns rows) if a model in a governed layer is missing its
    required guardrails:

      staging / raw_vault : at least one data test attached
      marts               : at least one data test AND an enforced contract

    Introspects the graph, so it sees the whole project regardless of selection.
    A dbt test PASSES when it returns ZERO rows; any row here names a gap.
#}

{%- set governed_layers = ['staging', 'raw_vault', 'marts'] -%}
{%- set violations = [] -%}

{%- if execute -%}

    {#- unique_ids of every model that has a test attached -#}
    {%- set tested_models = [] -%}
    {%- for node in graph.nodes.values() if node.resource_type == 'test' -%}
        {%- if node.attached_node -%}
            {%- do tested_models.append(node.attached_node) -%}
        {%- endif -%}
        {%- for dep in node.depends_on.nodes -%}
            {%- do tested_models.append(dep) -%}
        {%- endfor -%}
    {%- endfor -%}

    {%- for node in graph.nodes.values() if node.resource_type == 'model' -%}
        {%- set layer = node.fqn[1] -%}
        {%- if layer in governed_layers -%}

            {%- if node.unique_id not in tested_models -%}
                {%- do violations.append(node.name ~ ' | ' ~ layer ~ ' | missing_required_tests') -%}
            {%- endif -%}

            {%- if layer == 'marts' -%}
                {%- set contract = node.config.get('contract', {}) if node.config is mapping else node.config.contract -%}
                {%- set enforced = contract.get('enforced', false) if contract is mapping else contract.enforced -%}
                {%- if not enforced -%}
                    {%- do violations.append(node.name ~ ' | ' ~ layer ~ ' | contract_not_enforced') -%}
                {%- endif -%}
            {%- endif -%}

        {%- endif -%}
    {%- endfor -%}

{%- endif -%}

{%- if violations | length > 0 -%}
    {%- for v in violations %}
    select '{{ v }}' as coverage_violation
    {% if not loop.last %}union all{% endif %}
    {%- endfor %}
{%- else -%}
    select cast(null as {{ dbt.type_string() }}) as coverage_violation where 1 = 0
{%- endif -%}
