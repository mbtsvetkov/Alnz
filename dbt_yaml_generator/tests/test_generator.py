"""End-to-end: run the CLI against the fixture .xlsx + a temp dbt project."""

import os

from dbt_yaml_generator import cli, yaml_utils

from dbt_yaml_generator.tests.helpers import write_config_yml


def _run(project_root, config_path, xlsx, dry_run=False):
    argv = ["--source", "excel", "--excel-path", xlsx,
            "--config", config_path, "--project-dir", project_root]
    if dry_run:
        argv.append("--dry-run")
    return cli.main(argv)


def test_generate_end_to_end(project_tree, inventory_xlsx, tmp_path):
    config_path = write_config_yml(project_tree, str(tmp_path / "config.yml"))
    rc = _run(project_tree, config_path, inventory_xlsx)
    assert rc == 0

    yaml = yaml_utils.make_yaml()
    mdir = os.path.join(project_tree, "models", "bnl_bvlt")

    # bv_cpnc_load_date.yml: pre-existing test preserved, description overwritten, meta added,
    # second column appended, sentinel excluded.
    data, _ = yaml_utils.load_file(yaml, os.path.join(mdir, "bv_cpnc_load_date.yml"))
    model = data["models"][0]
    assert model["config"]["materialized"] == "incremental"       # per-folder default
    cols = {c["name"]: c for c in model["columns"]}
    assert set(cols) == {"CPNC_REPORTING_TS", "CPNC_REPORTING_TS_KEY"}
    assert "NOT_APPLICABLE" not in str(cols)                       # sentinel row skipped
    assert list(cols["CPNC_REPORTING_TS"]["data_tests"]) == ["not_null"]   # kept
    assert str(cols["CPNC_REPORTING_TS"]["description"]) == "Column cpnc reporting ts."
    assert cols["CPNC_REPORTING_TS"]["config"]["meta"]["pii"] is False

    # second model file created fresh
    data2, _ = yaml_utils.load_file(yaml, os.path.join(mdir, "bv_cpnc_ref_parameter_mapping.yml"))
    m2 = data2["models"][0]
    vf = {c["name"]: c for c in m2["columns"]}["VALID_FROM"]
    assert vf["config"]["meta"]["pii"] is True
    assert str(vf["description"]) == "Column valid from."


def test_rerun_is_idempotent(project_tree, inventory_xlsx, tmp_path):
    config_path = write_config_yml(project_tree, str(tmp_path / "config.yml"))
    _run(project_tree, config_path, inventory_xlsx)
    path = os.path.join(project_tree, "models", "bnl_bvlt", "bv_cpnc_load_date.yml")
    after_first = open(path, encoding="utf-8").read()
    _run(project_tree, config_path, inventory_xlsx)
    after_second = open(path, encoding="utf-8").read()
    assert after_first == after_second
