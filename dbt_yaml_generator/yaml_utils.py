"""Build and merge per-model dbt schema YAML with ruamel round-trip.

Rules (locked with the user):
  * model-level `config` comes from per-folder defaults (overlaid each run).
  * columns: Excel wins for description / data_type / config.meta; existing
    data_tests / constraints are PRESERVED; columns absent from Excel are kept.
  * strings double-quoted; booleans bare; comments/quoting of untouched nodes preserved.
"""

import io

from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap, CommentedSeq
from ruamel.yaml.scalarstring import DoubleQuotedScalarString as DQ


def make_yaml():
    yaml = YAML()
    yaml.preserve_quotes = True
    yaml.indent(mapping=2, sequence=4, offset=2)
    yaml.width = 4096
    return yaml


def load_file(yaml, path):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            text = fh.read()
    except FileNotFoundError:
        return None, None
    return yaml.load(text), text


def dump_to_string(yaml, data):
    buf = io.StringIO()
    yaml.dump(data, buf)
    return buf.getvalue()


def write_file(yaml, path, data):
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        yaml.dump(data, fh)


def _to_commented(obj):
    """Deep-copy a plain dict/list (from safe-loaded config) into ruamel nodes."""
    if isinstance(obj, dict):
        m = CommentedMap()
        for k, v in obj.items():
            m[k] = _to_commented(v)
        return m
    if isinstance(obj, (list, tuple)):
        s = CommentedSeq()
        for v in obj:
            s.append(_to_commented(v))
        return s
    return obj


def _scalar(value):
    """Double-quote non-empty strings and empty strings alike; leave bools/None bare."""
    if isinstance(value, bool) or value is None:
        return value
    return DQ(str(value))


def _apply_meta(col, record_meta):
    config = col.get("config")
    if not isinstance(config, CommentedMap):
        config = CommentedMap()
        col["config"] = config
    meta = config.get("meta")
    if not isinstance(meta, CommentedMap):
        meta = CommentedMap()
        config["meta"] = meta
    for key, value in record_meta.items():
        meta[key] = value if isinstance(value, bool) else DQ(str(value))


def _apply_column_content(col, record):
    """Set description/data_type/meta from the record; leave everything else intact."""
    col["description"] = DQ(record.description)
    col["data_type"] = record.data_type if record.data_type else DQ("")
    _apply_meta(col, record.meta)


def _build_new_column(record):
    col = CommentedMap()
    col["name"] = record.column_name
    _apply_column_content(col, record)
    return col


def _overlay_model_config(entry, defaults):
    """Overlay per-folder default keys onto the model's config, preserving extras."""
    if not defaults:
        return
    config = entry.get("config")
    if not isinstance(config, CommentedMap):
        config = CommentedMap()
        entry["config"] = config
    for key, value in _to_commented(defaults).items():
        config[key] = value


def build_or_merge(existing_data, model_name, records, defaults):
    """Return (data, extra_columns) — the full <model>.yml document to write.

    existing_data: round-trip-loaded doc, or None for a new file.
    extra_columns: existing column names not present in the Excel (kept, reported).
    """
    if existing_data is None:
        data = CommentedMap()
        data["version"] = 2
        data["models"] = CommentedSeq()
    else:
        data = existing_data
        if "version" not in data:
            data["version"] = 2
        if not isinstance(data.get("models"), CommentedSeq):
            data["models"] = CommentedSeq()

    # Locate (or create) the model entry.
    entry = None
    for m in data["models"]:
        if m and str(m.get("name", "")).lower() == model_name.lower():
            entry = m
            break
    if entry is None:
        # Key order: name, description, config, columns (matches the target layout).
        entry = CommentedMap()
        entry["name"] = model_name
        entry["description"] = DQ("TODO: describe {}.".format(model_name))
        data["models"].append(entry)
        _overlay_model_config(entry, defaults)
        entry["columns"] = CommentedSeq()
    else:
        if not str(entry.get("description", "")).strip():
            entry["description"] = DQ("TODO: describe {}.".format(model_name))
        _overlay_model_config(entry, defaults)
        if not isinstance(entry.get("columns"), CommentedSeq):
            entry["columns"] = CommentedSeq()
    columns = entry["columns"]

    # Index existing columns by lower-cased name.
    existing_by_name = {}
    for col in columns:
        if col and "name" in col:
            existing_by_name[str(col["name"]).lower()] = col

    excel_names = set()
    for record in records:
        excel_names.add(record.column_name.lower())
        col = existing_by_name.get(record.column_name.lower())
        if col is not None:
            _apply_column_content(col, record)          # Excel wins; tests/constraints untouched
        else:
            columns.append(_build_new_column(record))    # append missing

    extra_columns = [
        str(col["name"]) for col in columns
        if col and "name" in col and str(col["name"]).lower() not in excel_names
    ]
    return data, extra_columns
