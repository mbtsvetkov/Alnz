# Architecture & developer notes

This covers the "explain it" side of the assignment: what Data Vault actually is, how I'd
grow this into something a team works on, a rough learning path for people newer to it, and
how the YAML files are organised. I've kept it short on purpose.

## What Data Vault is, in plain terms

Data Vault is a way of modelling a warehouse so it stays auditable and easy to load from many
sources at once. Instead of one wide table you keep overwriting, you split everything into
three small pieces and only ever insert into them, never update or delete. You get full
history for free, and different sources can load in parallel without stepping on each other.

The three pieces:

- **Hubs** answer "what things exist". One row per unique business key (every customer that
  ever existed), plus a hash of that key and a bit of audit metadata. Nothing descriptive.
- **Links** answer "what's related to what". They hold the hash keys of the hubs they
  connect. Here, `link_customer_product` records that a customer ordered a product.
- **Satellites** answer "what do we know, and how has it changed". Descriptive attributes
  with history, hanging off a hub or a link.

Two ideas make it work. **Hash keys** (`*_hk`) are just an MD5 of the standardised business
key, used instead of incrementing integers so each table can be built independently. And a
**hashdiff** is an MD5 of a satellite's attributes; when it changes, you know something
changed and you insert a new version. Every row also carries a `load_date` and a
`record_source` so you always know when data arrived and where from.

Where this sits in the bigger picture: sources land in staging, staging feeds the **raw
vault** (the hubs, links and sats in this project), and on top of that you'd usually build a
business vault for derived logic and then friendly star-schema marts for reporting. This
project does staging plus raw vault, which is the foundation everything else stands on.

## Growing this into a team setup

The folder structure is the convention. Each layer gets its own folder and a single
`_*.yml` per folder for docs and tests:

```
models/
  staging/         one stg_ model per source table, materialized as views
  raw_vault/       hub_ / link_ / sat_ models, insert-only
  business_vault/  (later) derived satellites, point-in-time and bridge tables
  marts/           (later) fact_ / dim_ models for BI
```

The naming prefix tells you what a model is at a glance: `stg_`, `hub_`, `link_`, `sat_`,
and later `fact_` / `dim_`. Hash columns end in `_hk`, hashdiffs in `_hashdiff`.

A few practices worth holding the line on. Keep the vault insert-only; history is the whole
point. Do all your key standardisation (trim, upper, null handling) in one macro so every
model hashes identically, which is why the hashing lives in `macros/` here rather than being
copy-pasted. Always reference other models with `ref()` so dbt knows the build order, and
never hardcode a schema or table name. Test every key: unique and not_null on the primary
hash keys, and relationships from links and satellites back to their hubs.

For environments, each developer builds into their own schema (dbt Cloud handles this through
development credentials), and production runs from a scheduled job into a dedicated schema.
Changes go through pull requests with CI running `dbt build` before anything merges. As the
project grows, Slim CI (`dbt build --select state:modified+`) keeps that fast by only
building what changed.

This demo keeps everything in one schema with name-prefixed models so it's easy to look at.
In production I'd split the layers into their own schemas, which is a small change in
`dbt_project.yml`:

```yaml
models:
  alnz_data_vault:
    staging:   { +schema: staging }
    raw_vault: { +schema: raw_vault }
```

dbt appends those to your target schema, so you end up with clean, separately-permissioned
layers.

## A learning path for newer engineers

Roughly the order I'd hand work out, safest first:

1. Start in staging and tests. Add a CSV, write a `stg_` view that casts columns and adds
   metadata, attach `unique` and `not_null` tests. This teaches `ref()`, `dbt run -s` and
   `dbt test -s`, and you can't break the vault from here.
2. Move to hubs. Understand business keys versus hash keys, and why hubs only ever grow.
3. Then links, where grain matters (is it one row per relationship, or per transaction?) and
   the `relationships` test comes in.
4. Then satellites, which is where hashdiff change detection and insert-only history click.
5. Once the patterns are familiar, factor repeated SQL into macros (Jinja, `is_incremental()`)
   and start reasoning about incremental loads and late-arriving data.
6. From there it's CI, environments, and the business vault.

A simple way to split ownership: juniors own staging and tests, mediors own the vault models,
macros and CI.

## How the YAML is set up

There are three different kinds of YAML in a dbt project and it's easy to mix them up.

`dbt_project.yml` is the project file, one per repo. It sets paths and the default
materializations per folder (views for staging, incremental for the vault). Set the broad
behaviour here and override per-model with a `{{ config() }}` block when needed.

`profiles.yml` is the connection, and it is **not** in this repo. dbt Cloud stores the
Snowflake connection in its UI, so there are no credentials in the code. You only need this
file if you run dbt Core locally, in which case it lives in `~/.dbt/` and looks like:

```yaml
default:
  target: dev
  outputs:
    dev:
      type: snowflake
      account: "<account_identifier>"
      user: "<user>"
      password: "{{ env_var('DBT_SNOWFLAKE_PASSWORD') }}"   # keep secrets in an env var
      role: "<role>"
      warehouse: "<warehouse>"
      database: "<database>"
      schema: "<your_dev_schema>"
      threads: 4
```

The `_*.yml` files (one per model folder) are where you document and test. A column gets a
`description` and a list of tests; multi-column tests sit at the model level. For example:

```yaml
models:
  - name: hub_customer
    description: "One row per unique customer business key."
    columns:
      - name: customer_hk
        description: "Primary hash key."
        data_tests: [unique, not_null]
```

Two things to know on this project specifically. It's running the dbt 2.0 / Fusion preview,
which wants generic-test arguments nested under an `arguments:` key (so `relationships` puts
its `to` and `field` there). And it uses the current `data_tests:` key rather than the older
`tests:` — both work, but `data_tests:` is the one to use going forward. Real upstream tables
would be declared in a `sources:` block and read with `source()`; here the sample data is
seeds, read with `ref()` and documented in `seeds/_seeds.yml`.
