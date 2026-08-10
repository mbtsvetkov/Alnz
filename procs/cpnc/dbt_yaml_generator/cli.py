"""Command-line entry point: discover models, read the inventory, write <model>.yml."""

import argparse
import difflib
import os
import sys

from . import inventory, model_utils, yaml_utils
from .config import find_project_root, load_config

_HERE = os.path.dirname(os.path.abspath(__file__))
_DEFAULT_CONFIG = os.path.join(_HERE, "config.yml")


def _load_dotenv(path):
    """Load KEY=VALUE lines from a local .env without overriding the real environment."""
    if not os.path.isfile(path):
        return
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def _print_diff(project_root, path, before, after):
    rel = os.path.relpath(path, project_root)
    sys.stdout.writelines(
        difflib.unified_diff(
            (before or "").splitlines(keepends=True),
            after.splitlines(keepends=True),
            fromfile="a/" + rel,
            tofile="b/" + rel,
        )
    )


def build_arg_parser():
    p = argparse.ArgumentParser(
        prog="python -m dbt_yaml_generator",
        description="Generate per-model dbt schema YAML from a column-inventory source.",
    )
    p.add_argument("--source", choices=["excel", "snowflake"], default=None,
                   help="Inventory source (default: config source.default).")
    p.add_argument("--excel-path", default=os.environ.get("EXCEL_PATH"),
                   help="Path to the .xlsx (excel source). Overrides config/env.")
    p.add_argument("--config", default=_DEFAULT_CONFIG,
                   help="Path to config.yml (default: alongside this package).")
    p.add_argument("--project-dir", default=None,
                   help="dbt project root. Default: auto-detect (nearest dbt_project.yml).")
    p.add_argument("--dry-run", action="store_true",
                   help="Print a unified diff of every change; write nothing.")
    p.add_argument("--fill-types-from-snowflake", action="store_true",
                   help="Also fill still-blank data_type values from this target's "
                        "INFORMATION_SCHEMA.COLUMNS (default: config source.snowflake."
                        "fill_missing_data_types).")
    return p


def main(argv=None):
    args = build_arg_parser().parse_args(argv)
    _load_dotenv(os.path.join(_HERE, ".env"))

    project_root = find_project_root(override=args.project_dir)
    config = load_config(args.config)

    models = model_utils.discover_models(project_root, config.folders)

    snowflake_type_lookup = None
    if args.fill_types_from_snowflake or config.snowflake_fill_missing_data_types:
        from . import snowflake_types
        snowflake_type_lookup = snowflake_types.build_lookup(config, models)

    by_model, inv_stats = inventory.load_inventory(
        config, args.source, args.excel_path, snowflake_type_lookup=snowflake_type_lookup)
    print("Inventory: {} rows, {} models with columns (source: {})".format(
        inv_stats.total_rows, len(by_model), args.source or config.default_source))

    yaml = yaml_utils.make_yaml()

    written, no_inventory, extra_cols_report = [], [], []
    matched_model_keys = set()

    for model in models:
        records = by_model.get(model["name"].lower())
        if not records:
            no_inventory.append(model["name"])
            continue
        matched_model_keys.add(model["name"].lower())

        existing_data, before = yaml_utils.load_file(yaml, model["yml_path"])
        defaults = config.defaults_for(model["folder_rel"])
        data, extra = yaml_utils.build_or_merge(existing_data, model["name"], records, defaults)
        after = yaml_utils.dump_to_string(yaml, data)

        if extra:
            extra_cols_report.append((model["name"], extra))
        if after == before:
            continue
        if args.dry_run:
            _print_diff(project_root, model["yml_path"], before, after)
        else:
            yaml_utils.write_file(yaml, model["yml_path"], data)
        written.append(model["name"])

    inventory_without_sql = sorted(set(by_model) - matched_model_keys)
    _print_summary(inv_stats, written, no_inventory, inventory_without_sql,
                   extra_cols_report, args.dry_run)
    return 0


def _print_summary(inv_stats, written, no_inventory, inventory_without_sql,
                   extra_cols_report, dry_run):
    print("\n" + "=" * 64)
    print("Summary" + (" (dry-run — nothing written)" if dry_run else ""))
    print("=" * 64)
    print("  YAML files {}        : {}".format(
        "to change" if dry_run else "written", len(written)))
    for name in written:
        print("      {}.yml".format(name))
    print("  .sql models w/o inventory rows : {}".format(len(no_inventory)))
    for name in no_inventory:
        print("      {}".format(name))
    print("  inventory models w/o a .sql    : {}".format(len(inventory_without_sql)))
    for name in inventory_without_sql:
        print("      {}".format(name))
    print("  rows skipped (blank model)     : {}".format(inv_stats.skipped_blank_model))
    print("  rows skipped (blank column)    : {}".format(inv_stats.skipped_blank_column))
    print("  duplicate (model,column) rows  : {}".format(len(inv_stats.duplicate_keys)))
    print("  data_types filled from Snowflake: {}".format(len(inv_stats.filled_from_snowflake)))
    for model, col in inv_stats.filled_from_snowflake:
        print("      {}.{}".format(model, col))
    print("  columns with blank data_type   : {}".format(len(inv_stats.blank_data_type)))
    for model, col in inv_stats.blank_data_type:
        print("      {}.{}".format(model, col))
    if extra_cols_report:
        print("  existing columns kept but not in inventory:")
        for model, cols in extra_cols_report:
            print("      {}: {}".format(model, ", ".join(cols)))
