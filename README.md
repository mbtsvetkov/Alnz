# Data Vault on Snowflake with dbt

This project is a small but complete Data Vault 2.0 build. It takes some sample e-commerce
data (customers, products and the orders that connect them), lands it in a raw layer, and
then models it into Hubs, Links and Satellites using dbt running on Snowflake through dbt
Cloud. Along the way it covers the things you'd expect in a real project: tests, documentation
and a lineage graph, plus notes on how the whole thing was wired together.

I built it for the practical assignment ("build a data transformation pipeline using dbt to
implement a Data Vault model"), but I tried to keep it close to how I'd actually structure a
starter project for a team rather than something throwaway.

If you just want to run it, jump to [Running the project](#running-the-project). If you're
setting up the tooling from nothing, start with [How this was set up](#how-this-was-set-up).


## What's in here

The Data Vault itself lives in `models/raw_vault/`:

- Two hubs, `hub_customer` and `hub_product`, each holding the unique business keys.
- One link, `link_customer_product`, connecting the two hubs. It's modelled at order grain,
  so there's one link row per order (two orders for the same customer and product are two
  distinct rows, which is what you want for a transaction).
- Three satellites for the descriptive attributes: `sat_customer_details`,
  `sat_product_details`, and `sat_order_details` hanging off the link.

Everything upstream of that is in `models/staging/` (light cleaning and the hash logic), and
the sample data is in `seeds/` as plain CSV files. There are a couple of macros in `macros/`
that handle the hashing so the same rules are applied everywhere.

On top of the vault, `models/marts/` holds the **public, consumer-facing interface** —
`dim_customer` (versioned v1/v2), `dim_product` and `fact_orders` — governed by enforced
**data contracts** (column types, constraints, versioning, access). The quality bar per layer
and the contract policy are written up in
[docs/DATA_QUALITY.md](docs/DATA_QUALITY.md).

```
seeds/*.csv  ->  dbt seed  ->  raw tables  ->  staging views  ->  hubs / link / satellites  ->  marts (contracted)
```

The shape of the vault:

```
        hub_customer                         hub_product
             |                                    |
   sat_customer_details                  sat_product_details
             |                                    |
             +----------> link_customer_product <-+
                                  |
                          sat_order_details
```


## Project layout

```
alnz_data_vault/
  dbt_project.yml          project config and the materialization defaults
  packages.yml             one dependency, dbt_utils
  seeds/                   sample raw data as CSV, documented in _seeds.yml
  macros/
    generate_hashkey.sql   builds a hash key from business keys
    generate_hashdiff.sql  builds a hashdiff for satellite change detection
  models/
    staging/               cleans and standardises the raw data, adds the hashes (views)
    raw_vault/             the hubs, link and satellites (insert-only incremental tables)
    marts/                 public, contracted dim_/fact_ interface (versioned)
    exposures.yml          declared downstream consumers (BI dashboard)
  tests/
    assert_no_orphan_links.sql   a custom test for referential integrity
    assert_test_coverage.sql     the per-layer minimum-bar coverage gate
  docs/
    ARCHITECTURE.md        the concepts, team setup, dev pathway and a YAML guide
    DATA_QUALITY.md        the data-quality + data-contract framework playbook
    TEST_RESULTS.md        the test list, run logs and a debugging walkthrough
```


## How this was set up

This is the part that usually isn't written down, so here's the actual path from nothing to a
working pipeline. The order matters: Snowflake first (somewhere to put data), then dbt Cloud
(the tool), then Git (where the code lives).

### 1. Snowflake

I used a Snowflake account with a database to build into and a warehouse to run the queries.
If you're starting fresh, Snowflake offers a 30-day free trial at
[signup.snowflake.com](https://signup.snowflake.com) that works the same way. Either way you
need four things to hand off to dbt later: the **account identifier**, a **user** and
**password**, a **warehouse**, and a **database** plus a **role** that can create objects.

A minimal bootstrap in a Snowflake worksheet looks like this:

```sql
create warehouse if not exists dbt_wh
  warehouse_size = xsmall
  auto_suspend = 60
  auto_resume = true;

create database if not exists revelator_all;   -- or whatever you want to build into
```

dbt creates its own schemas inside that database, so you don't need to pre-create them.

### 2. dbt Cloud

dbt Cloud has a free Developer plan that's fine for a single developer, which is all this
needs. To get going:

1. Sign up at [getdbt.com](https://www.getdbt.com/) and create the free account.
2. Create a new **Project**. dbt asks for two connections during setup: the data warehouse
   and the code repository.
3. For the warehouse, pick **Snowflake** and paste in the details from step 1 (account, user,
   password, role, warehouse, database). dbt Cloud stores these for you, which is why there's
   no `profiles.yml` and no credentials anywhere in this repo. Hit **Test connection** to
   confirm it can reach Snowflake before moving on.
4. dbt Cloud keeps connection-level settings separate from your personal **development
   credentials** (your own user and password used by the IDE). If "Test connection" ever
   fails with an authentication error after it previously worked, it's almost always the dev
   credentials password needing to be re-entered.

### 3. Linking the GitHub repo

The dbt project is really just the files in a Git repo, so dbt Cloud needs to be pointed at
one. I created an empty repo on GitHub and connected it during project setup.

The smoothest option is the native GitHub integration (the dbt Cloud GitHub app), which
handles authentication for you. If instead you connect by Git URL, dbt Cloud generates a
**deploy key** that you have to add yourself: copy it from the project's repository settings,
then in GitHub go to **Settings → Deploy keys → Add deploy key**, paste it, and tick **Allow
write access** (dbt Cloud needs to commit back). Skipping the write-access box is what causes
the `Permission denied (publickey)` error when the IDE tries to clone.

When dbt Cloud first opens the repo it offers to initialise a starter project, which drops in
a default `dbt_project.yml` and an example model folder. I cleared that out and replaced it
with the structure above.

### 4. Putting it together

Once Snowflake, dbt Cloud and GitHub are all linked, the loop is just: edit files, commit and
push, then run dbt commands in the dbt Cloud IDE. Each run reads from your Git branch and
executes against your Snowflake warehouse.


## Running the project

In the dbt Cloud IDE, run these in order:

```bash
dbt deps      # install the dbt_utils package (do this first)
dbt seed      # load the three CSVs into raw tables in Snowflake
dbt run       # build the staging views and then the vault tables
dbt test      # run the 23 data-quality tests
```

Or do the lot in one go with `dbt build`, which seeds, runs and tests in dependency order.

To produce the documentation and lineage graph:

```bash
dbt docs generate
```

then click **View Docs** in dbt Cloud and open the lineage view.

A note on the incremental models: the vault tables are insert-only, so the first run does a
full build and the `{% if is_incremental() %}` logic only kicks in from the second run
onward. That's expected.

### Running it locally instead

If you'd rather use dbt Core on your machine, install the adapter with
`pip install dbt-snowflake`, create a `~/.dbt/profiles.yml` with a Snowflake profile (there's
a worked example in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md), including the recommended
way to keep the password in an environment variable), and then run the same commands.


## Checking the results

After a build, you can sanity-check the output in a Snowflake worksheet. Swap `<dev_schema>`
for your dbt development schema:

```sql
-- each hub should hold only unique keys
select count(*), count(distinct customer_hk) from <dev_schema>.hub_customer;  -- 8, 8
select count(*), count(distinct product_hk)  from <dev_schema>.hub_product;   -- 6, 6

-- one link row per order
select count(*) from <dev_schema>.link_customer_product;                      -- 15

-- the satellites carry the descriptive detail
select * from <dev_schema>.sat_customer_details limit 5;
```


## More detail

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) explains the Data Vault concepts in plain
  terms, suggests how to grow this into a team setup, sketches a learning path for junior and
  mid-level engineers, and walks through how the YAML files are organised.
- [docs/DATA_QUALITY.md](docs/DATA_QUALITY.md) is the data-quality & data-contract framework:
  the per-layer minimum test bar, severity conventions, the coverage gate, and the enforced
  contracts / versioning / access governance on the marts interface.
- [docs/TEST_RESULTS.md](docs/TEST_RESULTS.md) lists the tests, holds the run logs, and
  includes a short debugging walkthrough where a test is deliberately broken and then fixed.
