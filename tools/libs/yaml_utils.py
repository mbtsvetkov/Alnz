"""YAML helpers for the column-metadata generator.

All YAML I/O goes through ruamel.yaml in round-trip mode so existing files keep
their comments, key order, block scalars and quoting. Only the nodes we add
(scaffolded model entries and the ``config: meta:`` blocks) are new.
"""

import io

from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap, CommentedSeq
from ruamel.yaml.scalarstring import DoubleQuotedScalarString as DQ


def make_yaml():
    """A ruamel YAML configured to match this repo's formatting conventions."""
    yaml = YAML()
    yaml.preserve_quotes = True
    # Match the repo: 2-space mappings, list dash at parent+2, content at parent+4.
    yaml.indent(mapping=2, sequence=4, offset=2)
    # Don't let ruamel line-wrap long business_definition strings.
    yaml.width = 4096
    return yaml


def load_file(yaml, path):
    """Return (data, original_text). original_text is None if the file is absent."""
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


def new_schema_doc():
    """A fresh dbt schema document: ``version: 2`` + empty ``models:``."""
    doc = CommentedMap()
    doc["version"] = 2
    doc["models"] = CommentedSeq()
    return doc


def documented_model_names(data):
    """Lower-cased model names documented in a loaded schema doc (empty if none)."""
    if not data or "models" not in data or data["models"] is None:
        return set()
    return {str(m.get("name", "")).lower() for m in data["models"] if m}


def set_column_meta(col, gov_row):
    """Set/merge ``config: meta:`` on a column map. Other config keys are preserved."""
    config = col.get("config")
    if config is None:
        config = CommentedMap()
        col["config"] = config
    meta = config.get("meta")
    if meta is None:
        meta = CommentedMap()
        config["meta"] = meta
    meta["business_name"] = DQ(str(gov_row["business_name"]))
    meta["business_definition"] = DQ(str(gov_row["business_definition"]))
    meta["pii"] = bool(gov_row["pii"])


def build_model_entry(model_name, columns, governance):
    """Build a new ``models:`` entry (CommentedMap) for a scaffolded model.

    columns: iterable of (column_name, data_type) as returned by snowflake_utils.
    governance: dict keyed by (model_lower, column_lower).
    """
    entry = CommentedMap()
    entry["name"] = model_name
    entry["description"] = DQ("TODO: describe {}.".format(model_name))

    cols = CommentedSeq()
    for col_name, data_type in columns:
        col = CommentedMap()
        col["name"] = col_name.lower()  # repo documents columns in lower case
        if data_type:
            col["data_type"] = data_type
        gov_row = governance.get((model_name.lower(), col_name.lower()))
        if gov_row:
            set_column_meta(col, gov_row)
        cols.append(col)
    entry["columns"] = cols
    return entry


def inject_meta_into_doc(data, governance, stats):
    """Inject ``config: meta:`` into every governed column of a loaded doc.

    Mutates ``data`` in place. Records progress on ``stats`` (see EnrichStats).
    Returns nothing; caller diffs the serialized form to decide whether to write.
    """
    if not data or "models" not in data or data["models"] is None:
        return
    for model in data["models"]:
        if not model:
            continue
        mname = str(model.get("name", "")).lower()
        columns = model.get("columns") or []
        for col in columns:
            cname = str(col.get("name", "")).lower()
            gov_row = governance.get((mname, cname))
            if gov_row:
                set_column_meta(col, gov_row)
                stats.enriched_columns += 1
                stats.matched_keys.add((mname, cname))
            else:
                stats.columns_without_governance.append((mname, cname))
