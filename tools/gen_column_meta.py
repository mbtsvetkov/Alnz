#!/usr/bin/env python3
"""Generate/enrich dbt schema YAML with a governance block per column.

Two passes over the model folders listed in tools/config/meta_dirs.yml:

  1. Scaffold  - for a model with no YAML coverage yet, read its columns from
                 Snowflake INFORMATION_SCHEMA and append a fresh `models:` entry.
  2. Enrich    - inject/refresh `config: meta:` (business_name, business_definition,
                 pii) on every governed column, sourced from a Snowflake table.

Credentials come from env vars only (see tools/README.md). Runs on dbt Core / local /
CI; both dbt Cloud and dbt Core then consume the committed YAML identically.

Usage:
    python tools/gen_column_meta.py [--config PATH] [--table NAME] [--no-scaffold] [--dry-run]
"""

import argparse
import difflib
import os
import sys

# Make `libs` importable regardless of the caller's working directory.
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from libs import model_utils, snowflake_utils, yaml_utils  # noqa: E402
from ruamel.yaml.comments import CommentedSeq  # noqa: E402

_REPO_ROOT = os.path.dirname(_HERE)
_DEFAULT_CONFIG = os.path.join(_HERE, "config", "meta_dirs.yml")
_DEFAULT_TABLE = "GOVERNANCE.COLUMN_DICTIONARY"


class Stats:
    def __init__(self):
        self.scaffolded = []            # model names
        self.could_not_scaffold = []    # model names (not built in Snowflake)
        self.files_changed = []         # paths
        self.enriched_columns = 0
        self.columns_without_governance = []   # (model, column)
        self.matched_keys = set()              # (model, column)


def load_folders(config_path):
    yaml = yaml_utils.make_yaml()
    data, _ = yaml_utils.load_file(yaml, config_path)
    if not data or "folders" not in data:
        raise SystemExit("No 'folders:' found in {}".format(config_path))
    folders = []
    for entry in data["folders"]:
        # Accept both "models/marts" and {path: models/marts, ...} forms.
        path = entry["path"] if isinstance(entry, dict) else entry
        folders.append(str(path))
    return folders


def resolve(folder):
    """Resolve a config folder (repo-relative) to an absolute path."""
    return folder if os.path.isabs(folder) else os.path.join(_REPO_ROOT, folder)


def print_diff(path, before, after):
    rel = os.path.relpath(path, _REPO_ROOT)
    diff = difflib.unified_diff(
        (before or "").splitlines(keepends=True),
        after.splitlines(keepends=True),
        fromfile="a/" + rel,
        tofile="b/" + rel,
    )
    sys.stdout.writelines(diff)


def process_folder(folder_rel, conn, governance, table, no_scaffold, dry_run, stats):
    folder = resolve(folder_rel)
    if not os.path.isdir(folder):
        print("  ! skipping missing folder: {}".format(folder_rel))
        return

    yaml = yaml_utils.make_yaml()
    schema_paths = model_utils.get_schema_files(folder)
    target_path = model_utils.default_schema_file(folder)

    # Load every schema file once; remember original on-disk text for diffing.
    loaded = {}          # path -> data
    original_text = {}   # path -> str | None
    documented = set()
    for path in schema_paths:
        data, text = yaml_utils.load_file(yaml, path)
        loaded[path] = data
        original_text[path] = text
        documented |= yaml_utils.documented_model_names(data)

    # ---- Scaffold pass -----------------------------------------------------
    if not no_scaffold:
        undocumented = [m for m in model_utils.get_sql_model_names(folder)
                        if m not in documented]
        if undocumented:
            target_data = loaded.get(target_path)
            if target_data is None:
                target_data = yaml_utils.new_schema_doc()
                loaded[target_path] = target_data
                original_text.setdefault(target_path, None)
            if target_data.get("models") is None:
                target_data["models"] = CommentedSeq()
            for model_name in undocumented:
                columns = snowflake_utils.get_columns(conn, model_name)
                if not columns:
                    stats.could_not_scaffold.append(model_name)
                    print("  ! cannot scaffold '{}' - not found in INFORMATION_SCHEMA "
                          "(build it first with: dbt run -s {})".format(model_name, model_name))
                    continue
                entry = yaml_utils.build_model_entry(model_name, columns, governance)
                target_data["models"].append(entry)
                stats.scaffolded.append(model_name)

    # ---- Enrich pass -------------------------------------------------------
    for path, data in loaded.items():
        if not data or "models" not in data:
            continue
        yaml_utils.inject_meta_into_doc(data, governance, stats)
        after = yaml_utils.dump_to_string(yaml, data)
        before = original_text.get(path)
        if after == before:
            continue
        if dry_run:
            print_diff(path, before, after)
        else:
            yaml_utils.write_file(yaml, path, data)
        stats.files_changed.append(path)


def print_summary(stats, governance, dry_run):
    unmatched_gov = sorted(set(governance) - stats.matched_keys)
    print("\n" + "=" * 60)
    print("Summary" + (" (dry-run, nothing written)" if dry_run else ""))
    print("=" * 60)
    print("  models scaffolded          : {}".format(len(stats.scaffolded)))
    if stats.scaffolded:
        print("      " + ", ".join(stats.scaffolded))
    if stats.could_not_scaffold:
        print("  could NOT scaffold (unbuilt): {}".format(", ".join(stats.could_not_scaffold)))
    print("  files changed              : {}".format(len(set(stats.files_changed))))
    print("  columns enriched           : {}".format(stats.enriched_columns))
    print("  YAML columns w/o governance: {}".format(len(stats.columns_without_governance)))
    print("  governance rows unmatched  : {}".format(len(unmatched_gov)))
    if unmatched_gov:
        for model, column in unmatched_gov:
            print("      {}.{}".format(model, column))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--config", default=_DEFAULT_CONFIG,
                        help="Path to meta_dirs.yml (default: tools/config/meta_dirs.yml)")
    parser.add_argument("--table", default=_DEFAULT_TABLE,
                        help="Governance table (default: {})".format(_DEFAULT_TABLE))
    parser.add_argument("--no-scaffold", action="store_true",
                        help="Enrich only; do not create entries for undocumented models")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print a unified diff of every change; write nothing")
    args = parser.parse_args(argv)

    snowflake_utils.load_dotenv(os.path.join(_HERE, ".env"))
    folders = load_folders(args.config)

    conn = snowflake_utils.connect()
    try:
        governance = snowflake_utils.read_governance(conn, args.table)
        print("Loaded {} governance rows from {}".format(len(governance), args.table))
        stats = Stats()
        for folder in folders:
            print("Processing {}".format(folder))
            process_folder(folder, conn, governance, args.table,
                           args.no_scaffold, args.dry_run, stats)
    finally:
        conn.close()

    print_summary(stats, governance, args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
