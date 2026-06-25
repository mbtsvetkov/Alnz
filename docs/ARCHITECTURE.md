# Architecture, Best Practices & Developer Guide

This document covers the "explain it" parts of the assignment: architectural concepts in
plain language, a development pathway for junior/medior engineers, how to set up the
architecture for a team, and how to set up the YAML files.

---

## 1. Architectural concepts (simplified)

### Why Data Vault?
Data Vault is a way to model a warehouse so it is **auditable, parallel-loadable, and
resilient to change**. Instead of one big table that you overwrite, you split data into
three small, single-purpose building blocks and only ever **insert** (never update/delete).
That gives you full history "for free" and lets many sources load at once without locking
each other.

### The three building blocks

| Block | Answers | Holds | Analogy |
|---|---|---|---|
| **Hub** | *What things exist?* | One row per unique **business key** + its hash key | A list of distinct IDs (every customer that ever existed) |
| **Link** | *What is related to what?* | The hash keys of the hubs it connects | A join table (which customer bought which product) |
| **Satellite** | *What do we know about it, over time?* | Descriptive attributes + a **hashdiff** + load_date | A history log of attribute changes |

- **Hash keys** (`*_hk`): an MD5 of the standardised business key. They replace
  integer surrogate keys so hubs/links/sats can be **loaded independently and in parallel**
  (you can compute a customer's hash without looking anything up).
- **Hashdiff**: an MD5 of a satellite's descriptive columns. On each load we compare it to
  the current record; if it changed, we insert a new version — this is how history is kept
  **insert-only**.
- **load_date / record_source**: audit metadata on every row — *when* it arrived and *where*
  it came from.

### The layered "Vault" architecture (where this fits)
```
Sources ──► Staging ──► RAW VAULT ──► Business Vault ──► Information Marts (star schemas)
            (clean)     (hubs/links/  (derived rules,    (what analysts/BI query)
                         sats; this    soft business
                         project)      logic)
```
- **Raw Vault** (this project): a faithful, hashed, historised copy of source data. No
  business logic — just structure.
- **Business Vault**: optional derived structures (computed satellites, point-in-time
  tables) that apply business rules.
- **Information Marts**: friendly dimensional models (facts/dims) built on top for reporting.

This project implements **Staging + Raw Vault**, which is the foundation everything else
builds on.

---

## 2. Development pathway for junior / medior engineers

A concrete order to learn and contribute, lowest risk first:

1. **Seeds + staging + tests (junior start).** Add a CSV, write a `stg_` view that casts
   columns and adds metadata, add `unique`/`not_null` tests. Learn `ref()`, `dbt run -s`,
   `dbt test -s`. *You cannot break the vault from here.*
2. **Hubs.** Understand business keys and hash keys. Write a hub: `select distinct` key +
   `generate_hashkey(...)`. Learn why hubs are insert-only.
3. **Links.** Connect two hubs; understand grain (transactional vs. relationship) and the
   `relationships` test.
4. **Satellites.** Learn hashdiff change detection and the insert-only history pattern.
5. **Macros (medior).** Factor repeated SQL into macros (as `generate_hashkey` /
   `generate_hashdiff` here). Learn Jinja, `is_incremental()`.
6. **Incremental loading & Business Vault (medior).** Reason about idempotency, late-arriving
   data, and PIT/bridge tables.
7. **CI & operations (medior→senior).** Slim CI (`dbt build --select state:modified+`),
   environments, freshness, exposures, deployment jobs.

> Rule of thumb: **juniors own staging + tests; mediors own vault models + macros + CI.**

---

## 3. Setting up the architecture for a team

### Folder & naming conventions (the hierarchy)
```
models/
  staging/      one stg_ model per source table; views; light cleaning only
  raw_vault/    hub_ / link_ / sat_ models; insert-only; no business logic
  business_vault/   (future) derived sats, PIT, bridge tables
  marts/        (future) fact_ / dim_ models for BI
```
- **One prefix = one purpose:** `stg_`, `hub_`, `link_`, `sat_`, `fact_`, `dim_`.
- **One YAML per folder** (`_staging.yml`, `_raw_vault.yml`) describing + testing the models
  in it. The leading underscore sorts it to the top.
- **Hash columns** end in `_hk`; **hashdiffs** end in `_hashdiff`.

### Coding best practices
- **Insert-only** in the vault — never `update`/`delete`; history is sacred.
- **Standardise before hashing** (trim/upper/null-handling) so keys are deterministic — keep
  this in ONE macro so every model hashes identically.
- **CTEs over subqueries**, one transformation per CTE, `select *` only from the final CTE.
- **Test every key**: `unique` + `not_null` on hub/link primary hash keys; `relationships`
  from links/sats back to their hubs.
- **No hard-coded schemas/tables** — always `ref()` / `source()`.
- **Schema-per-layer in production** (see below) so permissions and lineage are clean.

### Environments
- **dev**: each developer builds into a personal schema (dbt Cloud development credentials),
  e.g. `DBT_<NAME>`.
- **prod**: a dedicated service account + schema, run by a scheduled dbt Cloud **job**
  (`dbt build`), with Slim CI on pull requests (`dbt build --select state:modified+`).
- **Reviews**: every change via PR; CI must be green (`dbt build` + tests) before merge.

### Schema-per-layer (production pattern)
This demo uses a single dev schema with name-prefixed models for easy spot-checking. In
production, separate layers into schemas via `dbt_project.yml`:
```yaml
models:
  alnz_data_vault:
    staging:   { +schema: staging }
    raw_vault: { +schema: raw_vault }
seeds:
  alnz_data_vault: { +schema: raw }
```
dbt appends these to the target schema (e.g. `ANALYTICS_RAW_VAULT`), giving clean separation
and per-layer access control.

---

## 4. How to set up the YAML files

There are three distinct kinds of YAML — don't confuse them:

### a) `dbt_project.yml` — the project (one per repo)
Defines the project name, file paths, and **configuration defaults** (materializations) by
folder. Set behaviour broadly here, override per-model with `{{ config(...) }}`.
```yaml
name: 'alnz_data_vault'
profile: 'default'          # in dbt Cloud the connection is in the UI; this is a placeholder
models:
  alnz_data_vault:
    staging:   { +materialized: view }
    raw_vault: { +materialized: incremental }
```

### b) `profiles.yml` — the connection (NOT in the repo)
Only for **local dbt Core**. dbt Cloud manages the connection in its UI, so this repo has no
`profiles.yml` and no secrets. If you run locally, create `~/.dbt/profiles.yml`:
```yaml
default:
  target: dev
  outputs:
    dev:
      type: snowflake
      account: "<account_identifier>"
      user: "<user>"
      password: "{{ env_var('DBT_SNOWFLAKE_PASSWORD') }}"   # secret via env var, never hard-coded
      role: "<role>"
      warehouse: "<warehouse>"
      database: "<database>"
      schema: "<your_dev_schema>"
      threads: 4
```

### c) `_*.yml` model/property files — docs + tests (one per folder)
This is where you **document** and **test**. Structure:
```yaml
version: 2
models:                       # (or `seeds:` / `sources:`)
  - name: hub_customer
    description: "One row per unique customer business key."
    columns:
      - name: customer_hk
        description: "Primary hash key."
        data_tests: [unique, not_null]          # column-level generic tests
    data_tests:                                  # model-level tests (multi-column)
      - dbt_utils.unique_combination_of_columns:
          combination_of_columns: [customer_hk, load_date]
```
Conventions used in this project:
- **`description:`** on every model and every key column — these power `dbt docs`.
- **Column-level tests** for single-column rules (`unique`, `not_null`, `relationships`).
- **Model-level `data_tests:`** for multi-column rules (composite uniqueness).
- **Sources vs seeds:** real upstream tables go under a `sources:` block and are referenced
  with `source()`; here the sample data is seeds, referenced with `ref()` and documented in
  `seeds/_seeds.yml`.

> Tip: `data_tests:` is the current dbt key (1.8+). Older projects use `tests:` — both work,
> but prefer `data_tests:` going forward.
