"""Offline unit tests for the YAML logic (no Snowflake, no driver)."""

import os

import gen_column_meta as gcm
from libs import snowflake_utils, yaml_utils

from fakes import FakeConnection

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "sample_schema.yml")

GOVERNANCE = {
    ("stg_customers", "customer_id"): {
        "business_name": "Customer ID",
        "business_definition": "Natural business key identifying a customer.",
        "pii": False,
    },
    ("stg_customers", "email"): {
        "business_name": "Email Address",
        "business_definition": "Primary contact email address of the customer.",
        "pii": True,
    },
}


def _load_fixture():
    yaml = yaml_utils.make_yaml()
    data, text = yaml_utils.load_file(yaml, FIXTURE)
    return yaml, data, text


def test_inject_adds_meta_and_preserves_comments():
    yaml, data, original = _load_fixture()
    stats = gcm.Stats()
    yaml_utils.inject_meta_into_doc(data, GOVERNANCE, stats)
    out = yaml_utils.dump_to_string(yaml, data)

    # Governance values injected as config: meta:
    assert "config:" in out
    assert "business_name: \"Email Address\"" in out
    assert "business_definition: \"Primary contact email address of the customer.\"" in out
    assert "pii: true" in out
    assert "pii: false" in out  # customer_id
    # Hand-authored comment and block scalar survive the round-trip.
    assert "FIXTURE COMMENT: this heading must survive a round-trip untouched." in out
    assert "Multi-line block scalar that must be preserved." in out
    # Existing content untouched.
    assert "- unique" in out and "- not_null" in out
    # Two columns enriched; the third recorded as ungoverned.
    assert stats.enriched_columns == 2
    assert ("stg_customers", "undocumented_col") in stats.columns_without_governance


def test_inject_is_idempotent():
    yaml, data, _ = _load_fixture()
    yaml_utils.inject_meta_into_doc(data, GOVERNANCE, gcm.Stats())
    first = yaml_utils.dump_to_string(yaml, data)
    yaml_utils.inject_meta_into_doc(data, GOVERNANCE, gcm.Stats())
    second = yaml_utils.dump_to_string(yaml, data)
    assert first == second  # no duplicated config/meta on a second run


def test_inject_updates_changed_value():
    yaml, data, _ = _load_fixture()
    yaml_utils.inject_meta_into_doc(data, GOVERNANCE, gcm.Stats())
    changed = dict(GOVERNANCE)
    changed[("stg_customers", "email")] = {
        "business_name": "Email Address",
        "business_definition": "UPDATED definition.",
        "pii": True,
    }
    yaml_utils.inject_meta_into_doc(data, changed, gcm.Stats())
    out = yaml_utils.dump_to_string(yaml, data)
    assert "UPDATED definition." in out
    assert out.count("business_name: \"Email Address\"") == 1  # updated, not duplicated


def test_build_model_entry_shape():
    columns = [("CUSTOMER_ID", "varchar"), ("SIGNUP_DATE", "date")]
    gov = {
        ("stg_new", "customer_id"): {
            "business_name": "Customer ID",
            "business_definition": "Natural key.",
            "pii": False,
        }
    }
    entry = yaml_utils.build_model_entry("stg_new", columns, gov)
    assert entry["name"] == "stg_new"
    assert entry["columns"][0]["name"] == "customer_id"          # lower-cased
    assert entry["columns"][0]["data_type"] == "varchar"
    assert entry["columns"][0]["config"]["meta"]["business_name"] == "Customer ID"
    # Ungoverned column gets name + data_type but no config block.
    assert "config" not in entry["columns"][1]


def test_read_governance_parses_rows():
    rows = [
        ("STG_CUSTOMERS", "EMAIL", "Email Address", "Contact email.", True),
        ("dim_product", "price", "List Price", "Catalogue price.", False),
    ]
    conn = FakeConnection(rows)
    gov = snowflake_utils.read_governance(conn, "GOVERNANCE.COLUMN_DICTIONARY")
    assert gov[("stg_customers", "email")]["pii"] is True
    assert gov[("dim_product", "price")]["business_name"] == "List Price"


def test_get_columns_formats_types(monkeypatch):
    monkeypatch.setenv("SNOWFLAKE_DATABASE", "DB")
    monkeypatch.setenv("SNOWFLAKE_SCHEMA", "dev")
    cols = {
        "fact_orders": [
            ("ORDER_ID", "TEXT", None, None, None),
            ("TOTAL_AMOUNT", "NUMBER", 38, 2, None),
            ("ORDER_DATE", "DATE", None, None, None),
        ]
    }
    conn = FakeConnection([], columns_by_model=cols)
    result = snowflake_utils.get_columns(conn, "fact_orders")
    assert result == [
        ("ORDER_ID", "varchar"),
        ("TOTAL_AMOUNT", "number(38,2)"),
        ("ORDER_DATE", "date"),
    ]
