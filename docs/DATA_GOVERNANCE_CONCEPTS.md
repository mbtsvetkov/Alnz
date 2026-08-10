# Data Governance Concepts — Contracts, Data Quality & Model Access

A **capabilities menu**: what governance features dbt gives you, what each one looks like in YAML, and which file it goes in. This is a reference for deciding *what to apply per model* — it does not prescribe a rollout. For this project's applied rules see [DATA_QUALITY.md](DATA_QUALITY.md); for the business case see [PROPOSAL-data-quality-and-contracts.md](PROPOSAL-data-quality-and-contracts.md).

There are three independent levers, and you can turn each on per model:

| Lever | Question it answers | Turn it on with |
|---|---|---|
| **Data contracts** | "Is this model's shape stable and promised?" | `contract:`, `columns:` + `data_type`, `constraints:`, `versions:` |
| **Data quality** | "Is the data inside it correct?" | `data_tests:`, freshness, `unit_tests:`, singular tests |
| **Model access** | "Who is allowed to depend on it?" | `access:`, `groups:`, exposures |

**Where config lives.** Two places, and they compose:

- **Project-wide defaults / toggles** → [dbt_project.yml](../dbt_project.yml). Set a behaviour once for a whole folder (e.g. "all marts are public and contracted").
- **Per-model detail** → each folder's `_<folder>.yml` (e.g. [models/marts/_marts.yml](../models/marts/_marts.yml)). Declare the columns, tests, constraints, and versions of individual models here.

> This project runs on **Snowflake via dbt Cloud** using the **dbt 2.0 / Fusion preview**. That means: use `data_tests:` (not the legacy `tests:` key), nest generic-test arguments under `arguments:`, and expect Snowflake to enforce only some constraint types (noted per section below).

---

## 1. Data contracts

**What it is.** A contract is an enforced promise about a model's *output shape*. You declare every column and its `data_type`; at build time dbt compares the compiled SQL to that declaration and **fails the build if they drift**. A consumer downstream can rely on the columns and types being exactly what was promised.

What a violation looks like — you rename or retype a column and the build stops before anything ships:

```
Compilation Error in model fact_orders
  This model has an enforced contract that failed.
  | column       | model output | contract      | reason             |
  | total_amount | FLOAT        | NUMBER(38,2)  | data type mismatch |
```

### What you can use

- **`contract: {enforced: true}`** — switches enforcement on. Requires a full `columns:` list with a `data_type` on every column.
- **`constraints:`** — declare `primary_key`, `foreign_key`, `not_null`, `check` on columns.
- **Versioning** — ship `v1` and `v2` of the same model side by side (`versions:`, `latest_version:`), give an old version a `deprecation_date:`, and `include`/`exclude` columns per version. Additive changes = minor; removing/renaming/narrowing a column = breaking (bump the version).

### In YAML

Enforce it for a whole folder once, in [dbt_project.yml](../dbt_project.yml):

```yaml
models:
  alnz_data_vault:
    marts:
      +materialized: table
      +access: public
      +contract:
        enforced: true
```

Or decide it **per model** rather than per folder: the [dbt_yaml_generator](../procs/cpnc/dbt_yaml_generator/) reads an `Is_Data_Contract_Enabled` flag from a model-level sheet of the inventory workbook and writes `config: contract: {enforced: true|false}` into each `<model>.yml`. It is a deliberately separate flow — `--apply-data-contracts` alongside normal generation, or `--contracts-only` to touch nothing but that key — so contracts are never enabled as a side effect of regenerating columns.

Then declare each model's shape in [models/marts/_marts.yml](../models/marts/_marts.yml). Note `data_type` on every column and the `constraints:` block:

```yaml
models:
  - name: fact_orders
    description: "One row per order. Public, contracted interface."
    columns:
      - name: link_customer_product_hk
        data_type: varchar
        constraints:
          - type: primary_key
          - type: not_null
      - name: customer_hk
        data_type: varchar
        constraints:
          - type: not_null
          - type: foreign_key
            to: ref('dim_customer')
            to_columns: [customer_hk]
      - name: total_amount
        data_type: number(38,2)
```

Versioning — v1 predates a column, v2 adds it. Consumers of v1 have until the `deprecation_date` to migrate:

```yaml
models:
  - name: dim_customer
    latest_version: 2
    columns:
      - name: email_domain
        data_type: varchar        # added in v2
      # ... all other columns ...
    versions:
      - v: 1
        deprecation_date: 2026-12-31
        columns:
          - include: all
            exclude: [email_domain]   # v1 never had it
      - v: 2
        columns:
          - include: all              # v2 = everything (additive change)
```

### Snowflake note

Snowflake enforces `not_null` only. `primary_key` / `foreign_key` are stored as **metadata** (documented, not enforced), and `check` constraints are **not supported** at all. So numeric ranges are enforced with `dbt_utils.accepted_range` tests instead of `check`, and referential integrity with `relationships` tests (see the next section). Contract **drift detection** works regardless of the warehouse — it's a dbt compile-time check, not a database feature.

---

## 2. Data quality (tests)

**What it is.** Tests are assertions dbt runs against built data. A failing test can **warn** (visible, non-blocking) or **error** (blocks the build / CI). With `store_failures: true` the offending rows land in a table so you can query exactly which records failed.

### What you can use

| Kind | Examples | Use for |
|---|---|---|
| **Built-in generic tests** | `not_null`, `unique`, `accepted_values`, `relationships` | keys, enums, referential integrity |
| **Package tests** (`dbt_utils`) | `accepted_range`, `unique_combination_of_columns` | numeric ranges, composite grain |
| **Singular tests** | any SQL file in [tests/](../tests/) that returns failing rows | bespoke, cross-model rules |
| **Unit tests** (`unit_tests:`) | mocked `given` rows → `expect` rows | transformation *logic*, no warehouse data needed |
| **Source freshness** | `loaded_at_field` + `freshness:` thresholds | catching stale upstream loads |
| **Severity** | `config: {severity: warn \| error}` | make a check advisory vs blocking |

Two heavier tiers are available but **off by default** in this project (flip a var in [dbt_project.yml](../dbt_project.yml) to enable): `dbt_expectations` (richer value/range/regex/distribution assertions) and `elementary` (anomaly detection + test-result observability).

### In YAML

Column-level generic tests, in the same `_<folder>.yml` as the model. Note the Fusion `arguments:` nesting and per-test `config:`:

```yaml
columns:
  - name: category
    data_type: varchar
    data_tests:
      - accepted_values:
          arguments:
            values: ['Electronics', 'Accessories']
  - name: price
    data_type: number(10,2)
    data_tests:
      - dbt_utils.accepted_range:
          config:
            severity: warn          # advisory, does not block the build
          arguments:
            min_value: 0
            inclusive: true
  - name: customer_hk
    data_tests:
      - relationships:
          arguments:
            to: ref('dim_customer')
            field: customer_hk
```

Model-level test for composite grain (e.g. a Data Vault satellite is one row per key per load), from [models/raw_vault/_raw_vault.yml](../models/raw_vault/_raw_vault.yml):

```yaml
models:
  - name: sat_customer_details
    data_tests:
      - dbt_utils.unique_combination_of_columns:
          arguments:
            combination_of_columns:
              - customer_hk
              - load_date
```

Unit test — assert logic against mocked inputs, from [models/marts/_unit_tests.yml](../models/marts/_unit_tests.yml):

```yaml
unit_tests:
  - name: fact_orders_computes_total_amount
    model: fact_orders
    given:
      - input: ref('sat_order_details')
        rows:
          - {link_customer_product_hk: 'lk1', quantity: 3, unit_price: 25.00}
    expect:
      rows:
        - {link_customer_product_hk: 'lk1', total_amount: 75.00}
```

Source freshness, from [models/staging/_sources.yml](../models/staging/_sources.yml):

```yaml
sources:
  - name: raw
    loaded_at_field: _loaded_at
    freshness:
      warn_after:  {count: 24, period: hour}
      error_after: {count: 48, period: hour}
    tables:
      - name: raw_orders
        freshness:                 # override per table — orders arrive more often
          warn_after:  {count: 6,  period: hour}
          error_after: {count: 12, period: hour}
```

### Fusion note

Use `data_tests:` (not `tests:`), and put generic-test parameters under `arguments:`. `store_failures: true` is set project-wide in [dbt_project.yml](../dbt_project.yml) so failing rows are always queryable.

---

## 3. Model access & privacy

**What it is.** The `access` modifier and **groups** control which *other models* are allowed to `ref()` a model — a visibility / API boundary inside the dbt DAG. This is **not** a warehouse permission: whether a human or BI tool can `SELECT` the table is controlled separately by database `grants:`. Access governs the *code* dependency graph; grants govern *query* privileges.

### What you can use

- **`access:`** — one of `public` (any model, including other projects, may `ref()` it), `protected` (default — only models in the same project), or `private` (only models in the same **group**).
- **`groups:`** — a named group with an accountable `owner`. Marking internal models `private` + assigning them to a group stops anything outside that group from depending on them.
- **Exposures** — declare downstream consumers (a dashboard, a report) so a model's *blast radius* is visible in the lineage even though the consumer lives outside dbt.
- **`config.meta`** — adjacent descriptive metadata (e.g. a `pii: true` flag, business definitions). Not access control, but the "who/what" often lives here; the [dbt_yaml_generator](../procs/cpnc/dbt_yaml_generator/) can scaffold it.

### In YAML

Define a group with an owner (top of [models/marts/_marts.yml](../models/marts/_marts.yml)):

```yaml
groups:
  - name: marts_public
    owner:
      name: Analytics Engineering
      email: analytics@alnz.example
```

Set access + group as a folder default in [dbt_project.yml](../dbt_project.yml)…

```yaml
models:
  alnz_data_vault:
    marts:
      +access: public
```

…and assign the group per model:

```yaml
models:
  - name: dim_customer
    group: marts_public
    access: public          # optional here — inherited from dbt_project.yml
```

Declare a downstream consumer in [models/exposures.yml](../models/exposures.yml):

```yaml
exposures:
  - name: revenue_dashboard
    type: dashboard
    url: https://bi.alnz.example/dashboards/revenue
    depends_on:
      - ref('fact_orders')
      - ref('dim_customer')
    owner:
      name: Analytics Engineering
      email: analytics@alnz.example
```

The typical pattern: **public + contracted marts** as the consumer-facing interface, **private/protected internal layers** (staging, raw vault) that no one outside the team may `ref()`.

---

## Quick reference — which file does what

| File | Holds |
|---|---|
| [dbt_project.yml](../dbt_project.yml) | Project-wide defaults & toggles: `+contract`, `+access`, `+store_failures`, package `vars` |
| `models/<folder>/_<folder>.yml` | Per-model detail: `columns` + `data_type`, `constraints`, `versions`, `data_tests`, `access`, `group` |
| [models/staging/_sources.yml](../models/staging/_sources.yml) | Source declarations + `freshness` thresholds |
| [models/exposures.yml](../models/exposures.yml) | Downstream consumers (dashboards, reports) for blast-radius visibility |
| [tests/](../tests/)`*.sql` | Singular (custom SQL) tests |

**Generated vs hand-authored.** The [dbt_yaml_generator](../procs/cpnc/dbt_yaml_generator/) package can scaffold the `columns:`, `data_type:`, and `config.meta:` portions of a model's YAML from a column inventory. It can also switch `contract.enforced` on or off **per model**, driven by a flag column on a model-level sheet of the same inventory workbook — an independent flow, off unless you run it with `--apply-data-contracts` (alongside normal generation) or `--contracts-only` (the contract key and nothing else). The remaining governance pieces — `access`, `group`, `constraints`, `data_tests`, `versions` — are authored by hand, so you stay in control of what promises each model makes.
