with orders as (

    select * from "ecommerce"."main"."stg_orders"

),

payments as (

    select * from "ecommerce"."main"."stg_payments"

),

final as (

    select
        orders.order_id,
        orders.customer_id,
        orders.order_date,
        orders.status,
        case when payments.payment_method = 'credit_card' then payments.amount else 0 end as credit_card_amount,
        case when payments.payment_method = 'bank_transfer' then payments.amount else 0 end as bank_transfer_amount,
        case when payments.payment_method = 'voucher' then payments.amount else 0 end as voucher_amount,
        case when payments.payment_method = 'gift_card' then payments.amount else 0 end as gift_card_amount,
        coalesce(payments.amount, 0) as amount
    from orders
    left join payments on orders.order_id = payments.order_id

)

select * from final