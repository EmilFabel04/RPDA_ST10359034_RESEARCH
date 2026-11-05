

with row_count as (
    select count(*) as n_rows from "ecommerce"."main"."stg_orders"
)

select n_rows
from row_count
where n_rows < 500 or n_rows > 1000

