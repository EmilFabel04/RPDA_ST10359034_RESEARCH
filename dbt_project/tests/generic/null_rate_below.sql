{#- Fails if the share of NULLs in the column is above max_rate (0-1). -#}
{% test null_rate_below(model, column_name, max_rate) %}

with stats as (
    select
        count(*) as total_rows,
        sum(case when {{ column_name }} is null then 1 else 0 end) as null_rows
    from {{ model }}
)

select
    total_rows,
    null_rows,
    null_rows * 1.0 / nullif(total_rows, 0) as null_rate
from stats
where null_rows * 1.0 / nullif(total_rows, 0) > {{ max_rate }}

{% endtest %}
