"""Read the column inventory from a Snowflake table (forward-ready alternate source).

Reuses the SAME SNOWFLAKE_* env vars dbt's profiles.yml references — a separate
connection, but no new credentials. The snowflake.connector import is lazy so the
package installs and its Excel path + tests run without the driver present.

Returns (rows, headers) in the same shape as excel_source.read_rows().
"""

import os

from .config import ConfigError

_ENV = [
    "SNOWFLAKE_ACCOUNT",
    "SNOWFLAKE_USER",
    "SNOWFLAKE_ROLE",
    "SNOWFLAKE_WAREHOUSE",
    "SNOWFLAKE_DATABASE",
    "SNOWFLAKE_SCHEMA",
]


def _require_env():
    missing = [k for k in _ENV if not os.environ.get(k)]
    if not (os.environ.get("SNOWFLAKE_PASSWORD") or os.environ.get("SNOWFLAKE_PRIVATE_KEY_PATH")):
        missing.append("SNOWFLAKE_PASSWORD (or SNOWFLAKE_PRIVATE_KEY_PATH)")
    if missing:
        raise ConfigError("Missing Snowflake env vars: " + ", ".join(missing))


def connect():
    """Open a Snowflake connection from SNOWFLAKE_* env vars.

    Shared by the --source snowflake path and the INFORMATION_SCHEMA data-type
    lookup. Always authenticates as username_password_mfa: this account requires
    MFA, and the connector caches the MFA token locally (via seed_mfa.py) so a
    valid cached token lets this connect silently, with no passcode prompt.
    """
    _require_env()

    try:
        import snowflake.connector  # lazy
    except ImportError:
        raise ConfigError(
            "snowflake-connector-python not installed. "
            "Uncomment it in requirements.txt and reinstall for --source snowflake."
        )

    kwargs = dict(
        account=os.environ["SNOWFLAKE_ACCOUNT"],
        user=os.environ["SNOWFLAKE_USER"],
        role=os.environ["SNOWFLAKE_ROLE"],
        warehouse=os.environ["SNOWFLAKE_WAREHOUSE"],
        database=os.environ["SNOWFLAKE_DATABASE"],
        schema=os.environ["SNOWFLAKE_SCHEMA"],
        authenticator="username_password_mfa",
    )
    if os.environ.get("SNOWFLAKE_PASSWORD"):
        kwargs["password"] = os.environ["SNOWFLAKE_PASSWORD"]
    else:
        kwargs["private_key_file"] = os.environ["SNOWFLAKE_PRIVATE_KEY_PATH"]

    try:
        return snowflake.connector.connect(**kwargs)
    except snowflake.connector.errors.Error as exc:
        raise ConfigError(
            "Snowflake MFA authentication failed: {}\n"
            "Re-run 'python seed_mfa.py' to refresh the cached MFA token, then retry.".format(exc)
        )


def read_rows(snowflake_cfg):
    table = (snowflake_cfg or {}).get("table")
    if not table:
        raise ConfigError("config: source.snowflake.table is required for --source snowflake.")

    conn = connect()
    try:
        cur = conn.cursor()
        try:
            cur.execute("select * from " + table)
            headers = [c[0] for c in cur.description]
            data = cur.fetchall()
        finally:
            cur.close()
    finally:
        conn.close()

    rows = [dict(zip(headers, values)) for values in data]
    return rows, headers
