"""Filesystem helpers: discover dbt models and their target YAML paths."""

import os
import re

# dim_customer_v1.sql / _v2.sql document ONE model `dim_customer` (dbt versioning).
_VERSION_SUFFIX = re.compile(r"_v\d+$")


def discover_models(project_root, folders):
    """Walk each configured folder recursively and return discovered models.

    Returns a list of dicts: {name, sql_path, yml_path, folder_rel} — one per distinct
    model (version suffixes collapsed). yml_path is <model>.yml co-located with the .sql.
    """
    seen = {}
    order = []
    for folder in folders:
        base = os.path.join(project_root, folder)
        if not os.path.isdir(base):
            continue
        for dirpath, _dirnames, filenames in os.walk(base):
            for fname in sorted(filenames):
                if not fname.endswith(".sql"):
                    continue
                model = _VERSION_SUFFIX.sub("", fname[:-4])
                if model in seen:
                    continue
                yml_path = os.path.join(dirpath, model + ".yml")
                folder_rel = os.path.relpath(dirpath, project_root).replace("\\", "/")
                seen[model] = True
                order.append(
                    {
                        "name": model,
                        "sql_path": os.path.join(dirpath, fname),
                        "yml_path": yml_path,
                        "folder_rel": folder_rel,
                    }
                )
    return order
