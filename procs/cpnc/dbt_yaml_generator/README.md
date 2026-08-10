# dbt_yaml_generator

Generate **one dbt schema file per model** (`<model>.yml`, next to the `.sql`) from a
**column-inventory source** — a local Excel export now (SharePoint-synced), a Snowflake table
later. Each column gets `description`, `data_type`, and a `config: meta:` block
(`business_name`, `business_definition`, `pii`, … — extensible). Model-level `config`
(`schema`/`materialized`/…) comes from per-folder defaults, and **data contracts** are switched
on per model from a separate sheet by a separate flag — see
[Data contracts (independent flow)](#data-contracts-independent-flow).

This is a **self-contained, drop-in package**: zip the folder, unzip into any dbt project,
configure, run.

---

## What it is / isn't

- **Is:** a code-generator you run in **dbt Core** (locally or CI). It reads the inventory and
  writes YAML files.
- **Isn't:** it does **not** run dbt, and it does **not** reinstall or modify your dbt install.
  "Target project" = your **dbt repo** (the folder with `dbt_project.yml` + `models/`), not the
  dbt-Core virtual environment.

After unzip:
```
<your-dbt-repo>/
  dbt_project.yml
  models/ ...                       # your .sql models
  procs/
    cpnc/
      requirements.txt              # shared deps for every procs/cpnc/* tool
      requirements-dev.txt
      run_yaml_generator.py         # launcher — run this
      dbt_yaml_generator/           # this package (writes <model>.yml next to each .sql)
```

## Setup (reuse your existing dbt venv)

```powershell
# activate the venv you already run dbt from, then:
pip install -r procs\cpnc\requirements.txt      # adds ruamel.yaml + openpyxl only
```
No existing Python env? Run `procs\cpnc\dbt_yaml_generator\bootstrap.ps1` (or `bootstrap.sh`) —
it makes a `.venv`, installs, and runs the tests as a smoke check.

## Configure

```powershell
copy procs\cpnc\dbt_yaml_generator\config.example.yml procs\cpnc\dbt_yaml_generator\config.yml
```
Edit `config.yml`:
- **`folders`** — parent folders (relative to the dbt project root) scanned recursively for `.sql`.
- **`source.excel.sheet`** — the tab holding the `prev_/cpnc_` headers (e.g. `Sheet1`).
- **`source.mapping`** — which headers are authoritative. Default = the **`cpnc_` side**.
- **`meta_fields`** — fields under `config.meta`. Starts with `business_name`,
  `business_definition`, `pii`; add a line to extend (e.g. `remark`).
- **`folder_defaults`** — model-level config per folder. **Don't set `contract` here** — that
  would contract a whole folder wholesale; use the per-model `contracts` sheet instead.
- **`contracts`** — the model-level sheet driving `contract.enforced`. Only read when you ask
  for it; see [Data contracts (independent flow)](#data-contracts-independent-flow).

`config.yml`, `.venv`, and `*.env` are gitignored, so they never travel in the zip.

## Run (from the dbt project root)

```powershell
python procs\cpnc\run_yaml_generator.py --excel-path "C:\Users\<you>\OneDrive - Allianz\...\cim3_cpnc_model_inventory.xlsx" --dry-run
python procs\cpnc\run_yaml_generator.py --excel-path "...same path..."
```
(Equivalent: `python -m dbt_yaml_generator ...` run from inside `procs\cpnc\`.)
- `--dry-run` prints a unified diff and writes nothing.
- `--source snowflake` reads a table instead (see below).
- `--project-dir` overrides the auto-detected project root.
- `--apply-data-contracts` / `--contracts-only` drive the contract flag (see below). Without
  them, no `contract` key is ever written or removed.
- The run prints a summary: files written, `.sql` models with no inventory rows, inventory
  models with no `.sql` (mismatch check), skipped/duplicate/blank-type counts.

Then let dbt consume the result: `dbt parse && dbt docs generate`.

## Behaviour

- **cpnc-only:** only the `cpnc_` columns feed the YAML. Rows with a blank `cpnc_column_name`
  (the `..._NOT_APPLICABLE_888` sentinels) are skipped.
- **Excel wins, tests kept:** on an existing `<model>.yml`, `description`/`data_type`/`meta` are
  overwritten from the inventory, but per-column `data_tests`/`constraints` and the model
  description are preserved. Columns not in the inventory are kept (and reported).
- **Contracts are opt-in:** `config.contract` is never touched unless `--apply-data-contracts` or
  `--contracts-only` is passed.
- **Empties:** blank string → `""`; blank `pii` (or any boolean) → `false`.
- **Idempotent:** re-running with an unchanged inventory rewrites nothing.

## Data contracts (independent flow)

A [data contract](../../../docs/DATA_GOVERNANCE_CONCEPTS.md) is an enforced promise about a
model's output shape: dbt compares the compiled SQL to the declared `columns:` + `data_type:` and
**fails the build if they drift**. That is a governance decision per model, so it is kept out of
normal generation entirely: **no `contract` key is written or removed unless you pass a flag.**

The decision comes from a **model-level sheet** in the same workbook — one row per model, e.g.
the `inventory_overview` tab, whose flag column says yes or no:

| # | model_name | schema | path | … | status | Is_Data_Contract_Enabled |
|---|---|---|---|---|---|---|
| 1 | `bv_cim_load_date` | `bnl_bvlt` | `bnl_bvlt/cim3` | … | pending | `TRUE` |
| 2 | `bv_cpnc_load_date` | `bnl_cpnc` | `bnl_cpnc` | … | pending | `FALSE` |

Configure the sheet in `config.yml` (all names are yours to change):
```yaml
contracts:
  sheet: inventory_overview
  header_row: 1
  model_column: model_name
  flag_column: Is_Data_Contract_Enabled
  path_column: path        # optional; tells apart same-named models in two schemas
  # excel_path: ""         # optional; only if the flags live in another workbook
```

Then run it — the flag is the *only* thing these two modes have in common:
```powershell
# generate columns/meta as usual AND apply the contract flag
python procs\cpnc\run_yaml_generator.py --apply-data-contracts --dry-run
python procs\cpnc\run_yaml_generator.py --apply-data-contracts

# contract key only — descriptions, data_types, meta and folder defaults are NOT touched
python procs\cpnc\run_yaml_generator.py --contracts-only --dry-run
python procs\cpnc\run_yaml_generator.py --contracts-only

# read the flag from a differently-named tab for this run
python procs\cpnc\run_yaml_generator.py --contracts-only --contracts-sheet data_contracts
```

What gets written, per model:
```yaml
models:
  - name: bv_cim_load_date
    config:
      materialized: incremental
      contract:
        enforced: true          # or false — both are written explicitly
```

Rules:
- **True and false are both explicit.** A blank flag cell counts as `false` (and is reported, so
  "nobody decided yet" is visible). An unrecognised value (`maybe`, …) is also `false` and is
  listed in the summary.
- **Models absent from the sheet are left completely alone** — no key added, none removed.
- **`enforced` only.** Per-column `constraints:`, `versions:`, `access:` and `data_tests:` stay
  hand-authored, exactly as [DATA_GOVERNANCE_CONCEPTS.md](../../../docs/DATA_GOVERNANCE_CONCEPTS.md)
  prescribes. Everything already in `config:` is preserved.
- **The sheet beats `folder_defaults`.** If both set a contract you get a warning and the sheet
  wins per model.
- **`--contracts-only` never scaffolds.** A contract needs a `columns:` list, so a model with no
  `<model>.yml` yet is reported and skipped, not created.
- **Blank `data_type` is a warning, not a block.** A contracted model whose columns lack types is
  still written, with the offending columns listed — `dbt build` will reject it until they're
  filled, which is the intended feedback loop.
- **Same model name twice** (e.g. the same view in two schemas) with *disagreeing* flags is
  resolved via `path_column` against the model's folder; if that can't decide, the model is left
  untouched and reported as a conflict.

On Snowflake, `not_null` is enforced, `primary_key`/`foreign_key` are metadata only, and `check`
is unsupported — but contract **drift detection** is a dbt compile-time check and works
regardless of the warehouse.

## Data-type backfill from Snowflake (optional)

A column's `data_type` is resolved in this order, stopping at the first non-blank:
1. the mapped inventory cell (e.g. `cpnc_data_type`),
2. `source.data_type_fallback`, if configured (another header on the **same** row),
3. **live** `INFORMATION_SCHEMA.COLUMNS`, if `source.snowflake.fill_missing_data_types: true`
   (or `--fill-types-from-snowflake`) — looked up from the model's real, deployed table.

Tier 3 needs the same `SNOWFLAKE_*` env vars as `--source snowflake` (see below) — schema is
derived from each model's folder, database from `SNOWFLAKE_DATABASE`. It runs **one** batched
query per run, not one per column. It is opt-in and OFF by default: with it off (or with
`--source excel` and no flag), the tool never imports `snowflake.connector` or opens a
connection — a still-blank data type just stays blank, exactly as before this feature existed.

This account requires MFA (`authenticator=username_password_mfa`). Run `python seed_mfa.py`
once to cache an MFA token locally; as long as that cache is valid, this connects silently
(no passcode prompt). If the cached token has expired, you'll get a clear error telling you
to re-run `seed_mfa.py`.

### Setting the SNOWFLAKE_* env vars (PowerShell)

`connect()` reads `SNOWFLAKE_ACCOUNT/USER/ROLE/WAREHOUSE/DATABASE/SCHEMA` +
`SNOWFLAKE_PASSWORD` (or `SNOWFLAKE_PRIVATE_KEY_PATH`) straight from the environment — it does
**not** read `profiles.yml`. `seed_mfa.py` only caches the MFA token; it does not set these
vars, so they still need to be exported in whatever terminal you run the generator from,
**every new session** (they don't persist once the window closes). Two things vary per person:

- **`SNOWFLAKE_DATABASE`** — must match wherever the models you're generating for actually
  live (check in Snowsight: expand the database → schema → the table should be there). This
  project has more than one target/database (e.g. `local_dev` → `DBAREA`,
  `dev` → `DBAREA_COMMON` in `profiles.yml`) — pick the one matching your target, not
  necessarily the profile's default.
- **`SNOWFLAKE_SCHEMA`** — just the connection's default session schema, conventionally
  `DBT_<your-username>` (e.g. `DBT_TSVETM`). It does **not** restrict which schema gets
  searched for a model's data type — that's derived per-model from its folder
  (`bnl_cpnc`, `bnl_bvlt`, …) — so any schema your role can access works here.

**Easiest: dot-source the seed script** `procs\cpnc\set_snowflake_env.ps1` — it sets all six
non-secret vars and prompts (masked, safe on a shared screen) for the password. Must be
**dot-sourced** (leading `. `), not just run, or the vars only exist inside the script's own
child scope and vanish the instant it exits:
```powershell
. .\procs\cpnc\set_snowflake_env.ps1
```
Edit the account/role/warehouse/database/schema values inside that file once to match your own
login and target (defaults to `DBAREA_COMMON` / `DBT_<username>`, per the notes above), then
just dot-source it at the start of every session, right before:
```powershell
python procs\cpnc\run_yaml_generator.py --dry-run
```

If you'd rather not run even that each session, put the values (in `KEY=VALUE` form, no `$env:`
prefix) in a `.env` file at `procs\cpnc\dbt_yaml_generator\.env` — it's gitignored, and
`cli.py` loads it automatically on every run. That still stores the password in plaintext on
disk, so only do this on a machine/session you control.

<details>
<summary>Manual one-off syntax (if you'd rather not use the seed script)</summary>

Which password syntax works depends on your **PowerShell version**
(`$PSVersionTable.PSVersion`):

PowerShell 7+ (`ConvertFrom-SecureString -AsPlainText` is supported):
```powershell
$env:SNOWFLAKE_PASSWORD = Read-Host -AsSecureString | ConvertFrom-SecureString -AsPlainText
```

Windows PowerShell 5.1 (ships with Windows by default — `-AsPlainText` isn't available):
```powershell
$sec = Read-Host -AsSecureString
$env:SNOWFLAKE_PASSWORD = [System.Runtime.InteropServices.Marshal]::PtrToStringAuto([System.Runtime.InteropServices.Marshal]::SecureStringToGlobalAllocUnicode($sec))
```
Both need `SNOWFLAKE_ACCOUNT/USER/ROLE/WAREHOUSE/DATABASE/SCHEMA` set the same way, e.g.
`$env:SNOWFLAKE_DATABASE = "DBAREA_COMMON"` — see `set_snowflake_env.ps1` for the full list.
</details>

## Snowflake source (optional, later)

Reuses the **same `SNOWFLAKE_*` env vars your `profiles.yml` already uses** — no new
credentials. Uncomment `snowflake-connector-python` in `procs\cpnc\requirements.txt`, create a
table like `snowflake/COLUMN_DICTIONARY.sql`, set `source.snowflake.table`, then:
```powershell
python procs\cpnc\run_yaml_generator.py --source snowflake
```

## Auth summary

- **Excel (local file):** no authentication in the script at all — you download / OneDrive-sync
  the `.xlsx`.
- **Snowflake:** shares dbt's credentials (own connection, no extra secret).
- Pulling from SharePoint *directly* (Microsoft Graph app registration) is intentionally out of
  scope — use the local/synced file.

## Tests

```powershell
pip install -r procs\cpnc\requirements-dev.txt
python -m pytest procs\cpnc\dbt_yaml_generator\tests
```
Fully offline — a fixture workbook is built in-memory, so no SharePoint and no Snowflake are
needed to prove the package works in any repo.
