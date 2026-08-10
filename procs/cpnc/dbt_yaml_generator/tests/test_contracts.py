"""The independent data-contracts flow: sheet reading, YAML enrichment, both CLI passes."""

import os

import pytest

from dbt_yaml_generator import cli, contracts, yaml_utils
from dbt_yaml_generator.config import ConfigError

from dbt_yaml_generator.tests.helpers import make_config, write_config_yml


# --- reading the sheet ----------------------------------------------------------------

def test_flags_map_every_kind_of_cell(cfg, inventory_xlsx):
    flags, stats = contracts.read_contract_flags(cfg, inventory_xlsx)

    assert flags.get("bv_cpnc_load_date") is True                # real boolean TRUE
    assert flags.get("bv_cpnc_ref_parameter_mapping") is False   # text "FALSE"
    assert flags.get("bv_cim_load_date") is True                 # "yes"
    assert flags.get("bv_cim_no_decision") is False              # blank -> false
    assert flags.get("bv_cim_odd_flag") is False                 # "maybe" -> false
    assert flags.get("BV_CPNC_LOAD_DATE") is True                # case-insensitive
    assert flags.get("never_on_the_sheet") is None               # absent -> untouched

    assert len(flags) == 7
    assert stats.total_rows == 11
    assert stats.skipped_blank_model == 1
    assert stats.duplicate_rows == 3
    assert stats.blank_flag == ["bv_cim_no_decision"]
    assert stats.unrecognised == [("bv_cim_odd_flag", "maybe")]
    assert [name for name, _ in stats.conflicts] == ["bv_cpnc_clash"]


def test_path_column_tells_same_named_models_apart(cfg, inventory_xlsx):
    flags, _ = contracts.read_contract_flags(cfg, inventory_xlsx)

    assert flags.get("bv_cpnc_dual", "models/bnl_bvlt/cim3") is True
    assert flags.get("bv_cpnc_dual", "models/bnl_cpnc") is False
    assert flags.get("bv_cpnc_dual", "models/somewhere_else") is None
    # disagreeing rows with a missing path are never guessed at
    assert flags.get("bv_cpnc_clash", "models/bnl_bvlt") is None


def test_missing_sheet_lists_the_sheets_present(inventory_xlsx):
    with pytest.raises(ConfigError) as err:
        contracts.read_contract_flags(make_config(contracts={"sheet": "nope"}), inventory_xlsx)
    assert "inventory_overview" in str(err.value)


def test_missing_flag_column_lists_the_headers_present(inventory_xlsx):
    with pytest.raises(ConfigError) as err:
        contracts.read_contract_flags(
            make_config(contracts={"flag_column": "Contracted?"}), inventory_xlsx)
    message = str(err.value)
    assert "Contracted?" in message and "Is_Data_Contract_Enabled" in message


def test_no_contracts_section_says_what_to_add(inventory_xlsx):
    with pytest.raises(ConfigError) as err:
        contracts.read_contract_flags(make_config(contracts=False), inventory_xlsx)
    assert "contracts:" in str(err.value)


# --- writing the YAML -----------------------------------------------------------------

def _doc(text):
    return yaml_utils.make_yaml().load(text)


def test_apply_contract_preserves_the_rest_of_config():
    data = _doc(
        "version: 2\n"
        "models:\n"
        "  - name: m\n"
        "    config:\n"
        "      materialized: incremental\n"
        "      contract:\n"
        "        enforced: true\n"
        "    columns:\n"
        "      - name: a\n"
        "        data_type: varchar\n"
    )
    entry = yaml_utils.find_model_entry(data, "M")          # case-insensitive
    yaml_utils.apply_contract(entry, False)                  # true -> false
    assert entry["config"]["materialized"] == "incremental"
    assert entry["config"]["contract"]["enforced"] is False
    assert yaml_utils.columns_missing_data_type(entry) == []


def test_apply_contract_creates_the_config_block_before_columns():
    data = _doc("version: 2\nmodels:\n  - name: m\n    columns:\n      - name: a\n")
    entry = yaml_utils.find_model_entry(data, "m")
    yaml_utils.apply_contract(entry, True)
    assert entry["config"]["contract"]["enforced"] is True
    assert list(entry.keys()) == ["name", "config", "columns"]
    assert yaml_utils.columns_missing_data_type(entry) == ["a"]
    assert yaml_utils.find_model_entry(data, "other") is None


# --- end to end -----------------------------------------------------------------------

def _run(project_root, config_path, xlsx, *extra):
    argv = ["--source", "excel", "--excel-path", xlsx,
            "--config", config_path, "--project-dir", project_root]
    return cli.main(argv + list(extra))


def _yml_path(project_tree, model):
    return os.path.join(project_tree, "models", "bnl_bvlt", model + ".yml")


def _entry(project_tree, model):
    data, _ = yaml_utils.load_file(yaml_utils.make_yaml(), _yml_path(project_tree, model))
    return data["models"][0]


def test_normal_run_writes_no_contract(project_tree, inventory_xlsx, tmp_path):
    config_path = write_config_yml(project_tree, str(tmp_path / "config.yml"))
    assert _run(project_tree, config_path, inventory_xlsx) == 0
    assert "contract" not in _entry(project_tree, "bv_cpnc_load_date")["config"]


def test_apply_data_contracts_on_top_of_generation(project_tree, inventory_xlsx, tmp_path):
    config_path = write_config_yml(project_tree, str(tmp_path / "config.yml"))
    assert _run(project_tree, config_path, inventory_xlsx, "--apply-data-contracts") == 0

    load_date = _entry(project_tree, "bv_cpnc_load_date")
    assert load_date["config"]["contract"]["enforced"] is True
    assert load_date["config"]["materialized"] == "incremental"      # folder default kept
    columns = {c["name"]: c for c in load_date["columns"]}
    assert list(columns["CPNC_REPORTING_TS"]["data_tests"]) == ["not_null"]  # hand-authored
    assert str(columns["CPNC_REPORTING_TS"]["description"]) == "Column cpnc reporting ts."

    mapping = _entry(project_tree, "bv_cpnc_ref_parameter_mapping")
    assert mapping["config"]["contract"]["enforced"] is False        # written explicitly


def test_contracts_only_touches_nothing_else(project_tree, inventory_xlsx, tmp_path, capsys):
    config_path = write_config_yml(project_tree, str(tmp_path / "config.yml"))
    assert _run(project_tree, config_path, inventory_xlsx, "--contracts-only") == 0

    model = _entry(project_tree, "bv_cpnc_load_date")
    assert model["config"]["contract"]["enforced"] is True
    assert "materialized" not in model["config"]                     # no folder defaults
    assert str(model["description"]) == "Existing model description."
    columns = {c["name"]: c for c in model["columns"]}
    assert set(columns) == {"CPNC_REPORTING_TS"}                     # no inventory columns
    assert str(columns["CPNC_REPORTING_TS"]["description"]) == "OLD description."

    # a model with no <model>.yml is reported, never scaffolded
    assert not os.path.exists(_yml_path(project_tree, "bv_cpnc_ref_parameter_mapping"))
    out = capsys.readouterr().out
    assert "bv_cpnc_ref_parameter_mapping" in out
    assert "bv_cim_load_date" in out                                 # on the sheet, no .sql
    assert "CPNC_REPORTING_TS" in out                                # blank data_type warning


def test_contracts_only_is_idempotent(project_tree, inventory_xlsx, tmp_path):
    config_path = write_config_yml(project_tree, str(tmp_path / "config.yml"))
    path = _yml_path(project_tree, "bv_cpnc_load_date")
    _run(project_tree, config_path, inventory_xlsx, "--contracts-only")
    first = open(path, encoding="utf-8").read()
    _run(project_tree, config_path, inventory_xlsx, "--contracts-only")
    assert open(path, encoding="utf-8").read() == first


def test_contracts_only_dry_run_writes_nothing(project_tree, inventory_xlsx, tmp_path, capsys):
    config_path = write_config_yml(project_tree, str(tmp_path / "config.yml"))
    path = _yml_path(project_tree, "bv_cpnc_load_date")
    before = open(path, encoding="utf-8").read()
    _run(project_tree, config_path, inventory_xlsx, "--contracts-only", "--dry-run")
    assert open(path, encoding="utf-8").read() == before
    assert "enforced: true" in capsys.readouterr().out               # shown as a diff


def test_yml_without_a_matching_entry_is_reported(project_tree, inventory_xlsx, tmp_path,
                                                 capsys):
    other = _yml_path(project_tree, "bv_cpnc_ref_parameter_mapping")
    with open(other, "w", encoding="utf-8") as fh:
        fh.write("version: 2\nmodels:\n  - name: something_else\n")
    config_path = write_config_yml(project_tree, str(tmp_path / "config.yml"))
    _run(project_tree, config_path, inventory_xlsx, "--contracts-only")
    assert ".yml w/o a models: entry" in capsys.readouterr().out
    assert "something_else" in open(other, encoding="utf-8").read()


def test_contracts_sheet_override(project_tree, inventory_xlsx, tmp_path):
    config_path = write_config_yml(project_tree, str(tmp_path / "config.yml"))
    with pytest.raises(ConfigError):
        _run(project_tree, config_path, inventory_xlsx, "--contracts-only",
             "--contracts-sheet", "does_not_exist")
