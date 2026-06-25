-- Custom singular test: referential integrity of the link.
--
-- A "data vault sin" is an orphan link — a link row whose customer_hk or product_hk
-- does not exist in the corresponding hub. The `relationships` tests in _raw_vault.yml
-- already cover each foreign key individually; this test asserts it in a single,
-- readable query and is a good template for more complex business-rule tests.
--
-- A dbt test PASSES when it returns ZERO rows. Any row returned here is an orphan link
-- and will fail the test.

select
    l.link_customer_product_hk,
    l.customer_hk,
    l.product_hk
from {{ ref('link_customer_product') }} l
left join {{ ref('hub_customer') }} hc on l.customer_hk = hc.customer_hk
left join {{ ref('hub_product') }}  hp on l.product_hk  = hp.product_hk
where hc.customer_hk is null
   or hp.product_hk is null
