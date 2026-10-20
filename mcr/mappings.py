"""Provider mapping rules (config/mappings.json). Defaults cover Fannie Mae and Freddie Mac.

PDF providers ("kind": "pdf") are described by table title + row anchor + which numeric cell to read.
Tabular providers ("kind": "tabular", xlsx/csv) are described by sheet + field label (see the README mapping guide).
"""
from __future__ import annotations

import json
import re

from .config import CONFIG_DIR

DEFAULT_MAPPINGS = {
    "Fannie Mae": {
        "kind": "pdf",
        "detect": ["Federal National Mortgage Association", "Fannie Mae"],
        "fields": {
            # CET1 minimum capital requirement: 2nd of 6 cells (Available | Minimum | Total | 3 ratios), $ billions.
            "CET1_amount": {
                "table_title": "capital metrics under the enterprise regulatory capital framework",
                "anchor_regex": r"^common equity\b", "end_word": "capital", "n_cells": 6, "integer_cells": 3,
                "cell_index": 1, "column_name": "Minimum Capital Requirement",
                "line_item": "Common equity tier 1 capital"},
            # Exhibit 11.1 Part 1 line 7, $ millions.
            "Adjusted_total_assets": {
                "table_title": "tier 1 leverage ratio",
                "anchor_regex": r"adjusted total assets \(sum of lines 1 to 6\)", "x_min": 400, "cell_index": -1,
                "line_item": "Line 7 · Adjusted total assets (sum of lines 1 to 6)", "table_note": "Part 1"},
        },
        "checks": {
            "rwa": {"table_title": "capital metrics under the enterprise regulatory capital framework",
                    "mode": "adjacent", "anchor_regex": r"^risk-weighted", "line_item": "Risk-weighted assets"},
            "ata_crosscheck": {"table_title": "capital metrics under the enterprise regulatory capital framework",
                               "mode": "adjacent", "anchor_regex": r"^adjusted total\b",
                               "line_item": "Adjusted total assets"},
        },
    },
    "Freddie Mac": {
        "kind": "pdf",
        "detect": ["Federal Home Loan Mortgage Corporation", "Freddie Mac"],
        "fields": {
            # Table 2.2: Minimum Capital Requirement is the FIRST of 5 cells (Min | Buffers | Total | Available | Shortfall).
            "CET1_amount": {
                "table_title": "ercf available capital and capital requirements",
                "anchor_regex": r"^cet1 capital", "end_word": "capital", "n_cells": 5, "integer_cells": 5,
                "cell_index": 0, "column_name": "Minimum Capital Requirement",
                "line_item": "CET1 capital"},
            "Adjusted_total_assets": {
                "table_title": "reconciliation of accounting total assets to adjusted total assets",
                "anchor_regex": r"^adjusted total assets", "x_min": 400, "cell_index": -1,
                "line_item": "Adjusted Total Assets"},
        },
        "checks": {
            "rwa": {"table_title": "adjusted total assets and standardized risk-weighted assets",
                    "anchor_regex": r"^risk-weighted assets", "x_min": 400, "cell_index": -1,
                    "line_item": "Risk-weighted Assets (Standardized Approach)"},
            "ata_crosscheck": {"table_title": "adjusted total assets and standardized risk-weighted assets",
                               "anchor_regex": r"^adjusted total assets", "x_min": 400, "cell_index": -1,
                               "line_item": "Adjusted Total Assets"},
        },
    },
}


def load_mappings() -> dict:
    p = CONFIG_DIR / "mappings.json"
    if not p.exists():
        save_mappings(DEFAULT_MAPPINGS)
    return json.loads(p.read_text(encoding="utf8"))


def save_mappings(m: dict) -> None:
    validate_mappings(m)
    CONFIG_DIR.mkdir(exist_ok=True)
    (CONFIG_DIR / "mappings.json").write_text(json.dumps(m, indent=2), encoding="utf8")


def validate_mappings(m: dict) -> None:
    for prov, cfg in m.items():
        if cfg.get("kind") not in ("pdf", "tabular"):
            raise ValueError(f"{prov}: 'kind' must be 'pdf' or 'tabular'")
        for f in ("CET1_amount", "Adjusted_total_assets"):
            if f not in cfg.get("fields", {}):
                raise ValueError(f"{prov}: mapping for {f} is missing")
        for spec in cfg["fields"].values():
            for key in ("anchor_regex",):
                if key in spec:
                    re.compile(spec[key])


def norm_name(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def find_provider(name: str, mappings: dict | None = None) -> str | None:
    """Match a file-name provider token ('Fannie_Mae', 'bankA') to a configured provider."""
    mappings = mappings or load_mappings()
    n = norm_name(name)
    return next((p for p in mappings if norm_name(p) == n), None)
