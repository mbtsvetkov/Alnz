# Plan: Column-metadata YAML generator (`config: meta:` from Snowflake)

## Context

The `alnz_data_vault` dbt project documents columns today with only `description` and
`data_tests` (see [_staging.yml](models/staging/_staging.yml),
[_raw_vault.yml](models/raw_vault/_raw_vault.yml), [_marts.yml](models/marts/_marts.yml)).
We want every column to also carry a governance block:

```yaml
columns:
  - name: email
    description: "Contact email."
    data_type: varchar          # kept as-is where present; populated on scaffold
    config:
      meta:
        business_name: "Email Address"
        business_definition: "Primary contact email address of the customer."
        pii: true
```

The three values come from a **Snowflake governance table**, and a **Python generator** writes
them into the `_*.yml` files. This mirrors the reference tooling the user shared
(`model_yaml_generation.py` / `libs.*` from another Allianz repo) but is built fresh here —
**none of that tooling, no metadata seed, and no `config: meta:` block exists in this repo yet**
(confirmed by search).

**Decisions locked with the user:**
- Delivery: **standalone Python script** (not a dbt macro).
- Source: **Snowflake table only.**
- Scope: **configurable per model folder** (like the old `sources_dir.txt` pattern).
- **Two responsibilities** (this is the create-if-missing addition):
  1. **Scaffold** — generate a schema entry for any model with no YAML coverage yet
     (matches `model_yaml_generation.py`'s create-if-missing behaviour).
  2. **Enrich** — inject/refresh the `config: meta:` governance block on every documented
     column (scaffolded or hand-written).

**How this satisfies "works in dbt Cloud *and* dbt Core":** a Python script cannot run *inside*
dbt Cloud (no Python runtime; the Snowflake connection lives in the Cloud UI, not a readable
`profiles.yml`). So the script is a **developer / CI code-generation step** (run on dbt Core,
locally, or in CI). It writes the YAML into the committed `_*.yml` files, and **both dbt Cloud
and dbt Core then consume that identical committed YAML** — via `dbt docs`, the manifest/catalog,
and `meta`-driven tooling. Documented in the tool's README so the boundary isn't surprising.

---

## Deliverables (all net-new)

```
tools/
  gen_column_meta.py          main generator (CLI)
  libs/
    snowflake_utils.py        connection + governance read + INFORMATION_SCHEMA column read
    model_utils.py            list .sql models per folder, find undocumented models
    yaml_utils.py             round-trip load / scaffold model entry / inject meta / write
  config/
    meta_dirs.yml             which model folders to process (per-folder scope)
  tests/
    test_yaml_utils.py        offline unit tests: scaffold + inject meta against fixtures
    test_generator.py         end-to-end with a MOCKED snowflake cursor (no live account)
    fixtures/                 sample _*.yml + fake governance rows
  requirements.txt            runtime deps (ruamel.yaml, snowflake-connector-python)
  requirements-dev.txt        pytest (for the offline tests)
  README.md                   local dbt-Core setup, env vars, table shape, scaffold caveat, Cloud/Core note
docs/governance/
  COLUMN_DICTIONARY.sql       CREATE TABLE + sample INSERTs for the governance table
```

The `libs/{snowflake_utils,model_utils,yaml_utils}.py` split intentionally mirrors the user's
existing toolchain (`libs.snowflake_utils`, `libs.model_utils`, `libs.yaml_utils`).

---

## The Snowflake governance table (contract)

One row per governed column (name/schema configurable, default `GOVERNANCE.COLUMN_DICTIONARY`):

| column | type | notes |
|---|---|---|
| `MODEL_NAME` | varchar | dbt model name, e.g. `dim_customer` (matched case-insensitively) |
| `COLUMN_NAME` | varchar | matched case-insensitively to the column |
| `BUSINESS_NAME` | varchar | → `config.meta.business_name` |
| `BUSINESS_DEFINITION` | varchar | → `config.meta.business_definition` |
| `PII` | boolean | → `config.meta.pii` |

[docs/governance/COLUMN_DICTIONARY.sql](docs/governance/COLUMN_DICTIONARY.sql) ships the
`CREATE TABLE` + seed rows for the current models so the feature is runnable end-to-end.
Versioned models (`dim_customer` v1/v2) key on the base name `dim_customer`.

## Column discovery for scaffolding (the new dependency)

When a model has no YAML, the script needs its column list. Source of truth =
**Snowflake `INFORMATION_SCHEMA.COLUMNS`** for the built object in the target
database/schema (from the `SNOWFLAKE_*` env vars). This also yields `DATA_TYPE`, which we
write as `data_type:` — needed for contracted marts and matching the old toolchain's
Snowflake-centric approach.

> **Caveat (call out in README):** scaffolding a model requires that model to be **built**
> in the target schema first (`dbt run -s <model>`). Enrich mode has no such dependency.
> If a model isn't built, the script logs it as "cannot scaffold — not found in
> INFORMATION_SCHEMA" and moves on rather than failing.

## Connection / credentials — NOT in the script

Credentials are **never hardcoded and never committed**. A single set of **environment
variables** is the source of truth, consumed by both dbt Core and this script:

`SNOWFLAKE_ACCOUNT`, `SNOWFLAKE_USER`, `SNOWFLAKE_PASSWORD` (or key-pair),
`SNOWFLAKE_ROLE`, `SNOWFLAKE_WAREHOUSE`, `SNOWFLAKE_DATABASE`, `SNOWFLAKE_SCHEMA`.

- `~/.dbt/profiles.yml` (outside the repo) references them via `env_var(...)` — dbt Core uses
  them to connect.
- `libs/snowflake_utils.py` reads the **same** env vars via `snowflake-connector-python`.

So you configure the connection once; nothing sensitive lands in git (the repo's `.gitignore`
already follows this convention, and ARCHITECTURE.md documents the same `env_var` pattern).
The script fails fast with a clear message if a required var is unset. Optional convenience: a
gitignored `tools/.env` the script auto-loads for local runs.

## Per-folder scope config — `tools/config/meta_dirs.yml`

```yaml
# Folders processed for scaffolding + meta enrichment. One _<folder>.yml per folder.
folders:
  - models/marts
  - models/staging
  - models/raw_vault
# Extensible: per-folder overrides (governance schema, skip-scaffold, etc.) can hang
# off each entry without changing the script contract.
```

The one-schema-file-per-folder naming (`_marts.yml`, `_staging.yml`, `_raw_vault.yml`) is the
repo's existing convention; scaffolded models are appended to (or create) `_<folder>.yml`.

---

## Script behavior (`gen_column_meta.py`)

1. Load `meta_dirs.yml`; for each folder, list `.sql` models and locate the folder's
   `_*.yml` file(s).
2. Connect to Snowflake once; read the **governance table** into a dict keyed by
   `(model.lower(), column.lower())`.
3. **Scaffold pass** — for each `.sql` model **not** documented in the folder's YAML:
   - fetch columns (+ `DATA_TYPE`) from `INFORMATION_SCHEMA.COLUMNS`;
   - build a new `models:` entry: `name`, placeholder `description`, and a `columns:` list
     (`name`, `data_type`, and the `config: meta:` block where governance rows exist);
   - append it to the folder's `_<folder>.yml` (create the file if the folder has none).
   - Does **not** invent tests/constraints (that stays out of scope unless requested).
4. **Enrich pass** — round-trip load each YAML with **ruamel.yaml** (`YAML(typ='rt')`,
   preserves comments/order/quoting) and for every `models[].columns[]`:
   - **governance match** → set/merge `column['config']['meta']`
     (`business_name`, `business_definition`, `pii`); leave `description`, `data_type`,
     `constraints`, `data_tests` untouched. Re-run merges/updates, never duplicates.
   - **no match** → leave unchanged; record for the summary.
5. **Idempotency / safety** — compare serialized before/after per file; skip unchanged writes
   (mirrors the reference scripts' `str(existing) == str(new)` guard). `--dry-run` prints a
   unified diff and writes nothing.
6. **Summary** — models scaffolded, models that couldn't scaffold (not built), files changed,
   columns enriched, YAML columns with no governance row, governance rows matching no column.

**Reuse note:** the reference scripts used custom `quote_strings` + PyYAML `write_yaml_file`,
which would flatten this repo's comments. We use ruamel.yaml round-trip for the same intent
(valid, double-quoted YAML) without destroying the curated docs.

CLI:
```
python tools/gen_column_meta.py \
  --config tools/config/meta_dirs.yml \
  --table GOVERNANCE.COLUMN_DICTIONARY \
  [--no-scaffold] [--dry-run]
```
`--no-scaffold` runs enrich-only (safe on machines with nothing built).

---

## Optional CI wiring (mention, don't build unless wanted)

A `.github/workflows/` job (folder exists but is empty) could run `--dry-run --no-scaffold` on
PRs and fail if committed YAML is stale vs the governance table. Requires Snowflake secrets;
left as a follow-up so the first cut has no infra dependency.

---

## Local dbt Core setup (free) — one-time

Both are free: **dbt Core** is open-source; **Snowflake** has a 30-day free trial
(~$400 credits) at [signup.snowflake.com](https://signup.snowflake.com) if you don't already
have an account. README will carry the full copy; the shape:

```bash
# 1. Python env + dbt Core with the Snowflake adapter (free, open-source)
python -m venv .venv && source .venv/Scripts/activate   # Windows Git Bash
pip install dbt-snowflake
pip install -r tools/requirements.txt

# 2. Snowflake connection as ENV VARS (the single source of truth; never committed)
export SNOWFLAKE_ACCOUNT=... SNOWFLAKE_USER=... SNOWFLAKE_PASSWORD=...
export SNOWFLAKE_ROLE=... SNOWFLAKE_WAREHOUSE=... SNOWFLAKE_DATABASE=... SNOWFLAKE_SCHEMA=...

# 3. ~/.dbt/profiles.yml referencing those SAME vars (worked example in ARCHITECTURE.md):
#    default: { target: dev, outputs: { dev: { type: snowflake,
#      account: "{{ env_var('SNOWFLAKE_ACCOUNT') }}", ... } } }

dbt debug     # confirms dbt Core reaches Snowflake with those creds
```

## Testing — two layers

**A. Offline (no Snowflake needed) — proves the YAML logic:**
```bash
pip install -r tools/requirements-dev.txt
pytest tools/tests            # scaffold + inject-meta run against fixtures with a MOCKED cursor
```
`tools/tests/` fakes the Snowflake cursor, so scaffolding, meta injection, comment
preservation, idempotency and drift are all asserted without a live account. This is the
"fully testable" core and what CI can run for free.

**B. End-to-end against real Snowflake:**
```bash
# 1. create the governance table + sample rows
#    (run docs/governance/COLUMN_DICTIONARY.sql in a Snowflake worksheet, or pipe it via the connector)
# 2. build the models so INFORMATION_SCHEMA knows their columns (needed for scaffold)
dbt deps && dbt seed && dbt run

# 3a. enrich existing docs (no build dependency)
python tools/gen_column_meta.py --no-scaffold --dry-run   # inspect diff
python tools/gen_column_meta.py --no-scaffold             # write config: meta: blocks

# 3b. scaffold: add a new stg_*.sql (build it), then
python tools/gen_column_meta.py                            # new models: entry appears

# 4. prove dbt consumes it (works identically in dbt Cloud off the same commit)
dbt parse && dbt docs generate   # business_name/definition/pii show on columns in the catalog
git diff                          # only added config: blocks / new entries; nothing reformatted
```
Idempotency: re-run → "no changes", empty `git diff`. Drift: change a governance value,
re-run → only that column's meta updates.

## Dependencies

Runtime: `ruamel.yaml`, `snowflake-connector-python` (`tools/requirements.txt`). Dev/test:
`pytest` (`tools/requirements-dev.txt`). dbt Core itself via `pip install dbt-snowflake`. No
changes to `dbt_project.yml`, `packages.yml`, or model SQL.
