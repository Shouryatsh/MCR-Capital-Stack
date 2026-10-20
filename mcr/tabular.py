"""Excel / CSV extraction driven by a per-provider mapping: {sheet?, field, value_column?, units?}.

Units are detected from the file (text near the row, the sheet header rows, or the column header); the mapping's
"units" is only a fallback when the file states none, and a detected unit always wins (conflicts are logged).
"""
from __future__ import annotations

import csv
import logging
import re
from pathlib import Path

from .models import (ATA, CET1, AmbiguousMappingError, Check, FieldNotFoundError, Observation, ParseError,
                     ParseResult, UnitsError)
from .units import detect_units, to_millions

log = logging.getLogger("mcr.tabular")


def _norm(s) -> str:
    s = re.sub(r"\(\d+\)|(?<=[A-Za-z])\d+\b", "", str(s))  # footnote markers
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9()% ]", " ", s.lower())).strip()


def load_grid(path: str) -> dict[str, list[list]]:
    """sheet name -> rows (lists of cell values)."""
    p = Path(path)
    if p.suffix.lower() == ".csv":
        with open(p, newline="", encoding="utf-8-sig") as f:
            return {"csv": [row for row in csv.reader(f)]}
    if p.suffix.lower() in (".xlsx", ".xlsm"):
        import openpyxl

        try:
            wb = openpyxl.load_workbook(p, data_only=True, read_only=True)
        except Exception as e:  # corrupt / not really an xlsx
            raise ParseError(p.name, f"cannot open workbook: {e}") from e
        return {ws.title: [list(r) for r in ws.iter_rows(values_only=True)] for ws in wb.worksheets}
    raise ParseError(p.name, f"unsupported file type {p.suffix!r}")


def _as_number(v):
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip()
    if re.fullmatch(r"\(?-?\$?\(?[\d,]+(\.\d+)?\)?", s):
        neg = "(" in s or s.startswith("-")
        x = float(re.sub(r"[^\d.]", "", s))
        return -x if neg else x
    return None


def _units_near(rows: list[list], r: int, c: int) -> str | None:
    """Unit statement in the row, then scanning upward (column header / title rows), then the top of the sheet."""
    for text in [" ".join(map(str, rows[r]))] + [" ".join(map(str, rows[k])) for k in range(r - 1, -1, -1)]:
        u = detect_units(text)
        if u:
            return u
    return None


def _find(rows, label_norm, exact_first=True):
    exact, partial = [], []
    for r, row in enumerate(rows):
        for c, v in enumerate(row):
            if v is None or _as_number(v) is not None:
                continue
            n = _norm(v)
            if n == label_norm:
                exact.append((r, c))
            elif label_norm in n:
                partial.append((r, c))
    return exact or partial


def extract_field(grid: dict, spec: dict, source: str, field_name: str, period: str, provider: str):
    sheets = [s for s in grid if not spec.get("sheet") or s.lower() == spec["sheet"].lower()]
    if not sheets:
        raise FieldNotFoundError(source, field_name, f"sheet {spec['sheet']!r} not in file (has: {', '.join(grid)})", period)
    want = _norm(spec["field"])
    hits = []  # (sheet, r, c, number, raw)
    for sh in sheets:
        rows = grid[sh]
        for r, c in _find(rows, want):
            hdr = spec.get("value_column")
            cols = range(c + 1, min(len(rows[r]), c + 8))
            if hdr:  # pick the column whose header (any row above) matches
                hn = _norm(hdr)
                cols = [k for k in cols if any(k < len(rows[h]) and hn in _norm(rows[h][k] or "") for h in range(0, r))]
            for k in cols:
                n = _as_number(rows[r][k])
                if n is not None:
                    hits.append((sh, r, c, k, n, rows[r][k]))
                    break
    if not hits:
        raise FieldNotFoundError(source, field_name, f"label {spec['field']!r} with a number beside it not found"
                                 + (f" on sheet {spec['sheet']!r}" if spec.get("sheet") else ""), period)
    if len({h[4] for h in hits}) > 1:
        locs = "; ".join(f"{h[0]}!R{h[1] + 1}C{h[3] + 1}={h[4]:,.0f}" for h in hits[:6])
        raise AmbiguousMappingError(source, f"{field_name}: label {spec['field']!r} matches several different values ({locs}). "
                                    "Set 'sheet' and/or 'value_column' in the mapping to choose one.", period)
    sh, r, c, k, n, raw = hits[0]
    rows = grid[sh]
    detected = _units_near(rows, r, k)
    hint = spec.get("units")
    if detected and hint and detected != hint:
        log.warning("%s %s: mapping says %s but the file says %s; using the file", source, field_name, hint, detected)
    units, usrc = (detected, "detected") if detected else (hint, "mapping")
    if not units:
        raise UnitsError(source, f"{field_name}: no unit statement found near {sh}!R{r + 1} and no 'units' fallback in the mapping", period)
    return Observation(
        provider=provider, period=period, field=field_name, source_file=source, table_name=sh,
        row_identifier=f"row {r + 1}", field_label=str(rows[r][c]).strip(), raw_value=str(raw), parsed_value=n,
        units_detected=units, units_source=usrc, value_mm=to_millions(n, units),
        location=f"{sh}!R{r + 1}C{k + 1}", column_name=str(spec.get("value_column", "")),
        notes=([f"units taken from mapping (file states none): {units}"] if usrc == "mapping" else []))


def parse_tabular(path: str, provider: str, cfg: dict, period: str, source_url: str = "") -> ParseResult:
    src = Path(path).name
    grid = load_grid(path)
    log.info("parsing %s as %s %s (%d sheet(s))", src, provider, period, len(grid))
    obs = {}
    for fname in (CET1, ATA):
        o = extract_field(grid, cfg["fields"][fname], src, fname, period, provider)
        o.source_url = source_url
        log.info("  %s: raw=%s units=%s(%s) -> %.0f mm at %s", fname, o.raw_value, o.units_detected, o.units_source, o.value_mm, o.location)
        obs[fname] = o
    checks = [Check("cet1_positive", "pass" if obs[CET1].value_mm > 0 else "fail", f"{obs[CET1].value_mm:,.0f} mm"),
              Check("ata_positive", "pass" if obs[ATA].value_mm > 0 else "fail", f"{obs[ATA].value_mm:,.0f} mm"),
              Check("cet1_below_ata", "pass" if obs[CET1].value_mm < obs[ATA].value_mm else "fail",
                    "CET1 must be smaller than adjusted total assets")]
    return ParseResult(provider, period, obs, checks)
