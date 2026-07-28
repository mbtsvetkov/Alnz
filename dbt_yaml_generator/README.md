# dbt_yaml_generator

Generate **one dbt schema file per model** (`<model>.yml`, next to the `.sql`) from a
**column-inventory source** — a local Excel export now (SharePoint-synced), a Snowflake table
later. Each column gets `description`, `data_type`, and a `config: meta:` block
(`business_name`, `business_definition`, `pii`, … — extensible). Model-level `config`
(`schema`/`materialized`/`contract`/…) comes from per-folder defaults.

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
  models/ ...                 # your .sql models
  dbt_yaml_generator/         # this package (writes <model>.yml next to each .sql)
```

## Setup (reuse your existing dbt venv)

```powershell
# activate the venv you already run dbt from, then:
pip install -r dbt_yaml_generator\requirements.txt      # adds ruamel.yaml + openpyxl only
```
No existing Python env? Run `dbt_yaml_generator\bootstrap.ps1` (or `bootstrap.sh`) — it makes a
`.venv`, installs, and runs the tests as a smoke check.

## Configure

```powershell
copy dbt_yaml_generator\config.example.yml dbt_yaml_generator\config.yml
```
Edit `config.yml`:
- **`folders`** — parent folders (relative to the dbt project root) scanned recursively for `.sql`.
- **`source.excel.sheet`** — the tab holding the `prev_/cpnc_` headers (e.g. `Sheet1`).
- **`source.mapping`** — which headers are authoritative. Default = the **`cpnc_` side**.
- **`meta_fields`** — fields under `config.meta`. Starts with `business_name`,
  `business_definition`, `pii`; add a line to extend (e.g. `remark`).
- **`folder_defaults`** — model-level config per folder. **Keep `contract.enforced` off until
  every column has a `data_type`.**

`config.yml`, `.venv`, and `*.env` are gitignored, so they never travel in the zip.

## Run (from the dbt project root)

```powershell
python -m dbt_yaml_generator --excel-path "C:\Users\<you>\OneDrive - Allianz\...\cim3_cpnc_model_inventory.xlsx" --dry-run
python -m dbt_yaml_generator --excel-path "...same path..."
```
- `--dry-run` prints a unified diff and writes nothing.
- `--source snowflake` reads a table instead (see below).
- `--project-dir` overrides the auto-detected project root.
- The run prints a summary: files written, `.sql` models with no inventory rows, inventory
  models with no `.sql` (mismatch check), skipped/duplicate/blank-type counts.

Then let dbt consume the result: `dbt parse && dbt docs generate`.

## Behaviour

- **cpnc-only:** only the `cpnc_` columns feed the YAML. Rows with a blank `cpnc_column_name`
  (the `..._NOT_APPLICABLE_888` sentinels) are skipped.
- **Excel wins, tests kept:** on an existing `<model>.yml`, `description`/`data_type`/`meta` are
  overwritten from the inventory, but per-column `data_tests`/`constraints` and the model
  description are preserved. Columns not in the inventory are kept (and reported).
- **Empties:** blank string → `""`; blank `pii` (or any boolean) → `false`.
- **Idempotent:** re-running with an unchanged inventory rewrites nothing.

## Snowflake source (optional, later)

Reuses the **same `SNOWFLAKE_*` env vars your `profiles.yml` already uses** — no new
credentials. Uncomment `snowflake-connector-python` in `requirements.txt`, create a table like
`snowflake/COLUMN_DICTIONARY.sql`, set `source.snowflake.table`, then:
```powershell
python -m dbt_yaml_generator --source snowflake
```

## Auth summary

- **Excel (local file):** no authentication in the script at all — you download / OneDrive-sync
  the `.xlsx`.
- **Snowflake:** shares dbt's credentials (own connection, no extra secret).
- Pulling from SharePoint *directly* (Microsoft Graph app registration) is intentionally out of
  scope — use the local/synced file.

## Tests

```powershell
pip install -r dbt_yaml_generator\requirements-dev.txt
python -m pytest dbt_yaml_generator\tests
```
Fully offline — a fixture workbook is built in-memory, so no SharePoint and no Snowflake are
needed to prove the package works in any repo.
