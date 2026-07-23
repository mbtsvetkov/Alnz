"""Snowflake connection + reads.

Credentials come exclusively from environment variables (never hardcoded, never
committed) — the same ones dbt Core's profiles.yml references via env_var(). The
snowflake.connector import is lazy so the offline test-suite can import this module
and exercise read_governance()/get_columns() against a mocked connection without the
driver installed.
"""

import os

REQUIRED_ENV = [
    "SNOWFLAKE_ACCOUNT",
    "SNOWFLAKE_USER",
    "SNOWFLAKE_ROLE",
    "SNOWFLAKE_WAREHOUSE",
    "SNOWFLAKE_DATABASE",
    "SNOWFLAKE_SCHEMA",
]


def load_dotenv(path):
    """Best-effort loader for a gitignored tools/.env (KEY=VALUE lines). Never overrides
    a variable already set in the real environment."""
    if not os.path.exists(path):
        return
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key, value = key.strip(), value.strip().strip('"').strip("'")
            os.environ.setdefault(key, value)


def _require_env():
    missing = [k for k in REQUIRED_ENV if not os.environ.get(k)]
    has_secret = os.environ.get("SNOWFLAKE_PASSWORD") or os.environ.get(
        "SNOWFLAKE_PRIVATE_KEY_PATH"
    )
    if not has_secret:
        missing.append("SNOWFLAKE_PASSWORD (or SNOWFLAKE_PRIVATE_KEY_PATH)")
    if missing:
        raise SystemExit(
            "Missing Snowflake connection env vars: "
            + ", ".join(missing)
            + "\nSet them in your shell (or tools/.env). See tools/README.md."
        )


def connect():
    """Open a Snowflake connection from env vars. Imports the driver lazily."""
    _require_env()
    import snowflake.connector  # lazy: only needed for real runs

    kwargs = dict(
        account=os.environ["SNOWFLAKE_ACCOUNT"],
        user=os.environ["SNOWFLAKE_USER"],
        role=os.environ["SNOWFLAKE_ROLE"],
        warehouse=os.environ["SNOWFLAKE_WAREHOUSE"],
        database=os.environ["SNOWFLAKE_DATABASE"],
        schema=os.environ["SNOWFLAKE_SCHEMA"],
    )
    if os.environ.get("SNOWFLAKE_PASSWORD"):
        kwargs["password"] = os.environ["SNOWFLAKE_PASSWORD"]
    else:
        kwargs["private_key_file"] = os.environ["SNOWFLAKE_PRIVATE_KEY_PATH"]
    return snowflake.connector.connect(**kwargs)


def read_governance(conn, table):
    """Read the governance table into {(model_lower, column_lower): {...}}."""
    cur = conn.cursor()
    try:
        cur.execute(
            "select MODEL_NAME, COLUMN_NAME, BUSINESS_NAME, BUSINESS_DEFINITION, PII "
            "from " + table
        )
        rows = cur.fetchall()
    finally:
        cur.close()

    governance = {}
    for model_name, column_name, business_name, business_definition, pii in rows:
        governance[(str(model_name).lower(), str(column_name).lower())] = {
            "business_name": business_name,
            "business_definition": business_definition,
            "pii": bool(pii),
        }
    return governance


def _format_data_type(data_type, numeric_precision, numeric_scale, char_length):
    """Turn INFORMATION_SCHEMA metadata into a dbt-friendly type string."""
    dt = (data_type or "").upper()
    if dt in ("NUMBER", "DECIMAL", "NUMERIC") and numeric_precision is not None:
        scale = numeric_scale or 0
        return "number({},{})".format(int(numeric_precision), int(scale))
    if dt in ("TEXT", "STRING", "VARCHAR", "CHAR", "CHARACTER"):
        if char_length:
            return "varchar({})".format(int(char_length))
        return "varchar"
    return dt.lower()


def get_columns(conn, model_name):
    """Columns of a built model as [(column_name, data_type_string), ...].

    Reads the connection's own DATABASE/SCHEMA (set at connect time) so it matches
    where dbt built the models. Returns [] if the object isn't found (not built yet).
    """
    database = os.environ["SNOWFLAKE_DATABASE"]
    schema = os.environ["SNOWFLAKE_SCHEMA"]
    cur = conn.cursor()
    try:
        cur.execute(
            "select COLUMN_NAME, DATA_TYPE, NUMERIC_PRECISION, NUMERIC_SCALE, "
            "CHARACTER_MAXIMUM_LENGTH "
            "from {}.INFORMATION_SCHEMA.COLUMNS "
            "where TABLE_SCHEMA = %s and TABLE_NAME = %s "
            "order by ORDINAL_POSITION".format(database),
            (schema.upper(), model_name.upper()),
        )
        rows = cur.fetchall()
    finally:
        cur.close()

    return [
        (name, _format_data_type(dt, prec, scale, clen))
        for (name, dt, prec, scale, clen) in rows
    ]
