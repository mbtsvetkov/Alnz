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


# --- contracts sheet: ONE ROW PER MODEL (the inventory_overview shape) ----------------
CONTRACT_HEADERS = [
    "#", "model_name", "schema", "path", "reference", "description(cpnc AI generated)",
    "where_conditions", "status", "remark", "Is_Data_Contract_Enabled",
]

CONTRACT_ROWS = [
    # in the project tree, real boolean TRUE
    {"#": 1, "model_name": "bv_cpnc_load_date", "schema": "bnl_cpnc", "path": "bnl_cpnc",
     "status": "pending", "Is_Data_Contract_Enabled": True},
    # in the project tree, text FALSE
    {"#": 2, "model_name": "bv_cpnc_ref_parameter_mapping", "schema": "bnl_cpnc",
     "path": "bnl_cpnc", "status": "pending", "Is_Data_Contract_Enabled": "FALSE"},
    # no .sql in the tree -> reported, never written
    {"#": 3, "model_name": "bv_cim_load_date", "schema": "bnl_bvlt",
     "path": "bnl_bvlt/cim3", "Is_Data_Contract_Enabled": "yes"},
    {"#": 4, "model_name": "bv_cim_no_decision", "schema": "bnl_bvlt",
     "path": "bnl_bvlt/cim3", "Is_Data_Contract_Enabled": ""},        # blank -> false
    {"#": 5, "model_name": "bv_cim_odd_flag", "schema": "bnl_bvlt",
     "path": "bnl_bvlt/cim3", "Is_Data_Contract_Enabled": "maybe"},   # unrecognised -> false
    # same model name in two schemas, disagreeing -> told apart by path
    {"#": 6, "model_name": "bv_cpnc_dual", "schema": "bnl_bvlt",
     "path": "bnl_bvlt/cim3", "Is_Data_Contract_Enabled": True},
    {"#": 6, "model_name": "bv_cpnc_dual", "schema": "bnl_cpnc",
     "path": "bnl_cpnc", "Is_Data_Contract_Enabled": False},
    # same model name, disagreeing, one path missing -> conflict, left untouched
    {"#": 7, "model_name": "bv_cpnc_clash", "path": "bnl_bvlt",
     "Is_Data_Contract_Enabled": True},
    {"#": 7, "model_name": "bv_cpnc_clash", "path": "", "Is_Data_Contract_Enabled": False},
    # blank model_name -> skipped
    {"#": 8, "model_name": "", "path": "bnl_cpnc", "Is_Data_Contract_Enabled": True},
    # duplicate that AGREES with row 1 -> counted, collapses
    {"#": 9, "model_name": "bv_cpnc_load_date", "schema": "bnl_cpnc", "path": "bnl_cpnc",
     "Is_Data_Contract_Enabled": "y"},
]

CONTRACTS_CFG = {
    "sheet": "inventory_overview",
    "header_row": 1,
    "model_column": "model_name",
    "flag_column": "Is_Data_Contract_Enabled",
    "path_column": "path",
}


def row_to_list(row, headers=None):
    return [row.get(h, "") for h in (headers or HEADERS)]


def make_config(extra_meta=False, fallback=False, contracts=True):
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
    if contracts:
        data["contracts"] = dict(CONTRACTS_CFG)
        if isinstance(contracts, dict):      # per-test overrides
            data["contracts"].update(contracts)
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
        "contracts:\n"
        "  sheet: inventory_overview\n"
        "  header_row: 1\n"
        "  model_column: model_name\n"
        "  flag_column: Is_Data_Contract_Enabled\n"
        "  path_column: path\n"
    )
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(content)
    return path
