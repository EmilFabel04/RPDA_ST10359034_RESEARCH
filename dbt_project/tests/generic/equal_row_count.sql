{#- Fails if the model and compare_model have different row counts (same grain). -#}
{% test equal_row_count(model, compare_model) %}

with model_rows as (
    select count(*) as n_rows from {{ model }}
),

compare_rows as (
    select count(*) as n_rows from {{ compare_model }}
)

select
    model_rows.n_rows as model_rows,
    compare_rows.n_rows as compare_model_rows
from model_rows
cross join compare_rows
where model_rows.n_rows != compare_rows.n_rows

{% endtest %}
