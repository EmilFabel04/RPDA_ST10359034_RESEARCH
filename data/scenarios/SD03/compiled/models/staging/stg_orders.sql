with source as (

    select * from "ecommerce"."raw"."raw_orders"

),

renamed as (

    select
        order_id,
        customer_id,
        cast(order_date as date) as order_date,
        status,
        loaded_at
    from source

)

select * from renamed