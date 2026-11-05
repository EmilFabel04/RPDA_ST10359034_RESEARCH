with source as (

    select * from "ecommerce"."raw"."raw_payments"

),

renamed as (

    select
        payment_id,
        order_id,
        payment_method,
        -- source stores integer cents; convert to currency units
        cast(amount as decimal(18, 2)) / 100 as amount,
        loaded_at
    from source

)

select * from renamed