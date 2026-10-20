"""Regulatory capital source values from the Fannie Mae and Freddie Mac ERCF disclosures:
minimum capital ratio (CET1), total risk-weighted assets and credit risk-weighted assets.

Values are read with the same position-aware PDF reader as the CET1 / adjusted-total-assets extraction, kept as exact decimals
(RWA in $ millions, the unit both companies publish them in; the ratio in percent) and stored with full provenance in
`capital_metrics`. Anything that cannot be read is recorded as a failed check; nothing is estimated.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

from . import store
from .mappings import load_mappings
from .models import Check, ParseError
from .pdf_extract import infer_period, lookup
from .pdf_layout import read_lines

log = logging.getLogger("mcr.capital")

MIN_RATIO, TOTAL_RWA, CREDIT_RWA = "min_capital_ratio", "total_rwa", "credit_rwa"
FIELDS = {
    MIN_RATIO: ("Minimum capital ratio (CET1)", "percent"),
    TOTAL_RWA: ("Total risk-weighted assets", "USD millions"),
    CREDIT_RWA: ("Credit risk-weighted assets", "USD millions"),
}
TO_MILLIONS = {"thousands": Decimal("0.001"), "millions": Decimal(1), "billions": Decimal(1000)}
RWA_TOLERANCE_MM = Decimal(1000)  # CET1 minimum is published rounded to $1bn

# Table titles are matched by title (never by exhibit number, which Fannie Mae changed between releases).
_FANNIE_RWA = "rwa summary"
_FREDDIE_RWA = "adjusted total assets and standardized risk-weighted assets"
SPECS: dict[str, dict[str, dict]] = {
    "Fannie Mae": {
        # Exhibit 2.2, CET1 row: 6 cells = Available | Minimum | Total (amounts) then Available | Minimum | Total (ratios, %)
        MIN_RATIO: {"table_title": "capital metrics under the enterprise regulatory capital framework", "anchor_regex": r"^common equity\b",
                    "end_word": "capital", "n_cells": 6, "integer_cells": 3, "cell_index": 4,
                    "column_name": "Minimum Capital Ratio Requirement", "line_item": "Common equity tier 1 capital"},
        TOTAL_RWA: {"table_title": _FANNIE_RWA, "anchor_regex": r"^total\b", "cell_index": -1, "line_item": "Total (Standardized Approach RWA)"},
        CREDIT_RWA: {"table_title": _FANNIE_RWA, "anchor_regex": r"^credit risk", "cell_index": -1, "line_item": "Credit risk (Standardized Approach RWA)"},
        "market_rwa": {"table_title": _FANNIE_RWA, "anchor_regex": r"^market risk", "cell_index": -1, "line_item": "Market risk"},
        "operational_rwa": {"table_title": _FANNIE_RWA, "anchor_regex": r"^operational risk", "cell_index": -1, "line_item": "Operational risk"},
    },
    "Freddie Mac": {
        # Table 2.2, risk-based capital ratios, CET1 row: 5 decimal cells, Minimum Capital Requirement first (the amounts row is integers)
        MIN_RATIO: {"table_title": "ercf available capital and capital requirements", "anchor_regex": r"^cet1 capital", "end_word": "capital",
                    "n_cells": 5, "integer_cells": 0, "cell_index": 0, "column_name": "Minimum Capital Requirement",
                    "line_item": "CET1 capital (risk-based capital ratios)"},
        TOTAL_RWA: {"table_title": _FREDDIE_RWA, "anchor_regex": r"^risk-weighted assets", "x_min": 400, "cell_index": -1,
                    "line_item": "Risk-weighted Assets (Standardized Approach)"},
        CREDIT_RWA: {"table_title": _FREDDIE_RWA, "anchor_regex": r"^credit risk", "x_min": 400, "cell_index": -1, "line_item": "Credit Risk"},
        "market_rwa": {"table_title": _FREDDIE_RWA, "anchor_regex": r"^market risk", "x_min": 400, "cell_index": -1, "line_item": "Market Risk"},
        "operational_rwa": {"table_title": _FREDDIE_RWA, "anchor_regex": r"^operational risk", "x_min": 400, "cell_index": -1, "line_item": "Operational Risk"},
    },
}


@dataclass
class Metric:
    provider: str
    period: str
    field: str
    label: str
    value: str  # exact decimal text: percent for the ratio, $ millions for RWA
    unit: str
    raw_value: str  # as printed
    units_detected: str  # unit statement of the table ("millions"), or "percent"
    source_file: str
    table_name: str
    line_item: str
    column_name: str
    location: str
    source_url: str = ""


@dataclass
class CapitalResult:
    provider: str
    period: str
    metrics: dict = field(default_factory=dict)
    checks: list = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(c.status != "fail" for c in self.checks)


def _plain(d: Decimal) -> str:
    s = format(d, "f")
    return s.rstrip("0").rstrip(".") if "." in s else s


def _read(lines, spec, src, name, period):
    """(decimal value in published units, raw text, units, table, row) for one spec; raises ParseError."""
    raw, _, units, (exhibit, title), row, _ = lookup(lines, spec, src, name, period)
    return Decimal(re.sub(r"[^\d.]", "", raw)), raw, units, f"{exhibit} · {title}", row


def extract(path: str | Path, provider: str, period: str | None = None, source_url: str = "") -> CapitalResult:
    path = Path(path)
    src, period = path.name, period or infer_period(str(path))
    specs = SPECS[provider]
    lines = read_lines(str(path))
    res = CapitalResult(provider, period)
    millions: dict[str, Decimal] = {}

    for name in (MIN_RATIO, TOTAL_RWA, CREDIT_RWA, "market_rwa", "operational_rwa"):
        spec = specs[name]
        try:
            val, raw, units, table, row = _read(lines, spec, src, name, period)
        except ParseError as e:
            res.checks.append(Check(f"{name}_readable", "fail" if name in FIELDS else "warn", str(e)))
            continue
        if name == MIN_RATIO:
            value, unit, units_label = val, "percent", "percent"
        else:
            value, unit, units_label = val * TO_MILLIONS[units], "USD millions", units
            millions[name] = value
        if name in FIELDS:
            label = FIELDS[name][0]
            res.metrics[name] = Metric(provider, period, name, label, _plain(value), unit, raw, units_label, src, table, spec["line_item"],
                                       spec.get("column_name", ""), f"p.{row.page + 1}", source_url)
            log.info("  %s %s = %s %s (%s, p.%d)", provider, name, _plain(value), unit, raw, row.page + 1)

    # ---- validation (flags, never silent)
    if TOTAL_RWA in millions and CREDIT_RWA in millions:
        t, c = millions[TOTAL_RWA], millions[CREDIT_RWA]
        res.checks.append(Check("credit_rwa_within_total", "pass" if 0 < c <= t else "fail", f"credit {c:,.0f} of total {t:,.0f} ($ millions)"))
        if "market_rwa" in millions and "operational_rwa" in millions:
            s = c + millions["market_rwa"] + millions["operational_rwa"]
            res.checks.append(Check("rwa_components_sum_to_total", "pass" if s == t else "fail",
                                    f"credit {c:,.0f} + market {millions['market_rwa']:,.0f} + operational {millions['operational_rwa']:,.0f} = {s:,.0f} vs total {t:,.0f}"))
        else:
            res.checks.append(Check("rwa_components_sum_to_total", "warn", "market or operational RWA could not be read, so the components were not summed"))
    if MIN_RATIO in res.metrics and TOTAL_RWA in millions:
        try:
            cet1 = lookup(lines, load_mappings()[provider]["fields"]["CET1_amount"], src, "CET1 minimum", period)
            cet1_mm = Decimal(re.sub(r"[^\d.]", "", cet1[0])) * TO_MILLIONS[cet1[2]]
            implied = Decimal(res.metrics[MIN_RATIO].value) / 100 * millions[TOTAL_RWA]
            diff = abs(implied - cet1_mm)
            res.checks.append(Check("min_ratio_matches_cet1_requirement", "pass" if diff <= RWA_TOLERANCE_MM else "fail",
                                    f"{res.metrics[MIN_RATIO].value}% x total RWA {millions[TOTAL_RWA]:,.0f} = {implied:,.0f} vs published CET1 minimum {cet1_mm:,.0f} "
                                    f"($ millions; diff {diff:,.0f}, tolerance {RWA_TOLERANCE_MM:,.0f})"))
        except (ParseError, KeyError) as e:
            res.checks.append(Check("min_ratio_matches_cet1_requirement", "warn", f"CET1 minimum could not be read for the cross-check: {e}"))
    return res


def ingest(path: str | Path, provider: str, period: str | None = None, source_url: str = "", db=None) -> CapitalResult:
    res = extract(path, provider, period, source_url)
    store.save_capital(res, db)
    return res


def backfill(root: Path, db=None) -> list[CapitalResult]:
    """Re-read every local disclosure PDF (raw/fannie, raw/freddie); no downloads."""
    out = []
    for folder, provider in (("fannie", "Fannie Mae"), ("freddie", "Freddie Mac")):
        for pdf in sorted((root / folder).glob("*.pdf")):
            try:
                out.append(ingest(pdf, provider, db=db))
            except Exception as e:  # one bad file must not stop the backfill
                log.error("capital extraction failed for %s: %s", pdf.name, e)
                out.append(CapitalResult(provider, pdf.name, checks=[Check("extraction", "fail", str(e))]))
    return out


# ------------------------------------------------------------------ read back
def load(provider: str, db=None) -> list[dict]:
    """One dict per period (oldest first): {period, metrics: {field: row}, checks: [...]}."""
    by: dict[str, dict] = {}
    for r in store.rows("SELECT * FROM capital_metrics WHERE provider=? ORDER BY period", (provider,), db):
        by.setdefault(r["period"], {"period": r["period"], "metrics": {}, "checks": []})["metrics"][r["field"]] = r
    for k in store.rows("SELECT * FROM capital_checks WHERE provider=? ORDER BY period, name", (provider,), db):
        by.setdefault(k["period"], {"period": k["period"], "metrics": {}, "checks": []})["checks"].append(k)
    return [by[p] for p in sorted(by)]
