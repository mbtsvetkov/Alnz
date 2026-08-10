"""Fixtures: a sample inventory workbook, a temp dbt project, and a Config."""

import pytest

from dbt_yaml_generator.tests.helpers import (
    CONTRACT_HEADERS, CONTRACT_ROWS, HEADERS, ROWS, make_config, row_to_list,
)


@pytest.fixture(scope="session")
def inventory_xlsx(tmp_path_factory):
    """The real workbook shape: a per-column sheet plus the per-model contracts sheet."""
    from openpyxl import Workbook
    path = tmp_path_factory.mktemp("xlsx") / "inventory.xlsx"
    wb = Workbook()
    ws = wb.active
    ws.title = "Sheet1"
    ws.append(HEADERS)
    for row in ROWS:
        ws.append(row_to_list(row))

    overview = wb.create_sheet("inventory_overview")
    overview.append(CONTRACT_HEADERS)
    for row in CONTRACT_ROWS:
        overview.append(row_to_list(row, CONTRACT_HEADERS))

    wb.save(str(path))
    return str(path)


@pytest.fixture
def raw_rows():
    """The row dicts as inventory.build_inventory expects (header -> value)."""
    return [dict(r) for r in ROWS], list(HEADERS)


@pytest.fixture
def cfg():
    return make_config()


@pytest.fixture
def project_tree(tmp_path):
    """A minimal dbt project with two models and one pre-existing <model>.yml."""
    root = tmp_path / "repo"
    (root / "models" / "bnl_bvlt").mkdir(parents=True)
    (root / "dbt_project.yml").write_text("name: test\nprofile: default\n", encoding="utf-8")

    mdir = root / "models" / "bnl_bvlt"
    (mdir / "bv_cpnc_load_date.sql").write_text("select 1", encoding="utf-8")
    (mdir / "bv_cpnc_ref_parameter_mapping.sql").write_text("select 1", encoding="utf-8")
    (mdir / "bv_cpnc_load_date.yml").write_text(
        "version: 2\n"
        "models:\n"
        "  - name: bv_cpnc_load_date\n"
        '    description: "Existing model description."\n'
        "    columns:\n"
        "      - name: CPNC_REPORTING_TS\n"
        '        description: "OLD description."\n'
        "        data_tests:\n"
        "          - not_null\n",
        encoding="utf-8",
    )
    return str(root)
