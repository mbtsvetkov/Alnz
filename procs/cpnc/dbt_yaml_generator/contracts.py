"""Read the per-model data-contract decision from a model-level inventory sheet.

INDEPENDENT FLOW: nothing in here runs unless the CLI is given --apply-data-contracts
or --contracts-only. Contracts are never enabled as a side effect of normal generation.

The sheet holds ONE ROW PER MODEL (not per column) — e.g. the `inventory_overview` tab,
whose flag column says whether that model's output shape is a promise. Only
`config.contract.enforced` is written from it; per-column `constraints:`, `versions:`,
`access:` and `data_tests:` stay hand-authored (see docs/DATA_GOVERNANCE_CONCEPTS.md).
"""

from .config import ConfigError
from .inventory import _TRUE, _s  # deliberate reuse: one definition of "trimmed" and "truthy"

_FALSE = {"false", "no", "0", "n", "f"}

_DEFAULT_SHEET = "inventory_overview"


class ContractStats:
    def __init__(self):
        # --- filled while reading the sheet ---
        self.total_rows = 0
        self.skipped_blank_model = 0
        self.duplicate_rows = 0
        self.blank_flag = []        # model names whose flag cell was empty -> false
        self.unrecognised = []      # (model, raw value) -> false
        self.conflicts = []         # (model, [raw values]) — disagreeing rows, unresolvable
        # --- filled while applying, per discovered model ---
        self.applied_true = []
        self.applied_false = []
        self.unresolved = []        # on the sheet, but no single decision could be picked
        self.no_sql = []            # on the sheet, no .sql discovered
        self.no_yml = []            # --contracts-only: model has no <model>.yml yet
        self.no_entry = []          # <model>.yml exists but has no entry for this model
        self.missing_data_type = []  # (model, [columns]) on an enforced model


def _coerce_flag(value):
    """Return (enforced, kind) with kind in {'true', 'false', 'blank', 'unrecognised'}.

    Excel TRUE/FALSE cells arrive as real bools; 1/0 as numbers; everything else as text.
    Blank and unrecognised both resolve to False, but are counted separately so the
    summary can distinguish "nobody decided yet" from "somebody typed something odd".
    """
    if isinstance(value, bool):
        return value, "true" if value else "false"
    if isinstance(value, (int, float)):
        return bool(value), "true" if value else "false"
    text = _s(value).lower()
    if not text:
        return False, "blank"
    if text in _TRUE:
        return True, "true"
    if text in _FALSE:
        return False, "false"
    return False, "unrecognised"


def _norm_path(value):
    return _s(value).replace("\\", "/").strip("/").lower()


def _resolvable_by_path(cands):
    """True when disagreeing rows for one model can be told apart by their path column."""
    paths = [c["path"] for c in cands]
    return all(paths) and len(set(paths)) == len(paths)


def _contracts_cfg(config, sheet_override=None):
    cfg = dict(config.contracts)
    if not cfg:
        raise ConfigError(
            "Data contracts were requested but config has no 'contracts:' section.\n"
            "Add it (see config.example.yml section 5), e.g.:\n"
            "  contracts:\n"
            "    sheet: {}\n"
            "    model_column: model_name\n"
            "    flag_column: Is_Data_Contract_Enabled".format(_DEFAULT_SHEET)
        )
    if sheet_override:
        cfg["sheet"] = sheet_override
    for key in ("model_column", "flag_column"):
        if not _s(cfg.get(key)):
            raise ConfigError("config: contracts.{} is required.".format(key))
    cfg.setdefault("sheet", _DEFAULT_SHEET)
    cfg.setdefault("header_row", 1)
    return cfg


def _require_headers(cfg, headers):
    """Fail early, listing the headers actually present, if the sheet does not match config."""
    present = {str(h).strip() for h in headers}
    needed = [cfg["model_column"], cfg["flag_column"]]
    if _s(cfg.get("path_column")):
        needed.append(cfg["path_column"])
    missing = [h for h in dict.fromkeys(needed) if h not in present]
    if missing:
        raise ConfigError(
            "Contracts sheet '{}' is missing expected column(s): {}\n"
            "Columns present: {}".format(
                cfg["sheet"], ", ".join(missing), ", ".join(sorted(h for h in present if h))
            )
        )


class ContractFlags:
    """Per-model contract decisions, resolved on lookup by model name (+ folder)."""

    def __init__(self, by_model, stats, sheet):
        self._by_model = by_model  # {model_lower: [candidate dict, ...]} in sheet order
        self.stats = stats
        self.sheet = sheet

    def __len__(self):
        return len(self._by_model)

    def __contains__(self, model_name):
        return str(model_name).lower() in self._by_model

    def model_names(self):
        """Sheet-cased model names, one per distinct model, in sheet order."""
        return [cands[0]["model"] for cands in self._by_model.values()]

    def get(self, model_name, folder_rel=""):
        """Return True/False for a model, or None when absent or undecidable.

        Several sheet rows can name the same model (e.g. the same view in two schemas).
        Rows that agree collapse; rows that disagree are disambiguated on the sheet's
        path column against the model's folder, and left alone if that fails.
        """
        cands = self._by_model.get(str(model_name).lower())
        if not cands:
            return None
        if len({c["enforced"] for c in cands}) == 1:
            return cands[0]["enforced"]
        if not _resolvable_by_path(cands):
            return None  # reported as a conflict; the model is left untouched
        rel = _norm_path(folder_rel)
        matches = [c for c in cands if rel == c["path"] or rel.endswith("/" + c["path"])]
        if len(matches) == 1:
            return matches[0]["enforced"]
        return None


def read_contract_flags(config, excel_path=None, sheet_override=None):
    """Read the contracts sheet and return (ContractFlags, ContractStats)."""
    from . import excel_source

    cfg = _contracts_cfg(config, sheet_override)
    # contracts.excel_path wins: it is a deliberate "the flags live in another workbook".
    path = _s(cfg.get("excel_path")) or excel_path or config.excel.get("path") or None
    rows, headers = excel_source.read_rows(cfg, path)
    _require_headers(cfg, headers)

    model_col = cfg["model_column"]
    flag_col = cfg["flag_column"]
    path_col = _s(cfg.get("path_column")) or None

    stats = ContractStats()
    by_model = {}

    for row in rows:
        stats.total_rows += 1
        model_name = _s(row.get(model_col))
        if not model_name:
            stats.skipped_blank_model += 1
            continue

        raw = row.get(flag_col)
        enforced, kind = _coerce_flag(raw)
        if kind == "blank":
            stats.blank_flag.append(model_name)
        elif kind == "unrecognised":
            stats.unrecognised.append((model_name, _s(raw)))

        key = model_name.lower()
        if key in by_model:
            stats.duplicate_rows += 1
        by_model.setdefault(key, []).append({
            "model": model_name,
            "enforced": enforced,
            "raw": raw,
            "path": _norm_path(row.get(path_col)) if path_col else "",
        })

    # Report duplicates that disagree and cannot be told apart by their path.
    for cands in by_model.values():
        if len(cands) < 2 or len({c["enforced"] for c in cands}) == 1:
            continue
        if _resolvable_by_path(cands):
            continue
        stats.conflicts.append((cands[0]["model"], [_s(c["raw"]) for c in cands]))

    return ContractFlags(by_model, stats, cfg["sheet"]), stats
