{#
  Override dbt's default schema-naming. By default dbt prefixes a custom
  +schema with the target schema (e.g. `gold` -> `<target>_gold`). We want
  the medallion schemas to be used LITERALLY (`silver`, `gold`, ...) because
  the FastAPI backend and the init SQL reference those exact names.
#}
{% macro generate_schema_name(custom_schema_name, node) -%}
    {%- if custom_schema_name is none -%}
        {{ target.schema }}
    {%- else -%}
        {{ custom_schema_name | trim }}
    {%- endif -%}
{%- endmacro %}
