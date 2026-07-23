# `gen_column_meta` — column governance metadata for dbt YAML

Generates and enriches the dbt schema files (`_*.yml`) with a per-column governance
block, sourced from a Snowflake table:

```yaml
columns:
  - name: email
    description: "Contact email."
    data_type: varchar
    config:
      meta:
        business_name: "Email Address"
        business_definition: "Primary contact email address of the customer."
        pii: true
```

Two passes over the folders listed in [config/meta_dirs.yml](config/meta_dirs.yml):

1. **Scaffold** — for a model with no YAML coverage, read its columns from Snowflake
   `INFORMATION_SCHEMA` and append a fresh `models:` entry.
2. **Enrich** — inject/refresh `config: meta:` on every governed column.

## Where it runs, and how "dbt Cloud + dbt Core" is satisfied

This is a **developer / CI code-generation step**. It runs under **dbt Core, locally, or in
CI** — not *inside* dbt Cloud (dbt Cloud has no Python runtime and keeps its Snowflake
connection in the UI). You run it, commit the updated `_*.yml`, and then **both dbt Cloud and
dbt Core consume that identical committed YAML** (docs, catalog, `meta`-driven tooling). The
generated files are plain dbt YAML with no runtime dependency on this tool.

## Credentials — never in the script, never committed

The connection comes only from **environment variables**, the same ones dbt Core's
`~/.dbt/profiles.yml` references via `env_var(...)`:

| var | example |
|---|---|
| `SNOWFLAKE_ACCOUNT` | `ab12345.eu-central-1` |
| `SNOWFLAKE_USER` | `martin` |
| `SNOWFLAKE_PASSWORD` | *(or `SNOWFLAKE_PRIVATE_KEY_PATH`)* |
| `SNOWFLAKE_ROLE` | `TRANSFORMER` |
| `SNOWFLAKE_WAREHOUSE` | `DBT_WH` |
| `SNOWFLAKE_DATABASE` | `REVELATOR_ALL` |
| `SNOWFLAKE_SCHEMA` | *(your dbt dev schema)* |

Set them in your shell, or drop them in a gitignored `tools/.env` (`KEY=VALUE` per line) which
the script auto-loads. The script fails fast with a clear message if any are missing.

## One-time local setup (dbt Core — free)

dbt Core is open-source and free; Snowflake offers a 30-day free trial if you need an account.

```bash
python -m venv .venv
source .venv/Scripts/activate          # Windows Git Bash;  .venv\Scripts\activate on PowerShell
pip install dbt-snowflake              # dbt Core + Snowflake adapter
pip install -r tools/requirements.txt  # ruamel.yaml + snowflake-connector-python

# export the SNOWFLAKE_* vars above, then point ~/.dbt/profiles.yml at them:
#   default:
#     target: dev
#     outputs:
#       dev:
#         type: snowflake
#         account:   "{{ env_var('SNOWFLAKE_ACCOUNT') }}"
#         user:      "{{ env_var('SNOWFLAKE_USER') }}"
#         password:  "{{ env_var('SNOWFLAKE_PASSWORD') }}"
#         role:      "{{ env_var('SNOWFLAKE_ROLE') }}"
#         warehouse: "{{ env_var('SNOWFLAKE_WAREHOUSE') }}"
#         database:  "{{ env_var('SNOWFLAKE_DATABASE') }}"
#         schema:    "{{ env_var('SNOWFLAKE_SCHEMA') }}"
#         threads: 4

dbt debug   # confirms the same creds reach Snowflake
```

## Create the governance table

Run [../docs/governance/COLUMN_DICTIONARY.sql](../docs/governance/COLUMN_DICTIONARY.sql) in a
Snowflake worksheet. It creates `GOVERNANCE.COLUMN_DICTIONARY` and seeds rows for the current
models. Columns: `MODEL_NAME, COLUMN_NAME, BUSINESS_NAME, BUSINESS_DEFINITION, PII`
(keyed on model + column, matched case-insensitively; versioned models use the base name).

## Running the generator

```bash
# build the models first so INFORMATION_SCHEMA knows their columns (needed for scaffolding)
dbt deps && dbt seed && dbt run

python tools/gen_column_meta.py --dry-run          # preview a unified diff, write nothing
python tools/gen_column_meta.py                     # scaffold missing + enrich
python tools/gen_column_meta.py --no-scaffold       # enrich only (no build dependency)
python tools/gen_column_meta.py --table GOVERNANCE.MY_DICT   # override the table
```

Then `dbt parse && dbt docs generate` to see `business_name` / `business_definition` / `pii`
on columns in the catalog. Re-running is idempotent (a second run reports "no changes").

> **Scaffold caveat:** scaffolding a model requires it to be **built** in the target schema
> first (`dbt run -s <model>`). Unbuilt models are logged as "cannot scaffold" and skipped;
> enrich mode has no such dependency.

## Tests

```bash
pip install -r tools/requirements-dev.txt
pytest tools/tests
```

The suite uses a **mocked Snowflake cursor** — scaffolding, meta injection, comment
preservation, idempotency and drift are all asserted with no live account. This is what CI can
run for free.
