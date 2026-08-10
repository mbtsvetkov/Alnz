"""Inventory mapping + YAML build/merge logic (no Excel, no Snowflake needed)."""

from dbt_yaml_generator import inventory, yaml_utils

from dbt_yaml_generator.tests.helpers import make_config


def _inv(cfg, raw_rows):
    rows, headers = raw_rows
    return inventory.build_inventory(cfg, rows, headers)


def test_inventory_mapping_and_skips(cfg, raw_rows):
    by_model, stats = _inv(cfg, raw_rows)
    # sentinel (blank cpnc_column_name) skipped; duplicate counted, not re-added
    assert stats.skipped_blank_column == 1
    assert len(stats.duplicate_keys) == 1
    load = by_model["bv_cpnc_load_date"]
    assert [r.column_name for r in load] == ["CPNC_REPORTING_TS", "CPNC_REPORTING_TS_KEY"]
    # type normalization + blank type (fallback off)
    assert load[0].data_type == "timestamp"
    assert load[1].data_type == ""
    assert ("bv_cpnc_load_date", "CPNC_REPORTING_TS_KEY") in stats.blank_data_type
    # boolean + string coercion
    assert load[0].meta["pii"] is False
    ref = by_model["bv_cpnc_ref_parameter_mapping"][0]
    assert ref.meta["pii"] is True


def test_fallback_fills_blank_type(raw_rows):
    cfg = make_config(fallback=True)
    by_model, _ = _inv(cfg, raw_rows)
    # CPNC_REPORTING_TS_KEY had blank cpnc_data_type; fallback prev_data_type=VARCHAR -> varchar
    key_col = by_model["bv_cpnc_load_date"][1]
    assert key_col.data_type == "varchar"


def test_snowflake_lookup_fills_blank_type_when_fallback_off(cfg, raw_rows):
    """Third tier only fires when the mapped column AND fallback are both blank."""
    rows, headers = raw_rows
    calls = []

    def stub_lookup(model_name, column_name):
        calls.append((model_name, column_name))
        if column_name == "CPNC_REPORTING_TS_KEY":
            return "NUMBER"
        return ""

    by_model, stats = inventory.build_inventory(cfg, rows, headers, snowflake_type_lookup=stub_lookup)
    key_col = by_model["bv_cpnc_load_date"][1]
    assert key_col.data_type == "number"  # normalized through type_map, same as other tiers
    assert ("bv_cpnc_load_date", "CPNC_REPORTING_TS_KEY") in stats.filled_from_snowflake
    assert ("bv_cpnc_load_date", "CPNC_REPORTING_TS_KEY") not in stats.blank_data_type
    # a column with a non-blank mapped data_type never calls the lookup for its own value
    assert ("bv_cpnc_load_date", "CPNC_REPORTING_TS") not in calls


def test_snowflake_lookup_miss_stays_blank(cfg, raw_rows):
    rows, headers = raw_rows
    by_model, stats = inventory.build_inventory(
        cfg, rows, headers, snowflake_type_lookup=lambda m, c: "")
    key_col = by_model["bv_cpnc_load_date"][1]
    assert key_col.data_type == ""
    assert stats.filled_from_snowflake == []
    assert ("bv_cpnc_load_date", "CPNC_REPORTING_TS_KEY") in stats.blank_data_type


def test_build_new_file_structure(cfg, raw_rows):
    by_model, _ = _inv(cfg, raw_rows)
    records = by_model["bv_cpnc_load_date"]
    data, extra = yaml_utils.build_or_merge(None, "bv_cpnc_load_date", records, {"materialized": "view"})
    out = yaml_utils.dump_to_string(yaml_utils.make_yaml(), data)

    assert "version: 2" in out
    assert "name: bv_cpnc_load_date" in out
    assert "materialized: view" in out                       # model-level config from defaults
    assert 'business_name: "Reporting Timestamp"' in out     # meta string double-quoted
    assert "pii: false" in out                               # boolean bare
    assert "data_type: timestamp" in out                     # normalized, unquoted
    assert extra == []


def test_meta_is_extensible(raw_rows):
    cfg = make_config(extra_meta=True)                       # adds 'remark'
    by_model, _ = inventory.build_inventory(cfg, raw_rows[0], raw_rows[1])
    records = by_model["bv_cpnc_ref_parameter_mapping"]
    data, _ = yaml_utils.build_or_merge(None, "bv_cpnc_ref_parameter_mapping", records, {})
    out = yaml_utils.dump_to_string(yaml_utils.make_yaml(), data)
    assert 'remark: "done"' in out


def test_merge_excel_wins_but_keeps_tests(cfg, raw_rows):
    """Existing column with a data_test: description/type/meta update, test preserved."""
    existing = (
        "version: 2\n"
        "models:\n"
        "  - name: bv_cpnc_load_date\n"
        '    description: "Existing model description."\n'
        "    columns:\n"
        "      - name: CPNC_REPORTING_TS\n"
        '        description: "OLD description."\n'
        "        data_tests:\n"
        "          - not_null\n"
    )
    yaml = yaml_utils.make_yaml()
    data = yaml.load(existing)
    by_model, _ = _inv(cfg, raw_rows)
    records = by_model["bv_cpnc_load_date"]

    merged, extra = yaml_utils.build_or_merge(data, "bv_cpnc_load_date", records, {"materialized": "view"})
    out = yaml_utils.dump_to_string(yaml, merged)

    assert "OLD description." not in out                      # Excel overwrote it
    assert "Column cpnc reporting ts." in out
    assert "- not_null" in out                                # data_test preserved
    assert "Existing model description." in out               # model description preserved
    assert "materialized: view" in out                        # model config overlaid
    # the previously-existing column is in the inventory, so nothing 'extra'
    assert extra == []


def test_idempotent_second_run(cfg, raw_rows):
    by_model, _ = _inv(cfg, raw_rows)
    records = by_model["bv_cpnc_load_date"]
    yaml = yaml_utils.make_yaml()

    data1, _ = yaml_utils.build_or_merge(None, "bv_cpnc_load_date", records, {"materialized": "view"})
    text1 = yaml_utils.dump_to_string(yaml, data1)
    # feed the produced YAML back in
    data2, _ = yaml_utils.build_or_merge(yaml.load(text1), "bv_cpnc_load_date", records, {"materialized": "view"})
    text2 = yaml_utils.dump_to_string(yaml, data2)
    assert text1 == text2
