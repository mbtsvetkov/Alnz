# Data Vault on Snowflake with dbt — `alnz_data_vault`

A compact, production-shaped **Data Vault 2.0** implementation built with **dbt** on
**Snowflake**, run via **dbt Cloud**. It loads sample e-commerce data into a raw layer and
transforms it into Hubs, Links, and Satellites, with tests, documentation, and logging.

> Built for the practical assignment: *"Build a data transformation pipeline using dbt to
> implement a Data Vault model."*

---

## 1. What this project delivers (mapped to the brief)

| Requirement | Where it lives |
|---|---|
| **2+ Hubs** | `models/raw_vault/hub_customer.sql`, `hub_product.sql` |
| **1+ Link** | `models/raw_vault/link_customer_product.sql` |
| **Satellites per hub** | `sat_customer_details`, `sat_product_details` (+ `sat_order_details` on the link) |
| **Load sample data → raw layer** | `seeds/*.csv` loaded by `dbt seed` |
| **Raw → Data Vault transforms** | `models/staging/*` then `models/raw_vault/*` |
| **Built-in + custom tests** | `_seeds.yml`, `_staging.yml`, `_raw_vault.yml` (generic) + `tests/assert_no_orphan_links.sql` (custom) |
| **Documentation + lineage** | YAML `description`s + `dbt docs generate` (DAG) + this README + [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) |
| **Logging & debugging** | dbt run/test logs + [docs/TEST_RESULTS.md](docs/TEST_RESULTS.md) (incl. a deliberate break→fix) |
| **Architecture / team / pathway / YAML guidance** | [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) |

---

## 2. Project structure

```
alnz_data_vault/
├─ dbt_project.yml            # project config + materialization defaults
├─ packages.yml              # dbt_utils dependency
├─ seeds/                    # sample RAW data (CSV) + tests/docs
│  ├─ raw_customers.csv
│  ├─ raw_products.csv
│  ├─ raw_orders.csv
│  └─ _seeds.yml
├─ macros/                   # reusable Data Vault logic
│  ├─ generate_hashkey.sql   # MD5 hash key from business keys
│  └─ generate_hashdiff.sql  # MD5 hashdiff for satellite change detection
├─ models/
│  ├─ staging/               # clean + standardise + attach hashes (views)
│  │  ├─ stg_customers.sql
│  │  ├─ stg_products.sql
│  │  ├─ stg_orders.sql
│  │  └─ _staging.yml
│  └─ raw_vault/             # the Data Vault (insert-only incremental tables)
│     ├─ hub_customer.sql
│     ├─ hub_product.sql
│     ├─ link_customer_product.sql
│     ├─ sat_customer_details.sql
│     ├─ sat_product_details.sql
│     ├─ sat_order_details.sql
│     └─ _raw_vault.yml
├─ tests/
│  └─ assert_no_orphan_links.sql   # custom singular test
└─ docs/
   ├─ ARCHITECTURE.md        # concepts, team setup, dev pathway, YAML guide
   └─ TEST_RESULTS.md        # test summary + debugging walkthrough + logs
```

---

## 3. Data flow

```
seeds/*.csv  ──dbt seed──►  RAW tables  ──dbt run (staging)──►  stg_* views  ──dbt run (raw_vault)──►  Hubs / Link / Satellites
```

```
                 ┌─────────────┐                 ┌─────────────┐
                 │ hub_customer│                 │ hub_product │
                 └──────┬──────┘                 └──────┬──────┘
        sat_customer_details                    sat_product_details
                        │                               │
                        └────────► link_customer_product ◄────────┘
                                          │
                                   sat_order_details
```

The order is modelled as a **transactional link** (one link row per order). Two orders for
the same customer + product produce two link rows (e.g. orders `1001` and `1010`), which is
correct for transaction grain.

---

## 4. How to run it (dbt Cloud)

The Snowflake connection is configured in **dbt Cloud** (Account settings → Connection), so
there are **no credentials in this repo**. In the dbt Cloud IDE, run in order:

```bash
dbt deps      # install dbt_utils
dbt seed      # load the 3 CSVs into RAW tables in Snowflake
dbt run       # build staging views + the Data Vault tables
dbt test      # run all generic + custom tests
dbt docs generate   # then click "View Docs" to see the lineage graph
```

Or run everything (seed + run + test) in one shot:

```bash
dbt build
```

### Running locally with dbt Core (optional)
1. `pip install dbt-snowflake`
2. Create `~/.dbt/profiles.yml` with a `default:` profile of `type: snowflake` (see
   [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the YAML and the recommended
   `env_var()` pattern for secrets).
3. Same commands as above.

---

## 5. Verifying the result in Snowflake

After `dbt build`, spot-check in a worksheet (replace `<DEV_SCHEMA>` with your dbt Cloud
development schema):

```sql
-- hubs hold unique keys
select count(*), count(distinct customer_hk) from <DEV_SCHEMA>.hub_customer;   -- 8, 8
select count(*), count(distinct product_hk)  from <DEV_SCHEMA>.hub_product;    -- 6, 6

-- link has one row per order (15) and no orphans
select count(*) from <DEV_SCHEMA>.link_customer_product;                       -- 15

-- satellites carry the descriptive attributes
select * from <DEV_SCHEMA>.sat_customer_details limit 5;
```

---

## 6. Tests & logs

See **[docs/TEST_RESULTS.md](docs/TEST_RESULTS.md)** for the full test inventory, the run
summary, and a worked **debugging walkthrough** (deliberately breaking a test and fixing it).

## 7. Concepts, team setup, dev pathway & YAML guide

See **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)**.
