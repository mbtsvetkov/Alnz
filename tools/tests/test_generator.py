"""End-to-end tests for process_folder() with a mocked Snowflake connection."""

import os

import gen_column_meta as gcm
from libs import yaml_utils

from fakes import FakeConnection

GOVERNANCE = {
    ("existing_model", "id"): {
        "business_name": "Identifier",
        "business_definition": "Row identifier.",
        "pii": False,
    },
    ("new_model", "id"): {
        "business_name": "Identifier",
        "business_definition": "Row identifier.",
        "pii": False,
    },
    ("new_model", "email"): {
        "business_name": "Email Address",
        "business_definition": "Contact email.",
        "pii": True,
    },
}

# INFORMATION_SCHEMA rows: (COLUMN_NAME, DATA_TYPE, PRECISION, SCALE, CHAR_LEN)
COLUMNS = {
    "new_model": [
        ("ID", "TEXT", None, None, None),
        ("EMAIL", "TEXT", None, None, None),
        ("AMOUNT", "NUMBER", 10, 2, None),
    ]
}

EXISTING_YML = """\
version: 2

# Keep this comment.
models:
  - name: existing_model
    description: "An already-documented model."
    columns:
      - name: id
        description: "Row id."
        data_tests:
          - not_null
"""


def _setup_folder(tmp_path):
    folder = tmp_path / "widgets"
    folder.mkdir()
    (folder / "existing_model.sql").write_text("select 1 as id", encoding="utf-8")
    (folder / "new_model.sql").write_text(
        "select 1 as id, 'a' as email, 1 as amount", encoding="utf-8"
    )
    (folder / "_widgets.yml").write_text(EXISTING_YML, encoding="utf-8")
    return folder


def _run(folder, monkeypatch, no_scaffold=False, dry_run=False):
    monkeypatch.setenv("SNOWFLAKE_DATABASE", "DB")
    monkeypatch.setenv("SNOWFLAKE_SCHEMA", "dev")
    conn = FakeConnection(list(GOVERNANCE), columns_by_model=COLUMNS)
    stats = gcm.Stats()
    gcm.process_folder(
        str(folder), conn, GOVERNANCE, "GOVERNANCE.COLUMN_DICTIONARY",
        no_scaffold=no_scaffold, dry_run=dry_run, stats=stats,
    )
    return stats


def test_scaffold_and_enrich(tmp_path, monkeypatch):
    folder = _setup_folder(tmp_path)
    stats = _run(folder, monkeypatch)

    assert stats.scaffolded == ["new_model"]

    yaml = yaml_utils.make_yaml()
    data, _ = yaml_utils.load_file(yaml, str(folder / "_widgets.yml"))
    models = {m["name"]: m for m in data["models"]}

    # Existing model enriched in place.
    existing_cols = {c["name"]: c for c in models["existing_model"]["columns"]}
    assert existing_cols["id"]["config"]["meta"]["business_name"] == "Identifier"
    # Existing comment + test preserved.
    out = yaml_utils.dump_to_string(yaml, data)
    assert "Keep this comment." in out
    assert "- not_null" in out

    # New model scaffolded with columns, data_type and meta.
    new_cols = {c["name"]: c for c in models["new_model"]["columns"]}
    assert set(new_cols) == {"id", "email", "amount"}
    assert new_cols["amount"]["data_type"] == "number(10,2)"
    assert new_cols["email"]["config"]["meta"]["pii"] is True
    assert "config" not in new_cols["amount"]  # ungoverned column: no meta


def test_no_scaffold_leaves_undocumented_alone(tmp_path, monkeypatch):
    folder = _setup_folder(tmp_path)
    stats = _run(folder, monkeypatch, no_scaffold=True)

    assert stats.scaffolded == []
    yaml = yaml_utils.make_yaml()
    data, _ = yaml_utils.load_file(yaml, str(folder / "_widgets.yml"))
    names = {m["name"] for m in data["models"]}
    assert names == {"existing_model"}  # new_model NOT added


def test_dry_run_writes_nothing(tmp_path, monkeypatch):
    folder = _setup_folder(tmp_path)
    before = (folder / "_widgets.yml").read_text(encoding="utf-8")
    _run(folder, monkeypatch, dry_run=True)
    after = (folder / "_widgets.yml").read_text(encoding="utf-8")
    assert before == after


def test_second_run_is_idempotent(tmp_path, monkeypatch):
    folder = _setup_folder(tmp_path)
    _run(folder, monkeypatch)
    after_first = (folder / "_widgets.yml").read_text(encoding="utf-8")
    stats = _run(folder, monkeypatch)
    after_second = (folder / "_widgets.yml").read_text(encoding="utf-8")
    assert after_first == after_second
    assert stats.files_changed == []  # nothing rewritten on the second pass
