with customers as (

    select * from "ecommerce"."main"."stg_customers"

),

orders as (

    select * from "ecommerce"."main"."stg_orders"

),

payments as (

    select * from "ecommerce"."main"."stg_payments"

),

customer_orders as (

    select
        customer_id,
        min(order_date) as first_order_date,
        max(order_date) as most_recent_order_date,
        count(order_id) as number_of_orders
    from orders
    group by customer_id

),

customer_payments as (

    select
        orders.customer_id,
        sum(payments.amount) as lifetime_value
    from payments
    inner join orders on payments.order_id = orders.order_id
    where orders.status != 'cancelled'
    group by orders.customer_id

),

final as (

    select
        customers.customer_id,
        customers.first_name,
        customers.last_name,
        customers.email,
        customers.country_code,
        customers.created_at,
        customer_orders.first_order_date,
        customer_orders.most_recent_order_date,
        coalesce(customer_orders.number_of_orders, 0) as number_of_orders,
        coalesce(customer_payments.lifetime_value, 0) as lifetime_value
    from customers
    left join customer_orders on customers.customer_id = customer_orders.customer_id
    left join customer_payments on customers.customer_id = customer_payments.customer_id
    -- marketing dashboard only covers launch markets (MKT-12)
    where customers.country_code in ('ZA', 'GB', 'US')

)

select * from final