# Handoff — column-metadata YAML generator (in progress)

Cross-machine handoff for the `gen_column_meta` feature. Full design is in
[IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md); usage in [README.md](README.md).

## What this feature is

A standalone Python code-gen tool that writes a per-column governance block
(`config: meta: {business_name, business_definition, pii}`) into the dbt schema YAML,
sourced from a **Snowflake governance table**. Two passes: **scaffold** missing model
YAML (columns from `INFORMATION_SCHEMA`) + **enrich** governed columns. Runs on dbt
Core / local / CI; dbt Cloud and dbt Core both consume the committed YAML.

## Status — DONE

- `tools/gen_column_meta.py` — CLI (scaffold + enrich, `--dry-run`, `--no-scaffold`, summary)
- `tools/libs/{yaml_utils,model_utils,snowflake_utils}.py`
- `tools/config/meta_dirs.yml` — per-folder scope
- `tools/tests/` — offline suite with a **mocked** Snowflake cursor (+ fixtures)
- `tools/requirements.txt`, `tools/requirements-dev.txt`, `tools/README.md`
- `docs/governance/COLUMN_DICTIONARY.sql` — CREATE TABLE + seed rows

## Status — REMAINING (resume here)

1. **Run the offline suite** (no Snowflake needed):
   ```bash
   python -m venv .venv && source .venv/Scripts/activate   # PowerShell: .venv\Scripts\activate
   pip install -r tools/requirements-dev.txt
   pytest tools/tests
   ```
   Fix anything red. This was the exact step paused at handoff — deps were **not** yet installed.
2. **Real-Snowflake end-to-end** (needs a connection):
   - Run `docs/governance/COLUMN_DICTIONARY.sql` in Snowflake.
   - Set the `SNOWFLAKE_*` env vars (see README), `dbt deps && dbt seed && dbt run`.
   - `python tools/gen_column_meta.py --dry-run` → review; then run for real.
   - `dbt parse && dbt docs generate` → confirm meta shows in the catalog. `git diff` = additions only.
3. Optional: CI job running `pytest tools/tests` (free) and/or `--dry-run --no-scaffold` drift check.

## Resume prompt for Claude on the other machine

> Read tools/HANDOFF.md and tools/IMPLEMENTATION_PLAN.md, then continue: install
> tools/requirements-dev.txt into a venv and run `pytest tools/tests`, fixing any failures.

## Notes

- Credentials are env-vars only — never in the script, never committed.
- `.venv*/` is git-ignored; each machine builds its own venv.
