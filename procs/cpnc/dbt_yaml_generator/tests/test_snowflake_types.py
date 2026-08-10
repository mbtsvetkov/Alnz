"""Pure-logic tests for snowflake_types.py -- no snowflake.connector, no network."""

from dbt_yaml_generator import snowflake_types


def test_schema_for_folder_rel():
    assert snowflake_types._schema_for_folder_rel("models/bnl_bvlt/cim3/cim3_ans") == "bnl_bvlt"
    assert snowflake_types._schema_for_folder_rel("models\\bnl_cpnc\\cpnc_ans") == "bnl_cpnc"
    assert snowflake_types._schema_for_folder_rel("models") is None
    assert snowflake_types._schema_for_folder_rel("") is None


def test_rows_to_lookup_uppercases_keys():
    rows = [
        ("bnl_bvlt", "bv_cim_load_date", "CIM3_REPORTING_TS", "TIMESTAMP_NTZ"),
        (None, "x", "y", "TEXT"),  # malformed row: skipped
    ]
    lookup = snowflake_types._rows_to_lookup(rows)
    assert lookup[("BNL_BVLT", "BV_CIM_LOAD_DATE", "CIM3_REPORTING_TS")] == "TIMESTAMP_NTZ"
    assert len(lookup) == 1


def test_build_lookup_no_models_returns_empty_closure():
    lookup = snowflake_types.build_lookup(config=None, models=[])
    assert lookup("anything", "anything") == ""


def test_build_lookup_closure_behavior(monkeypatch):
    """Stub the connection + query so this stays fully offline."""

    class FakeCursor:
        def execute(self, query, params):
            self.params = params

        def fetchall(self):
            return [
                ("BNL_BVLT", "BV_CIM_LOAD_DATE", "CIM3_REPORTING_TS", "TIMESTAMP_NTZ"),
            ]

        def close(self):
            pass

    class FakeConn:
        def cursor(self):
            return FakeCursor()

        def close(self):
            pass

    monkeypatch.setenv("SNOWFLAKE_DATABASE", "DBAREA")
    monkeypatch.setattr(snowflake_types.snowflake_source, "connect", lambda: FakeConn())

    models = [
        {"name": "bv_cim_load_date", "folder_rel": "models/bnl_bvlt/cim3"},
    ]
    lookup = snowflake_types.build_lookup(config=None, models=models)

    assert lookup("bv_cim_load_date", "CIM3_REPORTING_TS") == "TIMESTAMP_NTZ"
    assert lookup("bv_cim_load_date", "NO_SUCH_COLUMN") == ""
    assert lookup("no_such_model", "CIM3_REPORTING_TS") == ""


def test_build_lookup_missing_database_env_raises(monkeypatch):
    from dbt_yaml_generator.config import ConfigError

    monkeypatch.delenv("SNOWFLAKE_DATABASE", raising=False)
    models = [{"name": "bv_cim_load_date", "folder_rel": "models/bnl_bvlt/cim3"}]
    try:
        snowflake_types.build_lookup(config=None, models=models)
        assert False, "expected ConfigError"
    except ConfigError:
        pass
