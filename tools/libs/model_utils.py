"""Filesystem helpers: which models live in a folder, which schema files document them."""

import os
import re

# A versioned model dim_customer_v1.sql / dim_customer_v2.sql documents ONE model
# named `dim_customer` (dbt's versioning). Strip the _v<N> suffix to get the model name.
_VERSION_SUFFIX = re.compile(r"_v\d+$")


def get_sql_model_names(folder):
    """Distinct dbt model names from the .sql files in a folder (version suffix stripped)."""
    names = []
    for fname in sorted(os.listdir(folder)):
        if fname.endswith(".sql"):
            name = _VERSION_SUFFIX.sub("", fname[:-4])
            names.append(name)
    return list(dict.fromkeys(names))  # dedupe, keep order


def get_schema_files(folder):
    """Paths of dbt schema files (``_*.yml`` / ``_*.yaml``) in a folder."""
    out = []
    for fname in sorted(os.listdir(folder)):
        if fname.startswith("_") and (fname.endswith(".yml") or fname.endswith(".yaml")):
            out.append(os.path.join(folder, fname))
    return out


def default_schema_file(folder):
    """The canonical schema file for a folder, e.g. models/staging -> .../\_staging.yml."""
    return os.path.join(folder, "_" + os.path.basename(os.path.normpath(folder)) + ".yml")
