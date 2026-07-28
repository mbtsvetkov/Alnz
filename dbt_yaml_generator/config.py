"""Load + validate config.yml, and locate the dbt project root.

Project-root detection is what makes the package portable: `folders` in config are
resolved relative to the first ancestor directory containing dbt_project.yml, so the
package runs no matter where under the project it is dropped.
"""

import os

from ruamel.yaml import YAML


class ConfigError(SystemExit):
    """Raised (as a clean exit) when the config or project layout is unusable."""


def find_project_root(start=None, override=None):
    """Return the dbt project root (dir containing dbt_project.yml).

    override: explicit --project-dir (validated). Otherwise walk up from `start`
    (defaults to CWD) until dbt_project.yml is found.
    """
    if override:
        root = os.path.abspath(override)
        if not os.path.isfile(os.path.join(root, "dbt_project.yml")):
            raise ConfigError(
                "--project-dir '{}' has no dbt_project.yml".format(root)
            )
        return root

    current = os.path.abspath(start or os.getcwd())
    while True:
        if os.path.isfile(os.path.join(current, "dbt_project.yml")):
            return current
        parent = os.path.dirname(current)
        if parent == current:  # reached filesystem root
            raise ConfigError(
                "Could not find dbt_project.yml in any parent of {}.\n"
                "Run from inside your dbt project, or pass --project-dir.".format(
                    start or os.getcwd()
                )
            )
        current = parent


class MetaField:
    __slots__ = ("key", "source", "type")

    def __init__(self, key, source, type_):
        self.key = key
        self.source = source
        self.type = type_

    @property
    def is_boolean(self):
        return str(self.type).lower() == "boolean"


class Config:
    def __init__(self, data, path):
        self._data = data or {}
        self.path = path
        self._validate()

    # ---- top-level accessors ------------------------------------------------
    @property
    def folders(self):
        return list(self._data.get("folders") or [])

    @property
    def source(self):
        return self._data.get("source") or {}

    @property
    def mapping(self):
        return self.source.get("mapping") or {}

    @property
    def type_normalization(self):
        # normalise keys to upper-case for case-insensitive lookup
        raw = self.source.get("type_normalization") or {}
        return {str(k).upper(): v for k, v in raw.items()}

    @property
    def data_type_fallback(self):
        return self.source.get("data_type_fallback") or None

    @property
    def excel(self):
        return self.source.get("excel") or {}

    @property
    def snowflake(self):
        return self.source.get("snowflake") or {}

    @property
    def default_source(self):
        return self.source.get("default", "excel")

    @property
    def meta_fields(self):
        out = []
        for entry in self._data.get("meta_fields") or []:
            out.append(MetaField(entry["key"], entry["source"], entry.get("type", "string")))
        return out

    @property
    def folder_defaults(self):
        return self._data.get("folder_defaults") or {}

    def defaults_for(self, folder_relpath):
        """Longest-prefix folder_defaults match for a model's folder (posix-style)."""
        rel = folder_relpath.replace("\\", "/").rstrip("/")
        best_key, best_len = None, -1
        for key in self.folder_defaults:
            k = str(key).replace("\\", "/").rstrip("/")
            if (rel == k or rel.startswith(k + "/")) and len(k) > best_len:
                best_key, best_len = key, len(k)
        return dict(self.folder_defaults.get(best_key) or {}) if best_key is not None else {}

    # ---- validation ---------------------------------------------------------
    def _validate(self):
        if not self.folders:
            raise ConfigError("config: 'folders' is required and must be non-empty.")
        for field in ("model_name", "column_name", "description", "data_type"):
            if field not in self.mapping:
                raise ConfigError("config: source.mapping is missing '{}'.".format(field))
        if not self.meta_fields:
            raise ConfigError("config: 'meta_fields' must list at least one field.")
        for mf in self.meta_fields:
            if mf.type not in ("string", "boolean"):
                raise ConfigError(
                    "config: meta_fields '{}' has unsupported type '{}' "
                    "(use string or boolean).".format(mf.key, mf.type)
                )


def load_config(config_path):
    if not os.path.isfile(config_path):
        raise ConfigError(
            "Config not found: {}\nCopy config.example.yml to config.yml and edit it.".format(
                config_path
            )
        )
    with open(config_path, "r", encoding="utf-8") as fh:
        data = YAML(typ="safe").load(fh)
    return Config(data, config_path)
