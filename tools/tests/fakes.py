"""In-memory stand-ins for a snowflake.connector connection/cursor.

Let the tests exercise read_governance() / get_columns() and the full generator with
no live account and without the snowflake driver installed.
"""


class FakeCursor:
    def __init__(self, governance_rows, columns_by_model):
        self._governance_rows = governance_rows
        self._columns_by_model = columns_by_model
        self._result = []

    def execute(self, sql, params=None):
        if "INFORMATION_SCHEMA" in sql.upper():
            model = params[1].lower()  # params == (schema, TABLE_NAME)
            self._result = self._columns_by_model.get(model, [])
        else:
            self._result = self._governance_rows
        return self

    def fetchall(self):
        return self._result

    def close(self):
        pass


class FakeConnection:
    def __init__(self, governance_rows, columns_by_model=None):
        self._governance_rows = governance_rows
        self._columns_by_model = columns_by_model or {}

    def cursor(self):
        return FakeCursor(self._governance_rows, self._columns_by_model)

    def close(self):
        pass
