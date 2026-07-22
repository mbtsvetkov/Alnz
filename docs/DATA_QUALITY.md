# Data Quality & Data Contract Framework

A layer-tiered framework that makes this dbt project's models trustworthy. It
defines **one documented minimum bar** for data quality per layer, plus
**enforced contracts** on the models other people and tools consume. Optional
tooling is toggled through project `vars`, never hard-coded — a bare install
needs only `dbt_utils`.

This project (Snowflake + dbt Cloud, Fusion preview) is the worked reference
implementation. See [ARCHITECTURE.md](ARCHITECTURE.md) for the Data Vault layers
and [TEST_RESULTS.md](TEST_RESULTS.md) for the run logs and a debugging walkthrough.

---

## Principles

1. **Tiered, not uniform.** Test intensity scales with how exposed a model is.
2. **Contracts only at the interface.** Enforced contracts + versions apply to the
   public `marts` layer. Staging and the raw vault stay flexible.
3. **Shift left.** Catch bad keys and staleness at source/staging, before they
   propagate into the vault.
4. **Configurable, not mandatory.** Advanced packages are opt-in via `vars`.
5. **One documented bar.** This file is the single source of truth for the minimum
   per layer — and it is enforced by a coverage test, not reviewer memory.

---

## Part B — Data quality: the per-layer minimum bar

Baseline uses only native generic tests + `dbt_utils` (already installed).

| Layer | Materialization | Minimum quality bar |
|---|---|---|
| **sources** (`raw`) | n/a | `freshness` (warn/error); `not_null`/`unique` on natural keys; `loaded_at_field` set — see [`_sources.yml`](../models/staging/_sources.yml) |
| **staging** (`stg_`) | view | `not_null` + `unique` on business keys; type-cast in SQL — see [`_staging.yml`](../models/staging/_staging.yml) |
| **raw_vault** (`hub_`/`link_`/`sat_`) | incremental, insert-only | HK: `unique`+`not_null`; hub business key: `unique`; link/sat FKs: `relationships` to parent; sat grain: `dbt_utils.unique_combination_of_columns(*_hk, load_date)` — see [`_raw_vault.yml`](../models/raw_vault/_raw_vault.yml) |
| **marts** (`dim_`/`fact_`) — **public** | table | all of the above **plus** enforced contract, constraints, `accepted_values`/range checks, and **unit tests** — see [`_marts.yml`](../models/marts/_marts.yml) |

### Cross-cutting mechanisms

- **Severity & thresholds.** `config: {severity: warn|error}` (and `error_if`/
  `warn_if`) so non-critical checks warn instead of blocking. **Convention here:**
  key / relationship / enum integrity is **error** (blocks); range/sanity checks
  (`price >= 0`, `quantity >= 1`, `total_amount >= 0`) are **warn**.
- **`store_failures: true`** (set project-wide in [`dbt_project.yml`](../dbt_project.yml))
  so failing rows land in a table for triage.
- **Sources + freshness.** [`_sources.yml`](../models/staging/_sources.yml) declares
  the raw tables with `freshness` + `loaded_at_field`, run via `dbt source freshness`.
  The demo reads the same shape from **seeds** (fallback) so it builds without a
  live raw schema; switch staging to `source()` in production.
- **Unit tests.** Native `unit_tests:` assert mart logic from mocked inputs — see
  [`_unit_tests.yml`](../models/marts/_unit_tests.yml) (`total_amount`, `email_domain`).
- **Coverage gate.** [`assert_test_coverage.sql`](../tests/assert_test_coverage.sql)
  fails if a governed model lacks its required tests, or a mart lacks an enforced
  contract — the minimum bar as an automated check.

### Optional advanced tiers (config-gated)

Declared (commented) in [`packages.yml`](../packages.yml), referenced only behind a
var, so a minimal install ignores them:

- `vars: {use_dbt_expectations: true}` → richer value/range/regex/distribution assertions.
- `vars: {use_elementary: true}` → anomaly detection + test-result observability.

---

## Part C — Data contracts (marts only)

Applied to `marts` and anything referenced by an [exposure](../models/exposures.yml)
— nothing internal.

- **Enforced contract.** `contract.enforced: true` (set on the `marts` group in
  `dbt_project.yml`) + a full `columns:` list with `data_type` on every mart
  column. The build fails if the model's output shape drifts from the YAML. Mart
  SQL casts every column explicitly so output types match the contract.
- **Constraints.** `primary_key`, `foreign_key`, `not_null` declared on the
  contracted models.

  > **Portability note (Snowflake).** Snowflake **enforces `not_null` only**.
  > `primary_key` / `foreign_key` are stored as **metadata** (documented, not
  > enforced). **`check` constraints are not supported on Snowflake at all**, so
  > numeric ranges are enforced with `dbt_utils.accepted_range` tests instead.
  > Referential integrity is additionally guarded by `relationships` tests (and
  > `assert_no_orphan_links.sql`), which run on every adapter. If your adapter
  > rejects the `primary_key`/`foreign_key` DDL, drop those constraint blocks —
  > the tests still cover the integrity.

- **Versioning + deprecation.** `dim_customer` ships **v1 + v2** with
  `latest_version: 2`. v2 adds `email_domain` (an additive change → a *minor*
  version); v1 carries a `deprecation_date` so consumers migrate on
  `ref('dim_customer', version=1)` without a hard break.
- **Access governance.** `access: public` on marts (set in `dbt_project.yml`);
  staging/vault stay non-public. A `marts_public` group with a named owner controls
  cross-boundary `ref()`.
- **Exposures.** [`exposures.yml`](../models/exposures.yml) declares the downstream
  BI consumer so `dbt build -s +exposure:revenue_dashboard` and lineage show the
  contract's blast radius.

### Contract-change policy

- **Additive** change (new column) → a **minor** version.
- Column **removal / rename / type-narrowing** → **breaking**: requires a **new
  version** + `deprecation_date` + consumer notice.
- CI enforces the contract; this policy governs how you evolve it.

---

## Verification

Run in dbt Cloud (or Core with `~/.dbt/profiles.yml`):

- **Baseline.** `dbt build` — models + tests + contracts + the coverage gate all
  pass with optional tiers off. `dbt source freshness` runs once a live raw schema
  is wired.
- **Contract enforcement (negative test).** Change a contracted mart column's type
  in SQL but not in `_marts.yml` → `dbt build` fails with a contract error. Revert.
- **Coverage gate (negative test).** Remove a required test from a model →
  `assert_test_coverage` fails. Restore.
- **Versioning.** `dbt build -s dim_customer.v2` builds the versioned model;
  `ref('dim_customer')` → v2, `ref('dim_customer', version=1)` → v1.
- **Optional tiers.** Set `vars: {use_dbt_expectations: true}` (uncomment in
  `packages.yml`, `dbt deps`) → extra assertions activate; unset → skipped.

---

## Rollout checklist (reuse in another repo)

- [ ] Copy this playbook + `packages.yml` toggles + `store_failures`/`vars` in `dbt_project.yml`.
- [ ] Add a `sources:` block with `freshness:` + `loaded_at_field`.
- [ ] Bring each layer to the [minimum bar](#part-b--data-quality-the-per-layer-minimum-bar).
- [ ] Put enforced contracts + `versions` + `access: public` + a `group` on marts.
- [ ] Declare consumers in `exposures.yml`.
- [ ] Add `assert_test_coverage.sql` and confirm it passes.
