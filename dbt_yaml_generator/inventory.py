"""Turn raw inventory rows (from any source) into per-model column records.

One place applies the config mapping, type normalization and meta coercion, so the
Excel and Snowflake sources behave identically downstream.
"""

from .config import ConfigError

_TRUE = {"true", "yes", "1", "y", "t"}


class ColumnRecord:
    __slots__ = ("model_name", "column_name", "description", "data_type", "meta")

    def __init__(self, model_name, column_name, description, data_type, meta):
        self.model_name = model_name
        self.column_name = column_name
        self.description = description
        self.data_type = data_type
        self.meta = meta  # ordered dict: {meta_key: coerced_value}


class InventoryStats:
    def __init__(self):
        self.total_rows = 0
        self.skipped_blank_model = 0
        self.skipped_blank_column = 0
        self.duplicate_keys = []      # (model, column)
        self.blank_data_type = []     # (model, column)


def _s(value):
    """Trimmed string, or '' for None/blank."""
    if value is None:
        return ""
    return str(value).strip()


def _coerce_boolean(value):
    return _s(value).lower() in _TRUE


def _require_headers(config, headers):
    """Fail early if any mapped/meta source header is absent from the sheet/table."""
    present = {str(h).strip() for h in headers}
    needed = list(config.mapping.values())
    needed += [mf.source for mf in config.meta_fields]
    if config.data_type_fallback:
        needed.append(config.data_type_fallback)
    missing = [h for h in dict.fromkeys(needed) if h not in present]
    if missing:
        raise ConfigError(
            "Source is missing expected column(s): {}\nColumns present: {}".format(
                ", ".join(missing), ", ".join(sorted(present))
            )
        )


def build_inventory(config, rows, headers):
    """Return (by_model, stats).

    by_model: {model_name_lower: [ColumnRecord, ...]} in source row order.
    Rows with a blank mapped model_name or column_name are skipped (counted in stats).
    """
    _require_headers(config, headers)
    m = config.mapping
    type_map = config.type_normalization
    fallback = config.data_type_fallback

    by_model = {}
    seen_keys = set()
    stats = InventoryStats()

    for row in rows:
        stats.total_rows += 1
        model_name = _s(row.get(m["model_name"]))
        column_name = _s(row.get(m["column_name"]))
        if not model_name:
            stats.skipped_blank_model += 1
            continue
        if not column_name:
            stats.skipped_blank_column += 1
            continue

        key = (model_name.lower(), column_name.lower())
        if key in seen_keys:
            stats.duplicate_keys.append((model_name, column_name))
            continue
        seen_keys.add(key)

        # data_type: mapped column, optional fallback, then normalize.
        raw_type = _s(row.get(m["data_type"]))
        if not raw_type and fallback:
            raw_type = _s(row.get(fallback))
        data_type = type_map.get(raw_type.upper(), raw_type.lower()) if raw_type else ""
        if not data_type:
            stats.blank_data_type.append((model_name, column_name))

        # meta: coerce each configured field.
        meta = {}
        for mf in config.meta_fields:
            raw = row.get(mf.source)
            meta[mf.key] = _coerce_boolean(raw) if mf.is_boolean else _s(raw)

        record = ColumnRecord(
            model_name=model_name,
            column_name=column_name,
            description=_s(row.get(m["description"])),
            data_type=data_type,
            meta=meta,
        )
        by_model.setdefault(model_name.lower(), []).append(record)

    return by_model, stats


def load_inventory(config, source_name, excel_path=None):
    """Dispatch to the chosen source, then build the per-model inventory."""
    source_name = source_name or config.default_source
    if source_name == "excel":
        from . import excel_source
        path = excel_path or config.excel.get("path") or None
        rows, headers = excel_source.read_rows(config.excel, path)
    elif source_name == "snowflake":
        from . import snowflake_source
        rows, headers = snowflake_source.read_rows(config.snowflake)
    else:
        raise ConfigError("Unknown --source '{}' (expected excel or snowflake).".format(source_name))
    return build_inventory(config, rows, headers)
