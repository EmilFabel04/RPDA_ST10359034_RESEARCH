

with stats as (
    select
        count(*) as total_rows,
        sum(case when email is null then 1 else 0 end) as null_rows
    from "ecommerce"."main"."stg_customers"
)

select
    total_rows,
    null_rows,
    null_rows * 1.0 / nullif(total_rows, 0) as null_rate
from stats
where null_rows * 1.0 / nullif(total_rows, 0) > 0.05

