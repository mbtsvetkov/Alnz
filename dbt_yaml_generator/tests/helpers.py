"""Non-fixture test helpers (importable as dbt_yaml_generator.tests.helpers)."""

from dbt_yaml_generator.config import Config

HEADERS = [
    "#", "prev_model_name", "cpnc_model_name", "prev_column_name", "cpnc_column_name",
    "prev_column_description", "cpnc_column_description", "prev_data_type", "cpnc_data_type",
    "business_name", "business_definition", "pii", "Test", "remark", "investication",
]

# Each dict is one sheet row (only the columns we care about; others default blank).
ROWS = [
    {  # normal row, full cpnc data
        "prev_model_name": "bv_cim_load_date", "cpnc_model_name": "bv_cpnc_load_date",
        "prev_column_name": "CIM3_REPORTING_TS", "cpnc_column_name": "CPNC_REPORTING_TS",
        "cpnc_column_description": "Column cpnc reporting ts.", "prev_data_type": "TIMESTAMP_NTZ",
        "cpnc_data_type": "TIMESTAMP", "business_name": "Reporting Timestamp",
        "business_definition": "Timestamp the record was reported.", "pii": False,
    },
    {  # cpnc_data_type BLANK (fallback off -> stays blank); meta blank
        "prev_model_name": "bv_cim_load_date", "cpnc_model_name": "bv_cpnc_load_date",
        "prev_column_name": "CIM3_REPORTING_TS_KEY", "cpnc_column_name": "CPNC_REPORTING_TS_KEY",
        "cpnc_column_description": "Column cpnc reporting ts key.", "prev_data_type": "VARCHAR",
        "cpnc_data_type": "",
    },
    {  # SENTINEL: cpnc_column_name blank -> must be skipped
        "prev_model_name": "bv_cim_load_date", "cpnc_model_name": "bv_cpnc_load_date",
        "prev_column_name": "CIM3_DATE_NOT_APPLICABLE_888", "cpnc_column_name": "",
        "prev_data_type": "TIMESTAMP_NTZ",
    },
    {  # second model; pii TRUE; remark set
        "prev_model_name": "bv_cim_ref_parameter_mapping",
        "cpnc_model_name": "bv_cpnc_ref_parameter_mapping",
        "prev_column_name": "VALID_FROM", "cpnc_column_name": "VALID_FROM",
        "cpnc_column_description": "Column valid from.", "cpnc_data_type": "TEXT",
        "business_name": "Valid From", "business_definition": "Start of validity.",
        "pii": True, "remark": "done",
    },
    {  # DUPLICATE of row 1 (same model+column) -> counted, not re-emitted
        "cpnc_model_name": "bv_cpnc_load_date", "cpnc_column_name": "CPNC_REPORTING_TS",
        "cpnc_column_description": "dup", "cpnc_data_type": "TIMESTAMP",
    },
]


def row_to_list(row):
    return [row.get(h, "") for h in HEADERS]


def make_config(extra_meta=False, fallback=False):
    meta_fields = [
        {"key": "business_name", "source": "business_name", "type": "string"},
        {"key": "business_definition", "source": "business_definition", "type": "string"},
        {"key": "pii", "source": "pii", "type": "boolean"},
    ]
    if extra_meta:
        meta_fields.append({"key": "remark", "source": "remark", "type": "string"})
    source = {
        "default": "excel",
        "excel": {"sheet": "Sheet1", "header_row": 1},
        "snowflake": {"table": "GOVERNANCE.COLUMN_INVENTORY"},
        "mapping": {
            "model_name": "cpnc_model_name",
            "column_name": "cpnc_column_name",
            "description": "cpnc_column_description",
            "data_type": "cpnc_data_type",
        },
        "type_normalization": {
            "TEXT": "varchar", "VARCHAR": "varchar",
            "TIMESTAMP_NTZ": "timestamp_ntz", "TIMESTAMP": "timestamp", "NUMBER": "number",
        },
    }
    if fallback:
        source["data_type_fallback"] = "prev_data_type"
    data = {
        "folders": ["models"],
        "source": source,
        "meta_fields": meta_fields,
        "folder_defaults": {"models": {"materialized": "view"}},
    }
    return Config(data, "test-config")


def write_config_yml(root, path):
    content = (
        "folders: [models/bnl_bvlt]\n"
        "source:\n"
        "  default: excel\n"
        "  excel: {sheet: Sheet1, header_row: 1}\n"
        "  mapping:\n"
        "    model_name: cpnc_model_name\n"
        "    column_name: cpnc_column_name\n"
        "    description: cpnc_column_description\n"
        "    data_type: cpnc_data_type\n"
        "  type_normalization: {TEXT: varchar, TIMESTAMP: timestamp}\n"
        "meta_fields:\n"
        "  - {key: business_name, source: business_name, type: string}\n"
        "  - {key: business_definition, source: business_definition, type: string}\n"
        "  - {key: pii, source: pii, type: boolean}\n"
        "folder_defaults:\n"
        "  models/bnl_bvlt: {materialized: incremental}\n"
    )
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(content)
    return path
