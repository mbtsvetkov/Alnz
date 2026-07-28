-- =====================================================================================
-- OPTIONAL: Snowflake table for the `--source snowflake` path.
--
-- Mirrors the Excel column-inventory so the generator can read from a table instead of
-- the .xlsx later. Column NAMES here must match your config source.mapping / meta_fields
-- (the loader reads the table with `select *` and maps by header name, case-sensitive to
-- the mapping values). Adjust names/types to your governance table if it already exists.
-- =====================================================================================

create schema if not exists GOVERNANCE;

create or replace table GOVERNANCE.COLUMN_INVENTORY (
    prev_model_name          varchar,
    cpnc_model_name          varchar,      -- mapped: model_name
    prev_column_name         varchar,
    cpnc_column_name         varchar,      -- mapped: column_name
    prev_column_description  varchar,
    cpnc_column_description  varchar,      -- mapped: description
    prev_data_type           varchar,
    cpnc_data_type           varchar,      -- mapped: data_type
    business_name            varchar,      -- meta
    business_definition      varchar,      -- meta
    pii                      boolean,      -- meta
    "Test"                   varchar,      -- workflow (not meta by default)
    remark                   varchar,      -- meta (optional)
    investication            varchar       -- workflow (not meta by default)
);

-- Example row:
insert into GOVERNANCE.COLUMN_INVENTORY
    (cpnc_model_name, cpnc_column_name, cpnc_column_description, cpnc_data_type,
     business_name, business_definition, pii)
values
    ('bv_cpnc_load_date', 'CPNC_REPORTING_TS', 'Column cpnc reporting ts.', 'TIMESTAMP',
     'Reporting Timestamp', 'Timestamp the record was reported.', false);
