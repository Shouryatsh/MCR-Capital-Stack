"""Mapping-driven extraction from ERCF disclosure PDFs (Fannie Mae, Freddie Mac)."""
from __future__ import annotations

import logging
import re
from pathlib import Path

from .models import (ATA, CET1, Check, ColumnShapeError, FieldNotFoundError, Observation, ParseError, ParseResult,
                     UnitsError)
from .pdf_layout import Line, cover_text, read_lines, sections
from .units import TO_MILLIONS, detect_units, is_number, parse_number, to_millions

log = logging.getLogger("mcr.pdf")
MONTH_Q = {"march": 1, "june": 2, "september": 3, "december": 4}


# ------------------------------------------------------------------ period / provider detection
def infer_period(path: str, text: str | None = None) -> str:
    name = Path(path).name
    m = re.search(r"(\d{4})\s*q([1-4])", name, re.I)  # fannie ...2023q4...
    if m:
        return f"{m.group(1)}Q{m.group(2)}"
    m = re.search(r"(?<!\d)([1-4])q(\d{2})(?!\d)", name, re.I)  # freddie 4Q23
    if m:
        return f"20{m.group(2)}Q{m.group(1)}"
    text = text if text is not None else cover_text(path)
    m = re.search(r"(?:period\s+ended|as\s+of)\s+(March|June|September|December)\s+\d{1,2},\s+(\d{4})", text, re.I)
    if m:
        return f"{m.group(2)}Q{MONTH_Q[m.group(1).lower()]}"
    raise ParseError(name, "cannot infer the report period from the file name or cover text; enter it manually")


def detect_pdf_provider(path: str, mappings: dict) -> str:
    text = cover_text(path, pages=2).lower()
    for prov, cfg in mappings.items():
        if cfg.get("kind") == "pdf" and any(d.lower() in text for d in cfg.get("detect", [])):
            return prov
    raise ParseError(Path(path).name, "cannot tell which provider this PDF belongs to; choose the provider manually")


# ------------------------------------------------------------------ single value lookup
def _stem(word: str) -> str:
    return re.sub(r"(?<=[a-z])\d+$", "", word.lower())  # 'capital11' -> 'capital'


def _unit_for(sec: list[Line], upto: int) -> str | None:
    """Unit statement closest above the row, else the first one in the section."""
    for ln in reversed(sec[: upto + 1]):
        u = detect_units(ln.text)
        if u:
            return u
    for ln in sec:
        u = detect_units(ln.text)
        if u:
            return u
    return None


def _cells(line: Line, x_min: float, after_idx: int = -1) -> list:
    return [w for k, w in enumerate(line.words) if k > after_idx and is_number(w["text"]) and w["x0"] > x_min]


def lookup(lines: list[Line], spec: dict, source: str, field_name: str, period: str):
    """-> (raw_text, parsed_value, units, section_info, line, matched_label). Raises with a precise message."""
    anchor = re.compile(spec["anchor_regex"], re.I)
    end_word = spec.get("end_word")
    x_min = spec.get("x_min", 150 if spec.get("mode") == "adjacent" else 0)
    secs = sections(lines, spec["table_title"])
    if not secs:
        raise FieldNotFoundError(source, field_name, f"no table titled like {spec['table_title']!r}", period)
    shape_problem = None
    for exhibit_id, title, sec in secs:
        for i, ln in enumerate(sec):
            if not anchor.search(ln.text):
                continue
            cells = None
            if spec.get("mode") == "adjacent":  # label wrapped over two lines, number halfway between them
                for c in sec[i : i + 3]:
                    if c.page == ln.page and -1.0 <= c.top - ln.top <= 8.0:
                        cs = _cells(c, x_min)
                        if len(cs) == 1:
                            cells, row = cs, c
                            break
            elif end_word:  # label may wrap; the line containing the last label word carries the cells
                for c in sec[i : i + 3]:
                    if c.page != ln.page or c.top - ln.top > 30:
                        break
                    stems = [_stem(w["text"]) for w in c.words]
                    if end_word in stems:
                        last = max(k for k, s in enumerate(stems) if s == end_word)
                        cells, row = _cells(c, x_min, last), c
                        break
            else:  # all on one line, value to the right
                for c in sec[i : i + 3]:
                    if c.page == ln.page and c.top - ln.top <= 12:
                        cs = _cells(c, x_min)
                        if cs:
                            cells, row = cs, c
                            break
            if not cells:
                continue
            n, ints = spec.get("n_cells"), spec.get("integer_cells")
            if n and len(cells) != n:
                shape_problem = f"{row.text!r} has {len(cells)} numeric cells, expected {n}"
                continue
            if ints is not None:
                texts = [w["text"] for w in cells]
                if any("." in t for t in texts[:ints]) or not all("." in t for t in texts[ints:]):
                    shape_problem = f"{row.text!r}: first {ints} cells must be amounts and the rest ratios"
                    continue
            word = cells[spec.get("cell_index", -1)]
            units = _unit_for(sec, i)
            if not units:
                raise UnitsError(source, f"no '(Dollars in ...)' statement for {exhibit_id} {title!r}; refusing to assume units", period)
            return word["text"], parse_number(word["text"]), units, (exhibit_id, title), row, ln.text
    if shape_problem:
        raise ColumnShapeError(source, f"{field_name}: label found but columns do not line up: {shape_problem}", period)
    raise FieldNotFoundError(source, field_name, f"row matching /{spec['anchor_regex']}/ not found in {secs[0][0]} {secs[0][1]!r}", period)


# ------------------------------------------------------------------ whole-file parse
def parse_pdf(path: str, provider: str, cfg: dict, period: str | None = None, source_url: str = "") -> ParseResult:
    src = Path(path).name
    period = period or infer_period(path)
    lines = read_lines(path)
    log.info("parsing %s as %s %s", src, provider, period)
    obs: dict = {}
    for fname in (CET1, ATA):
        spec = cfg["fields"][fname]
        raw, val, units, (exhibit_id, title), row, label = lookup(lines, spec, src, fname, period)
        o = Observation(
            provider=provider, period=period, field=fname, source_file=src,
            table_name=f"{exhibit_id} · {title}" + (f", {spec['table_note']}" if spec.get("table_note") else ""),
            row_identifier=spec.get("line_item", label), field_label=spec.get("line_item", label),
            raw_value=raw, parsed_value=val, units_detected=units, value_mm=to_millions(val, units),
            location=f"p.{row.page + 1}", column_name=spec.get("column_name", ""), source_url=source_url)
        log.info("  %s: raw=%s units=%s -> %.0f mm (%s)", fname, raw, units, o.value_mm, o.location)
        obs[fname] = o

    checks = [Check("cet1_positive", "pass" if obs[CET1].value_mm > 0 else "fail",
                    f"CET1 minimum requirement = {obs[CET1].value_mm:,.0f} mm"),
              Check("ata_positive", "pass" if obs[ATA].value_mm > 0 else "fail", "")]
    # adjusted total assets cross-check against the second table that repeats it
    try:
        cs = cfg["checks"]["ata_crosscheck"]
        raw, val, units, (xid, xtitle), _, _ = lookup(lines, cs, src, "ATA cross-check", period)
        cross_mm = to_millions(val, units)
        tol = 0.5 * TO_MILLIONS[units] + 1e-6  # the cross-check value is rounded to its own unit
        ok = abs(obs[ATA].value_mm - cross_mm) <= tol
        checks.append(Check("ata_crosscheck", "pass" if ok else "fail",
                            f"{xid} shows {raw} ({units}); primary value {obs[ATA].value_mm:,.0f} mm"))
    except ParseError as e:
        checks.append(Check("ata_crosscheck", "fail", f"could not read cross-check value: {e}"))
    # CET1 minimum should be ~4.5% of standardized RWA
    try:
        raw, val, units, (rid, rtitle), _, _ = lookup(lines, cfg["checks"]["rwa"], src, "RWA", period)
        rwa_mm = to_millions(val, units)
        diff = abs(obs[CET1].value_mm - 0.045 * rwa_mm)
        checks.append(Check("cet1_vs_4.5pct_rwa", "pass" if diff <= 1000 else "fail",
                            f"min requirement {obs[CET1].value_mm:,.0f} mm vs 4.5% x RWA {rwa_mm:,.0f} mm = {0.045 * rwa_mm:,.0f} mm "
                            f"(diff {diff:,.0f} mm, tolerance 1,000 mm)"))
    except ParseError as e:
        checks.append(Check("cet1_vs_4.5pct_rwa", "fail", f"could not read RWA: {e}"))
    for c in checks:
        (log.info if c.status == "pass" else log.warning)("  check %s: %s %s", c.name, c.status, c.detail)
    return ParseResult(provider, period, obs, checks)
