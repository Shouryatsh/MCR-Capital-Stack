"""Ginnie Mae (GNMA) Maximum Exposure to Loss, built from the official English annual reports.

Total Maximum Exposure to Loss = Outstanding MBS + Outstanding MBS commitments (Notes to the Financial Statements).

* Reports: https://www.ginniemae.gov/about_us/what_we_do/Annual_Reports/annual_reportYY.pdf  (index page:
  https://www.ginniemae.gov/about-us/what-we-do/budget-performance/annual-reports). English originals only.
* Units are read from the file ("Dollars in thousands" / "Dollars in billions"), never assumed. Money is stored as exact
  integer US dollars (Decimal arithmetic, TEXT in SQLite), so there is no floating-point error.
* Every figure keeps its source report, URL, fiscal year, reporting date, PDF page, printed page and note.
* Anything missing, ambiguous or inconsistent is flagged (figure flags / gaps / reconciliation), never estimated.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import asdict, dataclass, field
from datetime import date
from decimal import Decimal
from pathlib import Path

import pymupdf
import requests

from . import config, store
from .units import detect_units

log = logging.getLogger("mcr.gnma")

INDEX_URL = "https://www.ginniemae.gov/about-us/what-we-do/budget-performance/annual-reports"
REPORT_URL = "https://www.ginniemae.gov/about_us/what_we_do/Annual_Reports/annual_report{yy:02d}.pdf"
FIRST_FY = 1999  # earliest English annual report on the site that is a PDF (1996-1998 URLs return an HTML error page)
PROVIDER = "GNMA"
MULTIPLIER = {"thousands": 1_000, "millions": 1_000_000, "billions": 1_000_000_000}

# Totals printed in the 2023 report (Notes to the Financial Statements, p. A-20), in USD thousands as published.
# Used ONLY to validate the extraction; the dataset itself is always built from the PDFs.
REFERENCE_TOTALS = {
    2023: {"mbs": 2_472_843_019, "commitments": 140_780_632, "total": 2_613_623_651},
    2022: {"mbs": 2_284_456_605, "commitments": 157_894_490, "total": 2_442_351_095},
}

_NUM = re.compile(r"^\(?\$?\d[\d,]*(?:\.\d+)?\)?$")
_YEAR = re.compile(r"^(?:19|20)\d\d$")
_MEL = re.compile(r"maximum\s+exposure\s+to\s+loss", re.I)
_LEAD_IN = re.compile(r"outstanding\s+mbs(?:\s+securities)?\s+and\s+commitments\s+were\s+as\s+follows", re.I)
_NOTE = re.compile(r"^(Note\s+(?:\d+|[A-Z])\s*[:\-–—]\s*[^.]{3,140})$")
_PAGE_LABEL = re.compile(r"^[A-Z]{1,2}-\d{1,3}$")
YEAR_ASSUMED = "column years assumed from the report's fiscal year (current year printed first); needs confirmation by another report"


# ------------------------------------------------------------------ data
@dataclass
class Figure:
    """One year's figures from one report, as published, plus the exact USD values and provenance."""

    fiscal_year: int
    reporting_date: str  # ISO, e.g. 2023-09-30
    role: str  # current (the report's own fiscal year) | comparative (prior-year column)
    source_report: str
    source_url: str
    pdf_page: int  # 1-based
    printed_page: str  # label printed on the page, e.g. A-20 ('' if none found)
    note: str  # nearest preceding "Note N: ..." heading ('' if none found)
    table_title: str
    table_kind: str  # maximum_exposure_to_loss | off_balance_sheet_table
    units: str  # thousands | millions | billions (as stated in the file)
    mbs_raw: str  # as printed
    commitments_raw: str
    total_raw: str  # '' when the table prints no total row
    mbs_usd: int
    commitments_usd: int
    total_usd: int  # always mbs_usd + commitments_usd
    reported_total_usd: int | None
    precision_usd: int  # size of one printed unit in USD (1,000 for thousands; 100,000,000 for $0.1bn)
    flags: list = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not any(f.startswith("FAIL") for f in self.flags)

    def published(self, usd: int) -> str:
        """An amount in the report's own unit and decimals, e.g. $2,613,623,651 (USD thousands as printed)."""
        dec = max(_decimals(self.mbs_raw), _decimals(self.commitments_raw))
        return f"${Decimal(usd) / MULTIPLIER[self.units]:,.{dec}f}"

    def as_published_total(self) -> str:
        """Total in the report's own unit with the report's own decimals, e.g. $2,613,623,651 (USD thousands)."""
        return f"{self.published(self.total_usd)} (USD {self.units})"


def _decimals(raw: str) -> int:
    return len(raw.split(".")[1]) if "." in raw else 0


def fmt_usd(v: int | None) -> str:
    return "—" if v is None else f"${v:,}"


def to_usd(raw: str, units: str) -> int:
    d = Decimal(re.sub(r"[^\d.]", "", raw)) * MULTIPLIER[units]
    if d != d.to_integral_value():
        raise ValueError(f"{raw!r} in {units} is not a whole number of dollars")
    return int(d)


def report_filename(fy: int) -> str:
    return f"annual_report{fy % 100:02d}.pdf"


def report_url(fy: int) -> str:
    return REPORT_URL.format(yy=fy % 100)


# ------------------------------------------------------------------ PDF reading
def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def page_rows(page, tol: float = 3.0) -> list[list[tuple]]:
    """Words grouped into visual rows (top to bottom, left to right); overprinted duplicate words are collapsed."""
    ws = sorted(page.get_text("words"), key=lambda w: ((w[1] + w[3]) / 2, w[0]))
    rows, cur, cy = [], [], None
    for w in ws:
        y = (w[1] + w[3]) / 2
        if cy is None or abs(y - cy) <= tol:
            cur.append(w)
            cy = y if cy is None else cy
        else:
            rows.append(cur)
            cur, cy = [w], y
    if cur:
        rows.append(cur)
    out = []
    for r in rows:
        r = sorted(r, key=lambda w: w[0])
        keep = []
        for w in r:
            if not any(k[4] == w[4] and abs(k[0] - w[0]) < 1.5 for k in keep):
                keep.append(w)
        out.append(keep)
    return out


def _text(row) -> str:
    return " ".join(w[4] for w in row)


def _numeric_after(row, start: int) -> list[tuple[str, float]]:
    """(token, x0) for numeric tokens right of word index `start`, dropping overprint fragments of a longer number."""
    toks = [(w[4].strip("()$ ,"), w[0]) for w in row[start:] if _NUM.match(w[4]) and re.search(r"\d", w[4])]
    digits = lambda t: re.sub(r"\D", "", t)  # noqa: E731
    return [(t, x) for t, x in toks
            if not any(len(digits(o)) > len(digits(t)) and digits(t) in digits(o) for o, _ in toks)]


def _match(row, kind: str, x_ref: float | None = None):
    """(numbers, label_x0) when the row carries the label for `kind` (mbs | commitments | total) followed by numbers.

    Anchored on the label words, so text sharing the visual row (two-column pages) cannot leak into the values;
    `x_ref` keeps commitments / total rows aligned with the Outstanding MBS label of the same table.
    """
    low = [w[4].lower().strip(":") for w in row]
    for k in range(len(row)):
        if kind == "total":
            if low[k] != "total":
                continue
            start = k + 1
        elif low[k] == "outstanding" and k + 1 < len(row) and low[k + 1] == "mbs":
            commit = k + 2 < len(row) and low[k + 2].startswith("commitment")
            if (kind == "commitments") != commit:
                continue
            start = k + 3 if commit else k + 2
            if not commit and start < len(row) and low[start] == "securities":
                start += 1
        else:
            continue
        if x_ref is not None and abs(row[k][0] - x_ref) > 40:
            continue
        nums = _numeric_after(row, start)
        if nums:
            return nums, row[k][0]
    return None

def printed_page_label(page) -> str:
    h = page.rect.height
    words = [w for w in page.get_text("words") if w[1] > h * 0.88]
    for w in words:
        if _PAGE_LABEL.match(w[4]):
            return w[4]
    nums = [w[4] for w in words if re.fullmatch(r"\d{1,3}", w[4])]
    return nums[0] if len(nums) == 1 else ""


def report_fiscal_year(doc, fallback: int) -> int:
    """Fiscal year named on the first pages ('Fiscal Year 2023' / 'FY 2023'); the file-name year if none is found."""
    text = " ".join(doc[i].get_text() for i in range(min(4, len(doc))))
    years = re.findall(r"(?:Fiscal\s+Year|FY)\s+(20\d\d|19\d\d)", text, re.I)
    return int(max(set(years), key=years.count)) if years else fallback


# ------------------------------------------------------------------ table location
@dataclass
class _Table:
    page_index: int
    title: str
    kind: str
    mbs: list
    commitments: list
    total: list | None
    years: list
    units: str | None
    date_printed: bool
    note: str
    printed_page: str
    problems: list


def _find_tables(doc) -> tuple[list[_Table], list[str]]:
    tables, hints = [], []
    lead_pages: list[int] = []
    rows_cache: dict[int, list] = {}

    def rows_of(i):
        if i not in rows_cache:
            rows_cache[i] = page_rows(doc[i])
        return rows_cache[i]

    for pi in range(len(doc)):
        raw = _norm(doc[pi].get_text())
        if "outstanding mbs" not in raw.lower():
            continue
        rows = rows_of(pi)
        for i, row in enumerate(rows):
            m = _match(row, "mbs")
            if not m:
                continue
            mbs, x_ref = m
            com = j = None
            for k in range(i + 1, min(i + 4, len(rows))):
                if (c := _match(rows[k], "commitments", x_ref)):
                    com, j = c[0], k
                    break
            if com is None:
                continue
            tot = None
            for k in range(j + 1, min(j + 4, len(rows))):
                if (tt := _match(rows[k], "total", x_ref)):
                    tot = tt[0]
                    break
            tables.append(_describe(doc, pi, rows_of, i, mbs, com, tot))
        if _LEAD_IN.search(raw):
            lead_pages.append(pi + 1)
    if not tables and lead_pages:
        hints.append(f"table introduced on pdf page {lead_pages[0]} but its values are not in the PDF text layer (not machine-readable)")
    return tables, hints


def _segments(row, gap: float = 40.0) -> list[str]:
    """Split a visual row into column segments (words separated by a wide gap), so two-column pages don't merge text."""
    segs, cur, last = [], [], None
    for w in row:
        if last is not None and w[0] - last > gap:
            segs.append(" ".join(cur))
            cur = []
        cur.append(w[4])
        last = w[2]
    if cur:
        segs.append(" ".join(cur))
    return segs


def _nearest_note(doc, pi, rows_of, upto_row: int) -> str:
    """Nearest preceding 'Note N: Title' heading (best effort; looks back up to 30 pages)."""
    for back in range(0, 31):
        if pi - back < 0:
            break
        rows = rows_of(pi - back)
        for r in reversed(rows[:upto_row] if back == 0 else rows):
            for seg in reversed(_segments(r)):
                m = _NOTE.match(seg)
                if m:
                    return m.group(1)
    return ""


def _describe(doc, pi, rows_of, i, mbs, com, tot) -> _Table:
    rows = rows_of(pi)
    n = len(mbs)
    problems = []
    if len(com) != n or (tot is not None and len(tot) != n):
        problems.append(f"row shapes differ (MBS {n}, commitments {len(com)}, total {len(tot) if tot else '-'} numbers)")
    lo, hi = min(x for _, x in mbs) - 90, max(x for _, x in mbs) + 90

    # context rows above the table: this page, then up to two earlier pages (the header may sit on the previous page)
    above = [(pi, r) for r in rows[:i + 1]]
    for back in (1, 2):
        if pi - back >= 0:
            above = [(pi - back, r) for r in rows_of(pi - back)] + above
    near = above[-40:]

    title, kind = "", "off_balance_sheet_table"
    for _, r in reversed(above[-8:]):
        if _MEL.search(_text(r)):
            title, kind = "Maximum exposure to loss", "maximum_exposure_to_loss"
            break
    if not title:
        lead = _LEAD_IN.search(_norm(doc[max(pi - 1, 0)].get_text() + " " + doc[pi].get_text()))
        title = "Outstanding MBS and commitments" + (" (table introduced by 'Outstanding MBS and commitments were as follows')" if lead else "")

    years = []
    for _, r in reversed(near):
        ys = [(w[4], w[0]) for w in r if _YEAR.match(w[4].strip(":,")) and lo <= w[0] <= hi]
        if len(ys) == n:
            years = [int(y.strip(":,")) for y, _ in sorted(ys, key=lambda p: p[1])]
            break

    units = None
    for _, r in reversed(above):
        units = detect_units(_text(r))
        if units:
            break

    date_printed = any(re.search(r"september\s+30", _text(r), re.I) for _, r in near)
    note = _nearest_note(doc, pi, rows_of, i)
    return _Table(pi, title, kind, mbs, com, tot, years, units, date_printed, note, printed_page_label(doc[pi]), problems)



# ------------------------------------------------------------------ extraction
@dataclass
class ReportResult:
    fiscal_year: int
    source_report: str
    figures: list
    gaps: list  # reasons no figure could be extracted / was extracted reliably


def extract_report(path: str | Path, fy: int, source_url: str = "") -> ReportResult:
    """Parse one annual report. Returns every figure found (current + comparative) and any documented gaps."""
    path = Path(path)
    name = path.name
    gaps: list[str] = []
    with pymupdf.open(path) as doc:
        rfy = report_fiscal_year(doc, fy)
        tables, hints = _find_tables(doc)
    rank = {"maximum_exposure_to_loss": 0, "off_balance_sheet_table": 1}
    tables.sort(key=lambda t: (rank[t.kind], t.page_index))
    if not tables:
        gaps += hints or ["no 'Outstanding MBS' / 'Outstanding MBS commitments' table found in the report text"]
        return ReportResult(fy, name, [], gaps)

    primary = tables[0]
    figures = _figures(primary, fy, name, source_url, rfy)
    # Other tables in the same report (e.g. the rounded-to-$ billions table in Note 4) must agree with the primary one,
    # within the coarser table's rounding.
    for other in tables[1:]:
        for fg in _figures(other, fy, name, source_url, rfy):
            mine = next((f for f in figures if f.fiscal_year == fg.fiscal_year), None)
            if mine and fg.ok and mine.ok and abs(mine.total_usd - fg.total_usd) > max(mine.precision_usd, fg.precision_usd):
                mine.flags.append(f"FAIL: pdf page {fg.pdf_page} prints a different FY{fg.fiscal_year} total than pdf page {mine.pdf_page}")
    if rfy != fy:
        for f in figures:
            f.flags.append(f"WARN: the report cover names fiscal year {rfy}, but the file is {name} (FY{fy})")
    gaps += [f"{fl.removeprefix('FAIL: ')}" for f in figures for fl in f.flags if fl.startswith("FAIL")]
    return ReportResult(fy, name, figures, gaps)


def _figures(t: _Table, fy: int, name: str, url: str, rfy: int) -> list[Figure]:
    n = len(t.mbs)
    flags_common = [f"FAIL: {p}" for p in t.problems]
    if t.units is None:
        flags_common.append("FAIL: no 'Dollars in ...' unit statement found above the table")
    years = t.years
    if len(years) != n:
        # Header unreadable in the text layer. Ginnie Mae always prints the current year first, so assume
        # [FY, FY-1, ...] and flag it; validate() requires another report to confirm every such column.
        years = [fy - k for k in range(n)]
        flags_common.append(f"WARN: {YEAR_ASSUMED} (header years found: {t.years or 'none'})")
    if flags_common and any(f.startswith("FAIL") for f in flags_common):
        return [_failed(t, fy, name, url, "; ".join(f.removeprefix("FAIL: ") for f in flags_common if f.startswith("FAIL")))]
    out = []
    for k in range(n):
        year = years[k]
        role = "current" if year == max(years) and year == fy else "comparative"
        flags = list(flags_common)
        if role == "current" and year != fy:
            flags.append("FAIL: first column year does not match the report's fiscal year")
        mbs_raw, com_raw = t.mbs[k][0], t.commitments[k][0]
        tot_raw = t.total[k][0] if t.total else ""
        try:
            mbs, com = to_usd(mbs_raw, t.units), to_usd(com_raw, t.units)
            rep = to_usd(tot_raw, t.units) if tot_raw else None
        except (ValueError, KeyError) as e:
            out.append(_failed(t, fy, name, url, f"unparseable number: {e}"))
            continue
        if rep is not None and rep != mbs + com:
            flags.append(f"FAIL: printed total {tot_raw} != Outstanding MBS {mbs_raw} + commitments {com_raw}")
        if rep is None:
            flags.append("INFO: table prints no total row; total computed as Outstanding MBS + commitments")
        if not 10**10 < mbs + com < 10**14:
            flags.append("FAIL: total is outside the plausible range ($10bn to $100tn); check units")
        if not t.date_printed:
            flags.append("WARN: 'September 30' not found near the table; reporting date assumed to be the fiscal year end")
        if t.kind != "maximum_exposure_to_loss":
            flags.append("INFO: this report has no 'Maximum exposure to loss' heading; figures are from the off-balance-sheet note's "
                         "Outstanding MBS / commitments table")
        prec = MULTIPLIER[t.units] // 10 ** max(_decimals(mbs_raw), _decimals(com_raw))
        if prec > MULTIPLIER["thousands"]:
            flags.append(f"INFO: published rounded to {prec:,} USD")
        out.append(Figure(
            fiscal_year=year, reporting_date=date(year, 9, 30).isoformat(), role=role, source_report=name, source_url=url,
            pdf_page=t.page_index + 1, printed_page=t.printed_page, note=t.note, table_title=t.title, table_kind=t.kind,
            units=t.units, mbs_raw=mbs_raw, commitments_raw=com_raw, total_raw=tot_raw, mbs_usd=mbs, commitments_usd=com,
            total_usd=mbs + com, reported_total_usd=rep, precision_usd=prec, flags=flags))
    return out


def _failed(t: _Table, fy: int, name: str, url: str, why: str) -> Figure:
    """A placeholder that is flagged FAIL and carries no numbers, so a bad table can never look valid."""
    return Figure(fy, date(fy, 9, 30).isoformat(), "current", name, url, t.page_index + 1, t.printed_page, t.note, t.title, t.kind,
                  t.units or "", "", "", "", 0, 0, 0, None, 0, [f"FAIL: {why}"])


# ------------------------------------------------------------------ validation
def validate(figures: list[Figure]) -> list[dict]:
    """Checks that must hold for the dataset. Each: {name, status (pass|fail|warn), detail}."""
    checks = []
    bad = [f for f in figures if f.total_usd != f.mbs_usd + f.commitments_usd]
    checks.append({"name": "Total = Outstanding MBS + commitments (every observation)", "status": "fail" if bad else "pass",
                   "detail": f"{len(figures)} observation(s) checked" + (f"; violated: {[(f.fiscal_year, f.source_report) for f in bad]}" if bad else "")})
    printed = [f for f in figures if f.reported_total_usd is not None]
    bad = [f for f in printed if f.reported_total_usd != f.total_usd]
    checks.append({"name": "Printed total equals computed total", "status": "fail" if bad else "pass",
                   "detail": f"{len(printed)} observation(s) print a total row" + (f"; violated: {[(f.fiscal_year, f.source_report) for f in bad]}" if bad else "")})
    for fy, ref in REFERENCE_TOTALS.items():
        own = next((f for f in figures if f.fiscal_year == fy and f.role == "current"), None)
        if own is None:
            checks.append({"name": f"FY{fy} equals the reference total", "status": "fail", "detail": "no FY%d observation extracted" % fy})
            continue
        got = (own.mbs_usd, own.commitments_usd, own.total_usd)
        want = tuple(ref[k] * MULTIPLIER["thousands"] for k in ("mbs", "commitments", "total"))
        checks.append({"name": f"FY{fy} equals the reference total ${ref['total']:,} (USD thousands)", "status": "pass" if got == want else "fail",
                       "detail": f"extracted {own.as_published_total()}"})
    fails = [f for f in figures if not f.ok]
    checks.append({"name": "No extraction failures", "status": "fail" if fails else "pass",
                   "detail": "; ".join(f"FY{f.fiscal_year} {f.source_report}: {fl}" for f in fails for fl in f.flags if fl.startswith("FAIL")) or "none"})
    rec = reconcile(figures)
    assumed = [f for f in figures if any(YEAR_ASSUMED in fl for fl in f.flags)]
    unconfirmed = [f for f in assumed if not any(
        r["fiscal_year"] == f.fiscal_year and r["component"] == "Total" and f.source_report in (r["report_a"], r["report_b"])
        and r["status"].startswith("match") for r in rec)]
    checks.append({"name": "Columns with an unreadable year header are confirmed by another report",
                   "status": "fail" if unconfirmed else "pass",
                   "detail": (f"{len(assumed)} column(s) assumed; unconfirmed: {[(f.fiscal_year, f.source_report) for f in unconfirmed]}"
                              if unconfirmed else f"{len(assumed)} column(s) assumed, all confirmed")})
    odd = [r for r in rec if r["status"] in ("MISMATCH", "differs by one rounding unit")]
    checks.append({"name": "Comparative figures in successive reports reconcile", "status": "warn" if odd else "pass",
                   "detail": (f"{len(rec)} comparison(s); " + "; ".join(
                       f"FY{r['fiscal_year']} {r['component']}: {r['report_a']} vs {r['report_b']} ({r['status']})" for r in odd))
                   if odd else f"{len(rec)} comparison(s), all match"})
    return checks


def reconcile(figures: list[Figure]) -> list[dict]:
    """Compare every figure printed for the same fiscal year in different reports (own report vs later comparatives)."""
    by: dict[int, list[Figure]] = {}
    for f in figures:
        if f.ok:
            by.setdefault(f.fiscal_year, []).append(f)
    out = []
    for fy in sorted(by):
        group = sorted(by[fy], key=lambda f: (f.role != "current", f.source_report))
        base = group[0]
        for other in group[1:]:
            if other.source_report == base.source_report:
                continue
            unit = max(base.precision_usd, other.precision_usd)
            for comp, a, b in (("Outstanding MBS", base.mbs_usd, other.mbs_usd),
                               ("Outstanding MBS commitments", base.commitments_usd, other.commitments_usd),
                               ("Total", base.total_usd, other.total_usd)):
                diff = abs(a - b)
                if diff == 0:
                    status = "match"
                elif diff * 2 <= unit:
                    status = "match within rounding"
                elif diff <= unit:
                    status = "differs by one rounding unit"
                else:
                    status = "MISMATCH"
                out.append({"fiscal_year": fy, "component": comp, "report_a": base.source_report, "usd_a": a,
                            "report_b": other.source_report, "usd_b": b, "difference_usd": a - b, "status": status})
    return out


# ------------------------------------------------------------------ fetch + ingest
def download(fy: int) -> Path:
    url = report_url(fy)
    dest = config.RAW_DIR / "ginnie" / report_filename(fy)
    dest.parent.mkdir(parents=True, exist_ok=True)
    r = requests.get(url, headers={"User-Agent": config.USER_AGENT}, timeout=300)
    r.raise_for_status()
    if not r.content.startswith(b"%PDF"):
        raise RuntimeError(f"not a PDF (content-type {r.headers.get('Content-Type', '?')}); the report is probably not published")
    dest.write_bytes(r.content)
    store.log_fetch(url, "ok", f"downloaded {len(r.content):,} bytes")
    return dest


def current_fiscal_year(today: date | None = None) -> int:
    today = today or date.today()
    return today.year + (1 if today.month >= 10 else 0)


def ingest_report(fy: int, fetch: bool = True, path=None) -> ReportResult:
    """Download (if needed), extract and store one report. Never raises for a missing/unreadable report: it records a gap."""
    src = config.RAW_DIR / "ginnie" / report_filename(fy)
    if fetch and not src.exists():
        try:
            download(fy)
        except Exception as e:
            store.log_fetch(report_url(fy), "error", str(e))
            res = ReportResult(fy, report_filename(fy), [], [f"report not retrievable from {report_url(fy)}: {e}"])
            store.save_gnma(res, path)
            return res
    if not src.exists():
        res = ReportResult(fy, report_filename(fy), [], [f"{report_filename(fy)} is not in raw/ginnie (run with fetch enabled)"])
    else:
        try:
            res = extract_report(src, fy, report_url(fy))
        except Exception as e:
            log.exception("GNMA extraction failed for %s", src)
            res = ReportResult(fy, report_filename(fy), [], [f"extraction error: {e}"])
    store.save_gnma(res, path)
    return res


def ingest_all(fetch: bool = True, first: int = FIRST_FY, last: int | None = None, path=None) -> list[ReportResult]:
    """Every report from `first` to the last completed fiscal year (its report may not be published yet: recorded as a gap)."""
    return [ingest_report(fy, fetch, path) for fy in range(first, (last or current_fiscal_year() - 1) + 1)]


# ------------------------------------------------------------------ read back for the dashboard
def load_figures(path=None) -> list[Figure]:
    out = []
    for r in store.rows("SELECT * FROM gnma_exposure ORDER BY fiscal_year, source_report, role", path=path):
        r = dict(r)
        r["flags"] = json.loads(r["flags"] or "[]")
        for k in ("mbs_usd", "commitments_usd", "total_usd"):
            r[k] = int(r[k])
        r["reported_total_usd"] = int(r["reported_total_usd"]) if r["reported_total_usd"] not in (None, "") else None
        r.pop("ingested_at", None)
        out.append(Figure(**r))
    return out


def headline_series(figures: list[Figure]) -> list[Figure]:
    """One observation per fiscal year, oldest first. The report's own figure wins; a comparative is used only if that
    year has no report of its own (e.g. FY2011 from the FY2012 report) and is flagged as such."""
    best: dict[int, Figure] = {}
    for f in figures:
        if not f.ok or not f.total_usd:
            continue
        cur = best.get(f.fiscal_year)
        if cur is None or (f.role == "current" and cur.role != "current"):
            best[f.fiscal_year] = f
        elif f.role == cur.role == "comparative" and f.source_report > cur.source_report:
            best[f.fiscal_year] = f
    out = []
    for fy in sorted(best):
        f = best[fy]
        if f.role == "comparative" and "INFO: comparative figure from a later report" not in f.flags:
            f.flags.append("INFO: comparative figure from a later report; the FY%d report itself has no extractable table" % fy)
        out.append(f)
    return out


def load_gaps(path=None) -> list[dict]:
    return store.rows("SELECT fiscal_year, source_report, reason FROM gnma_gaps ORDER BY fiscal_year, reason", path=path)


def figure_dict(f: Figure) -> dict:
    return asdict(f)
