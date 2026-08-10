# dbt_yaml_generator — Installation & Usage Guide

A step-by-step guide for a **new developer** to install and run the tool. It generates one dbt
schema file per model (`<model>.yml`, next to the `.sql`) from a **column-inventory Excel** —
each column gets `description`, `data_type`, and a `config: meta:` block (`business_name`,
`business_definition`, `pii`, …). Model-level `config` (schema/materialized/contract) comes from
per-folder defaults.

> **Mental model:** this is a **code generator you run in dbt Core**. It reads the Excel and
> writes YAML files. It does **not** run dbt and does **not** touch your dbt installation.

---

## 0. Prerequisites

- **Python 3.9–3.12** (3.11/3.12 recommended). Check: `python --version`.
- **The dbt repo** cloned locally (the folder containing `dbt_project.yml` and `models/`).
- **The column-inventory Excel** (`cim3_cpnc_model_inventory_*.xlsx`) downloaded or OneDrive-synced
  somewhere on your machine — it can live **outside** the repo.
- Access to a terminal (VS Code integrated terminal is fine).

---

## 1. Get the package into your repo

The tool is the folder **`dbt_yaml_generator/`**. It must sit **at the root of the dbt repo**
(next to `dbt_project.yml`):

```
<your-dbt-repo>/
  dbt_project.yml
  models/ ...
  dbt_yaml_generator/        <-- here
```

If you received it as a zip, unzip it here. **Check for double-nesting** — you want
`dbt_yaml_generator/cli.py` to exist directly, not `dbt_yaml_generator/dbt_yaml_generator/cli.py`.

---

## 2. Choose a Python environment

**Reuse the virtual environment you already run dbt from** — simplest, and nothing about dbt
changes. Activate it so your prompt shows the env name, e.g. `(dbt-core)`:

```powershell
# Windows PowerShell — adjust the path to your venv
& C:\path\to\your\dbt-venv\Scripts\Activate.ps1
```
```bash
# macOS / Linux
source /path/to/your/dbt-venv/bin/activate
```

> No existing environment? Run `dbt_yaml_generator\bootstrap.ps1` (or `bootstrap.sh`) — it creates
> a `.venv`, installs everything, and runs the tests. Then use that `.venv`.

---

## 3. Install dependencies

Into the **activated** environment (note `python -m pip` — guarantees it installs into the same
interpreter you'll run):

```powershell
python -m pip install -r dbt_yaml_generator\requirements.txt
```

This adds only two libraries: `ruamel.yaml` and `openpyxl`. (For the optional Snowflake source,
also uncomment `snowflake-connector-python` in `requirements.txt` and reinstall.)

---

## 4. Verify the install

```powershell
python -m dbt_yaml_generator --help
```
Prints the usage text = installed and importable. ✅

**(Optional) run the built-in self-tests** — proves the logic works on your machine with no Excel
and no Snowflake:
```powershell
python -m pip install -r dbt_yaml_generator\requirements-dev.txt   # adds pytest
python -m pytest dbt_yaml_generator\tests
```
Expect `11 passed`.

---

## 5. Configure

Copy the template and edit it:
```powershell
copy dbt_yaml_generator\config.example.yml dbt_yaml_generator\config.yml
code dbt_yaml_generator\config.yml
```

Edit these four sections:

```yaml
folders:                         # parent folders (relative to repo root), scanned recursively
  - models/bnl_bvlt

source:
  excel:
    path: "C:/Users/you/Downloads/cim3_cpnc_model_inventory.xlsx"   # forward slashes! (see note)
    sheet: Sheet1               # the tab with the prev_/cpnc_ headers
    header_row: 1
  mapping:                      # cpnc side is authoritative (leave unless your headers differ)
    model_name:  cpnc_model_name
    column_name: cpnc_column_name
    description: cpnc_column_description
    data_type:   cpnc_data_type

meta_fields:                    # fields under config.meta — add a line to extend
  - {key: business_name,       source: business_name,       type: string}
  - {key: business_definition, source: business_definition, type: string}
  - {key: pii,                 source: pii,                 type: boolean}

folder_defaults:                # model-level config per folder (keep contract OFF for now)
  models/bnl_bvlt:
    schema: bnl_bvlt
    materialized: incremental
    on_schema_change: fail
    # contract: {enforced: true}     # turn on ONLY when every data_type is populated
```

> **Windows path gotcha:** in `config.yml`, write the path with **forward slashes**
> (`C:/Users/...`) or single quotes (`'C:\Users\...'`). A double-quoted path with single
> backslashes (`"C:\Users\..."`) fails YAML parsing. Or omit `path` and pass `--excel-path` instead.

`config.yml` is gitignored — your local settings never get committed.

---

## 6. Dry run (writes nothing)

From the **repo root** (the folder with `dbt_project.yml`), with the venv active:
```powershell
python -m dbt_yaml_generator --dry-run
```
(If you didn't set `path` in config: add `--excel-path "C:\...\inventory.xlsx"`.)

**Read the summary at the end — this is the real check:**
```
Inventory: N rows, M models with columns (source: excel)
  YAML files to change           : ...
  .sql models w/o inventory rows : ...     <- should be LOW
  inventory models w/o a .sql    : ...     <- should be LOW
  columns with blank data_type   : ...
```
If **"YAML files to change" is 0**, the models didn't match any inventory rows — check the two
"w/o" lines (see Troubleshooting). Don't proceed until the diff and counts look right.

**Big diff you can't scroll?** Send it to a file and open it:
```powershell
python -m dbt_yaml_generator --dry-run *> dryrun_preview.txt
code dryrun_preview.txt
```

---

## 7. Generate for real, then verify

```powershell
python -m dbt_yaml_generator          # writes/updates the <model>.yml files
git diff                               # review changes (or the Source Control panel)
dbt parse                              # dbt reads the new YAML with no errors
```

Everything is under git, so if you're not happy: `git restore .` reverts it all.

### What it does to files
- **Model has no YAML** → creates `<model>.yml` (only if a matching `.sql` exists).
- **Model has YAML** → overwrites each column's `description`, `data_type`, `config.meta` from the
  Excel; **preserves** your `data_tests`/`constraints` and any columns not in the Excel; appends
  columns that are in the Excel but missing.
- **Missing cell values** → `""` for text fields, `false` for `pii`.
- **Idempotent** → re-running with an unchanged Excel writes nothing.

---

## 8. Day-to-day (every new session)

```powershell
& C:\path\to\dbt-venv\Scripts\Activate.ps1      # 1. activate (skip if VS Code auto-activates)
cd C:\path\to\your-dbt-repo                      # 2. go to repo root
python -m dbt_yaml_generator --dry-run           # 3. preview, then run without --dry-run
```
Dependencies and `config.yml` persist between sessions — no reinstall.

---

## Troubleshooting

| Symptom | Cause & fix |
|---|---|
| `ModuleNotFoundError: No module named 'ruamel'` | Deps not installed in the active env. Run `python -m pip install -r dbt_yaml_generator\requirements.txt`. |
| `No module named pytest` | Only for tests — `python -m pip install -r dbt_yaml_generator\requirements-dev.txt`. |
| `ScannerError: did not find expected hexadecimal number` | Excel `path` in `config.yml` used double quotes + single backslashes. Use forward slashes `C:/...`, single quotes `'C:\...'`, or doubled `\\`. |
| **"YAML files to change: 0"** despite existing files | Models didn't match inventory. Check `.sql models w/o inventory rows` / `inventory models w/o a .sql`: the `cpnc_model_name` values must equal your `.sql` filenames. Fix the folder, the Excel, or `mapping.model_name`. |
| `Relative module names not supported` (with `py -m .\...`) | Use `python -m dbt_yaml_generator` (module name, no path), and `python` not `py` (so you hit the venv). |
| `Could not find dbt_project.yml` | Run from the repo root, or pass `--project-dir "C:\path\to\repo"`. |
| Blank values everywhere in `meta` | Expected if the Excel cells are empty — the business fills them later; re-run updates only those. |
| Sheet/headers error | `source.excel.sheet` must be the tab that actually holds the `prev_/cpnc_` headers; the error lists the sheets it found. |
| Terminal cut off / can't scroll to top | Send output to a file: `... --dry-run *> dryrun_preview.txt` then open it; or raise `terminal.integrated.scrollback` in VS Code settings. |
| Excel open on your laptop | Reading still works (it reads the saved copy on disk). Just **save (Ctrl+S)** first so unsaved edits are picked up. |

---

## Command reference

```
python -m dbt_yaml_generator [options]

  --dry-run                 Preview a unified diff; write nothing.
  --excel-path PATH         Path to the .xlsx (overrides config / EXCEL_PATH env var).
  --source excel|snowflake  Inventory source (default: config source.default = excel).
  --config PATH             Path to config.yml (default: dbt_yaml_generator/config.yml).
  --project-dir PATH        dbt project root (default: auto-detected nearest dbt_project.yml).
```

Excel path resolution order: `--excel-path` → `EXCEL_PATH` env var → `source.excel.path` in config.
