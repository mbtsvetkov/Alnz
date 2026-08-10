"""Fill blank data_type values from Snowflake's INFORMATION_SCHEMA.COLUMNS.

Opt-in third tier (config source.snowflake.fill_missing_data_types, or
--fill-types-from-snowflake): when a column's data_type is still blank after
the inventory mapping and its data_type_fallback header, look up the type of
the model's real, physically-deployed table. Schema is derived from each
model's folder (matches dbt_project.yml's per-folder +schema convention);
database comes from SNOWFLAKE_DATABASE. One batched query covers every schema
needed, not one query per model/column.
"""

import os

from . import snowflake_source
from .config import ConfigError


def _schema_for_folder_rel(folder_rel):
    """Top-level segment under models/ — matches dbt_project.yml's +schema per folder.

    Returns None (a safe miss) when folder_rel isn't rooted under "models" or has no
    segment after it — never guesses a schema it can't be sure of.
    """
    parts = [p for p in folder_rel.replace("\\", "/").split("/") if p]
    if len(parts) >= 2 and parts[0].lower() == "models":
        return parts[1]
    return None


def _rows_to_lookup(rows):
    """rows: iterable of (schema, table, column, data_type) -> {(SCHEMA, TABLE, COLUMN): data_type}."""
    lookup = {}
    for schema, table, column, data_type in rows:
        if schema is None or table is None or column is None:
            continue
        key = (str(schema).upper(), str(table).upper(), str(column).upper())
        lookup[key] = data_type
    return lookup


def build_lookup(config, models):
    """Return a lookup(model_name, column_name) -> raw_type_or_"" closure.

    Runs one batched INFORMATION_SCHEMA.COLUMNS query across every schema any
    discovered model resolves to, then serves lookups from an in-memory dict.
    A miss (unknown model, table not deployed, column not found) returns ""
    -- same as if this tier didn't exist.
    """
    model_schema = {}
    schemas = set()
    for model in models:
        schema = _schema_for_folder_rel(model["folder_rel"])
        if not schema:
            continue
        model_schema[model["name"].lower()] = schema
        schemas.add(schema.upper())

    if not schemas:
        return lambda model_name, column_name: ""

    database = os.environ.get("SNOWFLAKE_DATABASE")
    if not database:
        raise ConfigError("Missing Snowflake env vars: SNOWFLAKE_DATABASE")

    schema_list = sorted(schemas)
    conn = snowflake_source.connect()
    try:
        cur = conn.cursor()
        try:
            placeholders = ", ".join(["%s"] * len(schema_list))
            query = (
                'SELECT TABLE_SCHEMA, TABLE_NAME, COLUMN_NAME, DATA_TYPE '
                'FROM "{database}".INFORMATION_SCHEMA.COLUMNS '
                'WHERE TABLE_SCHEMA IN ({placeholders})'
            ).format(database=database, placeholders=placeholders)
            cur.execute(query, tuple(schema_list))
            rows = cur.fetchall()
        finally:
            cur.close()
    finally:
        conn.close()

    lookup_dict = _rows_to_lookup(rows)

    def lookup(model_name, column_name):
        schema = model_schema.get(str(model_name).lower())
        if not schema:
            return ""
        key = (schema.upper(), str(model_name).upper(), str(column_name).upper())
        return lookup_dict.get(key) or ""

    return lookup
