"""Command-line entry point: discover models, read the inventory, write <model>.yml."""

import argparse
import difflib
import os
import sys

from . import contracts, inventory, model_utils, yaml_utils
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
    p.add_argument("--apply-data-contracts", action="store_true",
                   help="Also write config.contract.enforced per model from the contracts "
                        "sheet (config contracts.*). Off unless asked for.")
    p.add_argument("--contracts-only", action="store_true",
                   help="Apply data contracts and NOTHING else: no columns, descriptions, "
                        "meta or folder defaults are touched. Implies --apply-data-contracts.")
    p.add_argument("--contracts-sheet", default=None,
                   help="Override contracts.sheet for this run.")
    return p


def _warn_folder_default_contract(config):
    """folder_defaults.contract fights the sheet — the sheet wins per model, so say so once."""
    folders = [f for f, d in config.folder_defaults.items()
               if isinstance(d, dict) and "contract" in d]
    if folders:
        print("WARNING folder_defaults sets 'contract' for {} — the contracts sheet "
              "decides per model and overrides it.".format(", ".join(str(f) for f in folders)))


def _apply_contract_to(model, data, flags, stats):
    """Write config.contract.enforced for one model from the sheet, or record why not."""
    name = model["name"]
    if name not in flags:
        return  # not on the sheet -> no contract key is written or removed
    enforced = flags.get(name, model["folder_rel"])
    if enforced is None:
        stats.unresolved.append(name)
        return
    entry = yaml_utils.find_model_entry(data, name)
    if entry is None:
        stats.no_entry.append(name)
        return
    yaml_utils.apply_contract(entry, enforced)
    if not enforced:
        stats.applied_false.append(name)
        return
    stats.applied_true.append(name)
    missing = yaml_utils.columns_missing_data_type(entry)
    if missing:
        stats.missing_data_type.append((name, missing))


def main(argv=None):
    args = build_arg_parser().parse_args(argv)
    _load_dotenv(os.path.join(_HERE, ".env"))

    project_root = find_project_root(override=args.project_dir)
    config = load_config(args.config)
    apply_contracts = args.apply_data_contracts or args.contracts_only

    models = model_utils.discover_models(project_root, config.folders)

    contract_flags, contract_stats = None, None
    if apply_contracts:
        contract_flags, contract_stats = contracts.read_contract_flags(
            config, args.excel_path, sheet_override=args.contracts_sheet)
        print("Contracts: {} rows, {} models (sheet: {})".format(
            contract_stats.total_rows, len(contract_flags), contract_flags.sheet))
        _warn_folder_default_contract(config)

    if args.contracts_only:
        # No column inventory is read at all — nothing but the contract key is touched.
        by_model, inv_stats = {}, inventory.InventoryStats()
    else:
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
        if args.contracts_only:
            if model["name"] not in contract_flags:
                continue
            data, before = yaml_utils.load_file(yaml, model["yml_path"])
            if data is None:
                # A contract needs a columns: list, so nothing is scaffolded here.
                contract_stats.no_yml.append(model["name"])
                continue
        else:
            records = by_model.get(model["name"].lower())
            if not records:
                no_inventory.append(model["name"])
                continue
            matched_model_keys.add(model["name"].lower())

            existing_data, before = yaml_utils.load_file(yaml, model["yml_path"])
            defaults = config.defaults_for(model["folder_rel"])
            data, extra = yaml_utils.build_or_merge(
                existing_data, model["name"], records, defaults)
            if extra:
                extra_cols_report.append((model["name"], extra))

        # After build_or_merge, so the sheet always wins over folder_defaults.contract.
        if apply_contracts:
            _apply_contract_to(model, data, contract_flags, contract_stats)

        after = yaml_utils.dump_to_string(yaml, data)
        if after == before:
            continue
        if args.dry_run:
            _print_diff(project_root, model["yml_path"], before, after)
        else:
            yaml_utils.write_file(yaml, model["yml_path"], data)
        written.append(model["name"])

    if apply_contracts:
        discovered = {m["name"].lower() for m in models}
        contract_stats.no_sql = [n for n in contract_flags.model_names()
                                 if n.lower() not in discovered]

    inventory_without_sql = sorted(set(by_model) - matched_model_keys)
    _print_summary(inv_stats, written, no_inventory, inventory_without_sql,
                   extra_cols_report, args.dry_run, contract_stats=contract_stats,
                   contracts_only=args.contracts_only)
    return 0


def _print_summary(inv_stats, written, no_inventory, inventory_without_sql,
                   extra_cols_report, dry_run, contract_stats=None, contracts_only=False):
    print("\n" + "=" * 64)
    print("Summary" + (" (dry-run — nothing written)" if dry_run else ""))
    print("=" * 64)
    print("  YAML files {}        : {}".format(
        "to change" if dry_run else "written", len(written)))
    for name in written:
        print("      {}.yml".format(name))
    if not contracts_only:
        print("  .sql models w/o inventory rows : {}".format(len(no_inventory)))
        for name in no_inventory:
            print("      {}".format(name))
        print("  inventory models w/o a .sql    : {}".format(len(inventory_without_sql)))
        for name in inventory_without_sql:
            print("      {}".format(name))
        print("  rows skipped (blank model)     : {}".format(inv_stats.skipped_blank_model))
        print("  rows skipped (blank column)    : {}".format(inv_stats.skipped_blank_column))
        print("  duplicate (model,column) rows  : {}".format(len(inv_stats.duplicate_keys)))
        print("  data_types filled from Snowflake: {}".format(
            len(inv_stats.filled_from_snowflake)))
        for model, col in inv_stats.filled_from_snowflake:
            print("      {}.{}".format(model, col))
        print("  columns with blank data_type   : {}".format(len(inv_stats.blank_data_type)))
        for model, col in inv_stats.blank_data_type:
            print("      {}.{}".format(model, col))
    if contract_stats is not None:
        _print_contract_summary(contract_stats)
    if extra_cols_report:
        print("  existing columns kept but not in inventory:")
        for model, cols in extra_cols_report:
            print("      {}: {}".format(model, ", ".join(cols)))


def _print_contract_summary(s):
    print("  " + "-" * 62)
    print("  Data contracts (sheet-driven)")
    print("  contract enforced=true         : {}".format(len(s.applied_true)))
    for name in s.applied_true:
        print("      {}".format(name))
    print("  contract enforced=false        : {}".format(len(s.applied_false)))
    print("  flag blank -> false            : {}".format(len(s.blank_flag)))
    print("  unrecognised flag values       : {}".format(len(s.unrecognised)))
    for name, raw in s.unrecognised:
        print("      {}: '{}' (treated as false)".format(name, raw))
    print("  duplicate sheet rows           : {}".format(s.duplicate_rows))
    print("  sheet models w/o a .sql        : {}".format(len(s.no_sql)))
    for name in s.no_sql:
        print("      {}".format(name))
    if s.conflicts:
        print("  CONFLICTING rows (left as-is)  : {}".format(len(s.conflicts)))
        for name, values in s.conflicts:
            print("      {}: {}".format(name, ", ".join(values)))
    if s.unresolved:
        print("  undecidable models (left as-is): {}".format(len(s.unresolved)))
        for name in s.unresolved:
            print("      {}".format(name))
    if s.no_yml:
        print("  models w/o a .yml (skipped)    : {}".format(len(s.no_yml)))
        for name in s.no_yml:
            print("      {}".format(name))
    if s.no_entry:
        print("  .yml w/o a models: entry       : {}".format(len(s.no_entry)))
        for name in s.no_entry:
            print("      {}".format(name))
    if s.missing_data_type:
        print("  WARNING contracted models with blank data_type "
              "(dbt build will fail until filled):")
        for name, cols in s.missing_data_type:
            print("      {}: {}".format(name, ", ".join(cols)))
