"""FHLBanks (Federal Home Loan Banks) system-wide capital requirements, built from the official FHLBanks Office of
Finance "Combined Financial Report" (CFR) PDFs.

* Reports: https://www.fhlb-of.com/investor-resources/financial-reports/combined/  (one PDF per quarter, all 11
  FHLBanks: Boston, New York, Pittsburgh, Atlanta, Cincinnati, Indianapolis, Chicago, Des Moines, Dallas, Topeka,
  San Francisco).
* Two tables are extracted per report:
    Table 9.1 - Risk-Based Capital Requirements: FHLBank | Minimum Requirement ($mm) | Actual ($mm)
    Table 9.2 - Regulatory Capital Requirements: FHLBank | Min Ratio (%) | Actual Ratio (%) | Min ($mm) | Actual ($mm)
  Their numeric prefix (9.1/9.2, 11.1/11.2, 13.1/13.2, 15.1/15.2, 16.1/16.2) changes across report years as other
  notes are added or removed, so both are matched by title text, never by number.
* A system-wide "Combined" row (for analysis only, per the reports' own footnote) is published in some but not all
  periods; its absence is not an error.
* Units are $ millions, as published; percentages are stored as published (e.g. 4.00). Nothing is estimated: a period
  whose PDF is missing or unparsable is simply absent, and is recorded as a gap.
"""
from __future__ import annotations

import logging
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

import pymupdf
import requests

from . import config, store

log = logging.getLogger("mcr.fhlb")

PROVIDER = "FHLBs"
BANKS = ["Boston", "New York", "Pittsburgh", "Atlanta", "Cincinnati", "Indianapolis",
         "Chicago", "Des Moines", "Dallas", "Topeka", "San Francisco"]
INDEX_URL = "https://www.fhlb-of.com/investor-resources/financial-reports/combined/"

# period -> source PDF url (collected from the index page; the CDN path layout has varied by year).
URLS = {
    "2026Q1": "https://cdn.fhlb-of.com/files/2026/2026Q1CFR.pdf",
    "2026Q2": "https://cdn.fhlb-of.com/files/2026/2026Q2CFR.pdf",
    "2025Q1": "https://cdn.fhlb-of.com/files/Complete%20Combined%20Financial%20Reports/2025Q1CFR.pdf",
    "2025Q2": "https://cdn.fhlb-of.com/files/2025/2025Q2CFR.pdf",
    "2025Q3": "https://cdn.fhlb-of.com/files/2025/2025Q3CFR.pdf",
    "2025Q4": "https://cdn.fhlb-of.com/files/2025/2025Q4CFR.pdf",
    "2024Q1": "https://cdn.fhlb-of.com/files/Complete%20Combined%20Financial%20Reports/2024Q1CFR.pdf",
    "2024Q2": "https://cdn.fhlb-of.com/files/Complete%20Combined%20Financial%20Reports/2024Q2CFR.pdf",
    "2024Q3": "https://cdn.fhlb-of.com/files/Complete%20Combined%20Financial%20Reports/2024Q3CFR.pdf",
    "2024Q4": "https://cdn.fhlb-of.com/files/Complete%20Combined%20Financial%20Reports/2024Q4CFR.pdf",
    "2023Q1": "https://cdn.fhlb-of.com/files/2023Q1CFR.pdf",
    "2023Q2": "https://cdn.fhlb-of.com/files/2023Q2CFR.pdf",
    "2023Q3": "https://cdn.fhlb-of.com/files/2023Q3CFR.pdf",
    "2023Q4": "https://cdn.fhlb-of.com/files/2023Q4CFR.pdf",
    "2022Q1": "https://cdn.fhlb-of.com/files/2022Q1CFR.pdf",
    "2022Q2": "https://cdn.fhlb-of.com/files/2022Q2CFR.pdf",
    "2022Q3": "https://cdn.fhlb-of.com/files/2022Q3CFR.pdf",
    "2022Q4": "https://cdn.fhlb-of.com/files/2022Q4CFR.pdf",
    "2021Q1": "https://cdn.fhlb-of.com/files/2021Q1CFR.pdf",
    "2021Q2": "https://cdn.fhlb-of.com/files/2021Q2CFR.pdf",
    "2021Q3": "https://cdn.fhlb-of.com/files/2021Q3CFR.pdf",
    "2021Q4": "https://cdn.fhlb-of.com/files/2021Q4CFR.pdf",
    "2020Q1": "https://cdn.fhlb-of.com/files/2020Q1CFR.pdf",
    "2020Q2": "https://cdn.fhlb-of.com/files/2020Q2CFR.pdf",
    "2020Q3": "https://cdn.fhlb-of.com/files/2020Q3CFR.pdf",
    "2020Q4": "https://cdn.fhlb-of.com/files/2020Q4CFR.pdf",
    "2019Q1": "https://cdn.fhlb-of.com/files/2019Q1CFR.pdf",
    "2019Q2": "https://cdn.fhlb-of.com/files/2019Q2CFR.pdf",
    "2019Q3": "https://cdn.fhlb-of.com/files/2019Q3CFR.pdf",
    "2019Q4": "https://cdn.fhlb-of.com/files/2019Q4CFR.pdf",
    "2018Q1": "https://cdn.fhlb-of.com/files/2018Q1CFR.pdf",
    "2018Q2": "https://cdn.fhlb-of.com/files/2018Q2CFR.pdf",
    "2018Q3": "https://cdn.fhlb-of.com/files/2018Q3CFR.pdf",
    "2018Q4": "https://cdn.fhlb-of.com/files/2018Q4CFR.pdf",
    "2017Q1": "https://cdn.fhlb-of.com/files/2017Q1CFR.pdf",
    "2017Q2": "https://cdn.fhlb-of.com/files/2017Q2CFR.pdf",
    "2017Q3": "https://cdn.fhlb-of.com/files/2017Q3CFR.pdf",
    "2017Q4": "https://cdn.fhlb-of.com/files/2017Q4CFR.pdf",
    "2016Q1": "https://cdn.fhlb-of.com/files/2016Q1CFR.pdf",
    "2016Q2": "https://cdn.fhlb-of.com/files/2016Q2CFR.pdf",
    "2016Q3": "https://cdn.fhlb-of.com/files/2016Q3CFR.pdf",
    "2016Q4": "https://cdn.fhlb-of.com/files/2016Q4CFR.pdf",
}

T91_TITLE = r"Table\s*[\d\.]+\s*-\s*Risk-Based Capital Requirements"
T92_TITLE = r"Table\s*[\d\.]+\s*-\s*Regulatory Capital Requirements"
# (field, label, unit, table) in display order.
FIELDS = [
    ("t91_min_mm", "Risk-based capital, minimum requirement", "USD millions", "Table 9.1 · Risk-Based Capital Requirements"),
    ("t91_actual_mm", "Risk-based capital, actual", "USD millions", "Table 9.1 · Risk-Based Capital Requirements"),
    ("t92_min_ratio_pct", "Regulatory capital ratio, minimum requirement", "percent", "Table 9.2 · Regulatory Capital Requirements"),
    ("t92_actual_ratio_pct", "Regulatory capital ratio, actual", "percent", "Table 9.2 · Regulatory Capital Requirements"),
    ("t92_min_mm", "Regulatory capital, minimum requirement", "USD millions", "Table 9.2 · Regulatory Capital Requirements"),
    ("t92_actual_mm", "Regulatory capital, actual", "USD millions", "Table 9.2 · Regulatory Capital Requirements"),
]
_FIELD_UNIT = {f: u for f, _, u, _ in FIELDS}
_FIELD_LABEL = {f: lbl for f, lbl, _, _ in FIELDS}
_FIELD_TABLE = {f: t for f, _, _, t in FIELDS}

# Derived columns (calculated here, never stored): (field, label, unit, formula).
DERIVED_FIELDS = [
    ("derived_total_assets_mm", "Total Assets", "USD millions",
     "Risk-based capital, actual ÷ Regulatory capital ratio, actual"),
    ("derived_actual_rbc_ratio_pct", "Actual Risk Based Capital Ratio", "percent",
     "Risk-based capital, minimum requirement ÷ Total Assets (derived above)"),
]


def derive_combined(banks: dict[str, dict[str, float]]) -> dict[str, float]:
    """System-wide Combined values for a period whose report did not publish a Combined row: the dollar fields are the sum
    of the 11 FHLBanks, and the actual regulatory capital ratio is total regulatory capital over the total assets implied by
    each bank's own ratio (a weighted figure, not an average of ratios). Returns {} unless all 11 banks have every input.
    The minimum ratio is a fixed 4% requirement that the reports do not publish for Combined, so it is not derived."""
    members = [banks.get(b) for b in BANKS]
    needed = ("t91_min_mm", "t91_actual_mm", "t92_min_mm", "t92_actual_mm", "t92_actual_ratio_pct")
    if any(m is None or any(m.get(f) is None for f in needed) or m["t92_actual_ratio_pct"] <= 0 for m in members):
        return {}
    out = {f: sum(m[f] for m in members) for f in ("t91_min_mm", "t91_actual_mm", "t92_min_mm", "t92_actual_mm")}
    assets = sum(m["t92_actual_mm"] / (m["t92_actual_ratio_pct"] / 100) for m in members)
    out["t92_actual_ratio_pct"] = out["t92_actual_mm"] / assets * 100
    return out


def derive(values: dict[str, float]) -> dict[str, float]:
    """Derived values for one bank-period from its published values; a value is omitted when an input is missing or the
    divisor is not positive. The ratio is published in percent, so it is divided by 100 before use. Works on floats (the
    dashboard tables) or Decimals (the exact benchmark engine)."""
    out: dict[str, float] = {}
    rbc_actual, ratio = values.get("t91_actual_mm"), values.get("t92_actual_ratio_pct")
    if rbc_actual is not None and ratio is not None and ratio > 0:
        out["derived_total_assets_mm"] = rbc_actual / (ratio / 100)
    assets, rbc_min = out.get("derived_total_assets_mm"), values.get("t91_min_mm")
    if assets and rbc_min is not None:
        out["derived_actual_rbc_ratio_pct"] = rbc_min / assets * 100
    return out


def period_sort_key(period: str) -> tuple[int, int]:
    return int(period[:4]), int(period[5])


def report_filename(period: str) -> str:
    return f"{period}.pdf"


@dataclass
class Observation:
    """One extracted FHLB figure plus everything needed to trace it back to the source PDF."""

    period: str
    report_date: str
    fhlbank: str
    field: str
    label: str
    raw_value: str
    parsed_value: float
    unit: str
    source_file: str
    source_url: str
    table_name: str
    location: str
    flags: list = field(default_factory=list)

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class FhlbResult:
    period: str
    report_date: str
    observations: list = field(default_factory=list)
    gaps: list = field(default_factory=list)  # reasons the period could not be (fully) read


# ------------------------------------------------------------------ download
def fetch_missing(periods: list[str] | None = None) -> list[str]:
    """Download any period in `periods` (default: all of URLS) not already present in raw/fhlb/."""
    dest_dir = config.RAW_DIR / "fhlb"
    dest_dir.mkdir(parents=True, exist_ok=True)
    downloaded = []
    for period in sorted(periods or URLS, key=period_sort_key):
        url = URLS.get(period)
        if not url:
            continue
        dest = dest_dir / report_filename(period)
        if dest.exists():
            continue
        r = requests.get(url, headers={"User-Agent": config.USER_AGENT}, timeout=180)
        r.raise_for_status()
        if not r.content.startswith(b"%PDF"):
            store.log_fetch(url, "fail", "response was not a PDF")
            log.warning("%s: response was not a PDF", url)
            continue
        dest.write_bytes(r.content)
        store.log_fetch(url, "ok", f"downloaded {len(r.content):,} bytes")
        log.info("downloaded %s -> %s", url, dest)
        downloaded.append(period)
    return downloaded


# ------------------------------------------------------------------ PDF parsing (title-matched, never by table number)
def _full_text_by_page(doc) -> list[str]:
    return [page.get_text() for page in doc]


def _page_of(pages: list[str], pattern: str) -> int:
    rx = re.compile(pattern)
    for i, t in enumerate(pages):
        if rx.search(t):
            return i + 1  # 1-based
    return 0


def _find_block(text: str, start_pat: str, end_pats: list[str]) -> str | None:
    m = re.search(start_pat, text)
    if not m:
        return None
    rest = text[m.end():]
    end = len(rest)
    for ep in end_pats:
        em = re.search(ep, rest)
        if em and em.start() < end:
            end = em.start()
    return rest[:end]


def _to_number(tok: str) -> float:
    neg = tok.startswith("(") and tok.endswith(")")
    tok = tok.strip("()").replace(",", "")
    v = float(tok)
    return -v if neg else v


def _extract_bank_rows(block: str, n_values: int, combined_n_values: int | None = None) -> dict[str, list[dict]]:
    """For each bank name (and a trailing Combined row, if present), the next n_values numeric/percent tokens
    before the following bank name (or end of block). Some reports stopped publishing the Combined row entirely,
    so it is optional."""
    combined_n_values = n_values if combined_n_values is None else combined_n_values
    names = BANKS + ["Combined"]
    positions = []
    pos = 0
    for name in names:
        pat = re.escape(name) if name != "Combined" else r"Combined\s*\(?\d*\)?"
        m = re.search(pat, block[pos:])
        if not m:
            if name == "Combined":
                break  # not every report publishes a system-wide Combined row
            raise ValueError(f"bank {name!r} not found in table block")
        positions.append((name, pos + m.start(), pos + m.end()))
        pos = pos + m.end()
    out: dict[str, list[dict]] = {}
    for i, (name, _start, end) in enumerate(positions):
        seg_end = positions[i + 1][1] if i + 1 < len(positions) else len(block)
        seg = block[end:seg_end]
        want = combined_n_values if name == "Combined" else n_values
        toks = [t.strip() for t in re.findall(r"\(?-?[\d,]+\.?\d*\)?\s*%?", seg) if t.strip()]
        vals = []
        for t in toks:
            if len(vals) >= want:
                break
            is_pct = t.endswith("%")
            vals.append({"value": _to_number(t.rstrip("%").strip()), "is_pct": is_pct})
        out[name] = vals
    return out


def extract_period(path: str | Path, period: str, source_url: str = "") -> FhlbResult:
    path = Path(path)
    doc = pymupdf.open(path)
    pages = _full_text_by_page(doc)
    text = "\f".join(pages)
    res = FhlbResult(period=period, report_date="")

    t91_num_m = re.search(r"Table\s*([\d\.]+)\s*-\s*Risk-Based Capital Requirements", text)
    t92_num_m = re.search(r"Table\s*([\d\.]+)\s*-\s*Regulatory Capital Requirements", text)
    if not t91_num_m or not t92_num_m:
        res.gaps.append("could not locate the Table 9.1/9.2 titles in the PDF text layer")
        return res

    dm = re.search(T91_TITLE + r" at ([^\n(]+)", text)
    res.report_date = dm.group(1).strip() if dm else ""

    t91_block = _find_block(text, T91_TITLE + r"[^\n]*\n(?:\(dollars[^\n]*\n)?", [T92_TITLE, r"\n_{5,}"])
    t92_block = _find_block(text, T92_TITLE + r"[^\n]*\n(?:\(dollars[^\n]*\n)?",
                            [r"\n_{5,}", r"TABLE OF CONTENTS", r"Table\s*[\d\.]+\s*-\s*Leverage Capital Requirements"])
    if t91_block is None or t92_block is None:
        res.gaps.append("could not locate the Table 9.1/9.2 bodies in the PDF text layer")
        return res

    t91_page = _page_of(pages, r"Risk-Based Capital Requirements")
    t92_page = _page_of(pages, r"Regulatory Capital Requirements")
    try:
        t91 = _extract_bank_rows(t91_block, n_values=2)
        t92 = _extract_bank_rows(t92_block, n_values=4, combined_n_values=3)
    except ValueError as e:
        res.gaps.append(str(e))
        return res

    src_file, loc91, loc92 = path.name, f"p.{t91_page}" if t91_page else "", f"p.{t92_page}" if t92_page else ""
    table_num = {"Table 9.1 · Risk-Based Capital Requirements": f"Table {t91_num_m.group(1)} · Risk-Based Capital Requirements",
                 "Table 9.2 · Regulatory Capital Requirements": f"Table {t92_num_m.group(1)} · Regulatory Capital Requirements"}

    for bank, vals in t91.items():
        for field_name, idx in (("t91_min_mm", 0), ("t91_actual_mm", 1)):
            if idx >= len(vals):
                continue
            res.observations.append(_obs(period, res.report_date, bank, field_name, vals[idx], src_file, source_url,
                                         table_num[_FIELD_TABLE[field_name]], loc91))
    for bank, vals in t92.items():
        if bank == "Combined" and len(vals) == 3:  # Combined omits the minimum-ratio column (it's not meaningful system-wide)
            mapping = [("t92_actual_ratio_pct", 0), ("t92_min_mm", 1), ("t92_actual_mm", 2)]
        else:
            mapping = [("t92_min_ratio_pct", 0), ("t92_actual_ratio_pct", 1), ("t92_min_mm", 2), ("t92_actual_mm", 3)]
        for field_name, idx in mapping:
            if idx >= len(vals):
                continue
            res.observations.append(_obs(period, res.report_date, bank, field_name, vals[idx], src_file, source_url,
                                         table_num[_FIELD_TABLE[field_name]], loc92))
    return res


def _obs(period, report_date, bank, field_name, val, source_file, source_url, table_name, location) -> Observation:
    raw = f"{val['value']:,.2f}%" if val["is_pct"] else f"{val['value']:,.0f}"
    return Observation(period=period, report_date=report_date, fhlbank=bank, field=field_name,
                       label=_FIELD_LABEL[field_name], raw_value=raw, parsed_value=val["value"],
                       unit=_FIELD_UNIT[field_name], source_file=source_file, source_url=source_url,
                       table_name=table_name, location=location)


# ------------------------------------------------------------------ ingest / load
def ingest_all(raw_dir: Path | None = None, db=None, fetch=False) -> list[FhlbResult]:
    """Parse every FHLB CFR PDF found locally (raw/fhlb/*.pdf), optionally downloading missing ones first."""
    raw_dir = raw_dir or (config.RAW_DIR / "fhlb")
    if fetch:
        fetch_missing()
    results = []
    for period in sorted(URLS, key=period_sort_key):
        path = raw_dir / report_filename(period)
        if not path.exists():
            continue
        try:
            res = extract_period(path, period, URLS.get(period, ""))
        except Exception as e:  # noqa: BLE001 - keep going; record as a gap, never crash a full backfill
            res = FhlbResult(period=period, report_date="", gaps=[f"unexpected error: {e}"])
            log.exception("failed to parse %s", path)
        store.save_fhlb(period, res, db)
        results.append(res)
    return results


def load_rows(db=None) -> list[dict]:
    return store.rows("SELECT * FROM fhlb_capital ORDER BY period, fhlbank, field", (), db)


def load_gaps(db=None) -> list[dict]:
    return store.rows("SELECT * FROM fhlb_gaps ORDER BY period", (), db)


# ------------------------------------------------------------------ validation (nothing is stored as "estimated")
def validate(rows: list[dict]) -> list[dict]:
    checks = []
    by_period: dict[str, dict[str, dict]] = {}
    for r in rows:
        by_period.setdefault(r["period"], {}).setdefault(r["fhlbank"], {})[r["field"]] = r

    bad_min_ratio = [(p, b) for p, banks in by_period.items() for b, f in banks.items()
                     if "t92_min_ratio_pct" in f and abs(f["t92_min_ratio_pct"]["parsed_value"] - 4.0) > 1e-9]
    checks.append({"name": "Regulatory capital minimum ratio is 4.00% for every bank and period",
                   "status": "fail" if bad_min_ratio else "pass",
                   "detail": f"unexpected values: {bad_min_ratio}" if bad_min_ratio else f"{sum(1 for v in by_period.values() for b in v if b != 'Combined')} bank-period(s) checked"})

    recon_fail = []
    for p, banks in by_period.items():
        combined = banks.get("Combined", {})
        if "t92_actual_mm" not in combined:
            continue
        total = sum(f["t92_actual_mm"]["parsed_value"] for b, f in banks.items() if b != "Combined" and "t92_actual_mm" in f)
        diff = abs(total - combined["t92_actual_mm"]["parsed_value"])
        if diff > 5.0:  # reports note the Combined row may differ from the simple sum by combining adjustments
            recon_fail.append((p, round(diff, 1)))
    checks.append({"name": "Combined regulatory capital reconciles to the sum of the 11 FHLBanks (within $5mm)",
                   "status": "fail" if recon_fail else "pass",
                   "detail": f"differences: {recon_fail}" if recon_fail else f"{sum(1 for v in by_period.values() if 'Combined' in v)} period(s) with a Combined row"})

    periods_with_all_banks = [p for p, banks in by_period.items() if len([b for b in banks if b != "Combined"]) == len(BANKS)]
    missing = sorted(set(URLS) - set(periods_with_all_banks), key=period_sort_key)
    checks.append({"name": "All 11 FHLBanks present for every ingested period",
                   "status": "warn" if missing else "pass",
                   "detail": f"periods without all 11 banks: {missing}" if missing else f"{len(periods_with_all_banks)} period(s)"})
    return checks


def summary(rows: list[dict]) -> dict:
    periods = sorted({r["period"] for r in rows}, key=period_sort_key)
    banks = sorted({r["fhlbank"] for r in rows})
    return {"periods": len(periods), "first_period": periods[0] if periods else None,
            "last_period": periods[-1] if periods else None, "banks": len(banks)}
