{#- Fails if the model's row count is outside [min_rows, max_rows]. -#}
{% test row_count_between(model, min_rows, max_rows) %}

with row_count as (
    select count(*) as n_rows from {{ model }}
)

select n_rows
from row_count
where n_rows < {{ min_rows }} or n_rows > {{ max_rows }}

{% endtest %}
