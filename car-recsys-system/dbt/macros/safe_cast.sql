{#
  Numeric-safe cast: strips currency/grouping characters then casts, returning
  NULL instead of erroring on garbage. Fixes the legacy raw layer's mixed
  NUMERIC/TEXT review-rating columns.
#}
{% macro safe_numeric(expr) -%}
    NULLIF(regexp_replace(({{ expr }})::text, '[^0-9.\-]', '', 'g'), '')::numeric
{%- endmacro %}

{% macro safe_integer(expr) -%}
    NULLIF(regexp_replace(({{ expr }})::text, '[^0-9\-]', '', 'g'), '')::integer
{%- endmacro %}

{#
  cars.com "Yes"/"No"/"None reported"/"At least 1 ..." history strings -> boolean.
  `positive_is_true`: when true, a "Yes"/"clean"-style value maps to TRUE.
#}
{% macro history_to_bool(expr, positive_tokens) -%}
    CASE
        WHEN ({{ expr }}) IS NULL THEN NULL
        {%- for tok in positive_tokens %}
        WHEN lower(({{ expr }})::text) LIKE '%{{ tok }}%' THEN TRUE
        {%- endfor %}
        ELSE FALSE
    END
{%- endmacro %}

{#
  Parse cars.com review dates. Observed format is MM/DD/YYYY; fall back to
  NULL on anything unparseable rather than failing the model.
#}
{% macro parse_review_date(expr) -%}
    CASE
        WHEN ({{ expr }}) ~ '^\d{1,2}/\d{1,2}/\d{4}$'
            THEN to_date(({{ expr }})::text, 'MM/DD/YYYY')
        ELSE NULL
    END
{%- endmacro %}
