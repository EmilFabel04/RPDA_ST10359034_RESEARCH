

with model_rows as (
    select count(*) as n_rows from "ecommerce"."main"."fct_orders"
),

compare_rows as (
    select count(*) as n_rows from "ecommerce"."main"."stg_orders"
)

select
    model_rows.n_rows as model_rows,
    compare_rows.n_rows as compare_model_rows
from model_rows
cross join compare_rows
where model_rows.n_rows != compare_rows.n_rows

