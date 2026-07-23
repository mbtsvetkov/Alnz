-- =====================================================================================
-- Governance column dictionary — the single source of truth for the business metadata
-- injected into dbt schema YAML by tools/gen_column_meta.py.
--
-- Run this once in a Snowflake worksheet (or pipe it through the connector) to create
-- and seed the table the generator reads. The generator defaults to GOVERNANCE.COLUMN_DICTIONARY;
-- override with --table if you use a different location.
--
-- Keyed logically by (MODEL_NAME, COLUMN_NAME), matched case-insensitively against the
-- dbt model/column names. Versioned models (dim_customer v1/v2) use the base name.
-- =====================================================================================

create schema if not exists GOVERNANCE;

create or replace table GOVERNANCE.COLUMN_DICTIONARY (
    MODEL_NAME          varchar       not null,
    COLUMN_NAME         varchar       not null,
    BUSINESS_NAME       varchar,
    BUSINESS_DEFINITION varchar,
    PII                 boolean        default false,
    constraint PK_COLUMN_DICTIONARY primary key (MODEL_NAME, COLUMN_NAME)
);

insert into GOVERNANCE.COLUMN_DICTIONARY
    (MODEL_NAME, COLUMN_NAME, BUSINESS_NAME, BUSINESS_DEFINITION, PII)
values
    -- ---------------------------------------------------------------- marts: dim_customer
    ('dim_customer', 'customer_hk',    'Customer Hash Key',   'Surrogate hash key uniquely identifying a customer.', false),
    ('dim_customer', 'customer_id',    'Customer ID',         'Natural business key identifying a customer.', false),
    ('dim_customer', 'first_name',     'First Name',          'Customer given name.', true),
    ('dim_customer', 'last_name',      'Last Name',           'Customer family name.', true),
    ('dim_customer', 'email',          'Email Address',       'Primary contact email address of the customer.', true),
    ('dim_customer', 'email_domain',   'Email Domain',        'Domain portion of the customer email address.', true),
    ('dim_customer', 'country',        'Country',             'Country the customer is associated with.', false),
    ('dim_customer', 'signup_date',    'Signup Date',         'Date the customer first registered.', false),
    ('dim_customer', 'load_date',      'Load Date',           'Timestamp the sourced satellite row was loaded.', false),
    ('dim_customer', 'record_source',  'Record Source',       'Provenance / originating system of the record.', false),

    -- ----------------------------------------------------------------- marts: dim_product
    ('dim_product', 'product_hk',      'Product Hash Key',    'Surrogate hash key uniquely identifying a product.', false),
    ('dim_product', 'product_id',      'Product ID',          'Natural business key identifying a product.', false),
    ('dim_product', 'product_name',    'Product Name',        'Display name of the product.', false),
    ('dim_product', 'category',        'Product Category',    'Category the product belongs to.', false),
    ('dim_product', 'price',           'List Price',          'Catalogue list price of the product.', false),
    ('dim_product', 'load_date',       'Load Date',           'Timestamp the sourced satellite row was loaded.', false),
    ('dim_product', 'record_source',   'Record Source',       'Provenance / originating system of the record.', false),

    -- ----------------------------------------------------------------- marts: fact_orders
    ('fact_orders', 'link_customer_product_hk', 'Order Hash Key', 'Surrogate hash key uniquely identifying an order (link).', false),
    ('fact_orders', 'order_id',        'Order ID',            'Natural business key identifying an order.', false),
    ('fact_orders', 'customer_hk',     'Customer Hash Key',   'Reference to the ordering customer.', false),
    ('fact_orders', 'product_hk',      'Product Hash Key',    'Reference to the ordered product.', false),
    ('fact_orders', 'order_date',      'Order Date',          'Date the order was placed.', false),
    ('fact_orders', 'quantity',        'Quantity',            'Number of units ordered.', false),
    ('fact_orders', 'unit_price',      'Unit Price',          'Price per unit at the time of the order.', false),
    ('fact_orders', 'total_amount',    'Total Amount',        'Derived order value: quantity * unit_price.', false),
    ('fact_orders', 'load_date',       'Load Date',           'Timestamp the sourced satellite row was loaded.', false),
    ('fact_orders', 'record_source',   'Record Source',       'Provenance / originating system of the record.', false),

    -- --------------------------------------------------------------- staging (key columns)
    ('stg_customers', 'customer_id',   'Customer ID',         'Natural business key identifying a customer.', false),
    ('stg_customers', 'customer_hk',   'Customer Hash Key',   'Hash key feeding hub_customer and its satellite.', false),
    ('stg_products',  'product_id',    'Product ID',          'Natural business key identifying a product.', false),
    ('stg_products',  'product_hk',    'Product Hash Key',    'Hash key feeding hub_product and its satellite.', false),
    ('stg_orders',    'order_id',      'Order ID',            'Natural business key identifying an order.', false),

    -- ------------------------------------------------------------- raw_vault (key columns)
    ('hub_customer', 'customer_hk',    'Customer Hash Key',   'Primary hash key of the customer hub.', false),
    ('hub_customer', 'customer_id',    'Customer ID',         'Natural business key identifying a customer.', false),
    ('hub_product',  'product_hk',     'Product Hash Key',    'Primary hash key of the product hub.', false),
    ('hub_product',  'product_id',     'Product ID',          'Natural business key identifying a product.', false);
