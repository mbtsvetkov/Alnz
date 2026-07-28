"""Excel reading: headers, values, and clear errors (no SharePoint)."""

import pytest

from dbt_yaml_generator import excel_source
from dbt_yaml_generator.config import ConfigError


def test_read_rows_headers_and_values(inventory_xlsx):
    rows, headers = excel_source.read_rows({"sheet": "Sheet1", "header_row": 1}, inventory_xlsx)
    assert "cpnc_model_name" in headers and "cpnc_column_name" in headers
    first = rows[0]
    assert first["cpnc_model_name"] == "bv_cpnc_load_date"
    assert first["cpnc_column_name"] == "CPNC_REPORTING_TS"
    assert first["cpnc_data_type"] == "TIMESTAMP"


def test_missing_sheet_errors(inventory_xlsx):
    with pytest.raises(ConfigError) as e:
        excel_source.read_rows({"sheet": "DoesNotExist", "header_row": 1}, inventory_xlsx)
    assert "not found" in str(e.value)


def test_missing_file_errors():
    with pytest.raises(ConfigError):
        excel_source.read_rows({"sheet": "Sheet1"}, "no_such_file.xlsx")
