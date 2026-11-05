with source as (

    select * from "ecommerce"."raw"."raw_customers"

),

renamed as (

    select
        customer_id,
        first_name,
        last_name,
        lower(email) as email,
        upper(country) as country_code,
        cast(created_at as timestamp) as created_at,
        loaded_at
    from source

)

select * from renamed