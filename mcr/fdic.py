"""FDIC Deposit Insurance Fund (DIF) headline figures, built from the official FDIC Annual Report's
"Financial Section" (the audited financial statements + MD&A), one PDF per calendar year.

Three data points per year, all transcribed from the Financial Section only (per explicit source instruction -
a more precise exact-dollar insured-deposits figure exists in the Appendices, but is intentionally NOT used here):

* Fund Balance - Ending: the DIF's exact ending fund balance for the year, in $ thousands, from the "Statement of
  Income and Fund Balance" (or equivalent). Each report also states the prior year's ending balance alongside it,
  which is kept too so the year-over-year chain can be cross-checked (see `validate()`).
* Minimum Reserve Ratio: the DIF's statutory minimum reserve ratio in effect for that report (1.15% under the
  Federal Deposit Insurance Reform Act of 2005, 2006-2009; raised to 1.35% by the Dodd-Frank Act, 2010-2024). This
  is distinct from the FDIC Board's discretionary Designated Reserve Ratio (DRR, e.g. 2.0% from 2011 onward), which
  is NOT what is stored here.
* Estimated Insured Deposits: the DIF's "Off-Balance-Sheet Exposure: Deposit Insurance" note, a rounded ($0.1
  trillion precision) estimate with its own "as of" date (not always December 31 of the data year - several years
  use September 30 of the data year instead, which is preserved exactly).

Sources: 2020-2024 downloaded directly from www.fdic.gov; 2006-2018 are embedded in the full combined annual
report (pre-2019 reports are not split into numbered sections) and were retrieved from archive.fdic.gov via the
Wayback Machine (the archive.fdic.gov site itself blocks direct automated downloads).

Every data point's `quote` is the exact (whitespace-normalized) sentence/snippet it was transcribed from, and is
re-verified against the PDF's own extracted text at every ingest - if a quote can no longer be located (e.g. a
revised file), that specific value is dropped and recorded as a gap, never kept stale.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path

import pymupdf
import requests

from . import config, store

log = logging.getLogger("mcr.fdic")

PROVIDER = "FDIC"
INDEX_URL = "https://www.fdic.gov/financial-reports/annual-reports"

# archive.fdic.gov document IDs for the pre-2019 combined annual reports (citation_pdf_url pattern:
# https://archive.fdic.gov/view/fdic/{id}/fdic_{id}_DS1.pdf), recovered via the Wayback Machine.
_ARCHIVE_ID = {
    "2006": "635", "2007": "633", "2008": "221", "2009": "215", "2010": "207", "2011": "199",
    "2012": "195", "2013": "193", "2014": "187", "2015": "185", "2016": "182", "2017": "178", "2018": "14270",
}

# report_key (= calendar year) -> (title, source URL). Financial Section only.
REPORTS: dict[str, tuple[str, str]] = {
    "2024": ("FDIC 2024 Annual Report - Financial Section", "https://www.fdic.gov/financial-reports/2024-annual-report-section4.pdf"),
    "2023": ("FDIC 2023 Annual Report - Financial Section", "https://www.fdic.gov/about/financial-reports/reports/2023annualreport/ar23section5.pdf"),
    "2022": ("FDIC 2022 Annual Report - Financial Section", "https://www.fdic.gov/about/financial-reports/reports/2022annualreport/ar22section5.pdf"),
    "2021": ("FDIC 2021 Annual Report - Financial Section", "https://www.fdic.gov/about/financial-reports/reports/2021annualreport/ar21section5.pdf"),
    "2020": ("FDIC 2020 Annual Report - Financial Section", "https://www.fdic.gov/about/financial-reports/reports/2020annualreport/ar20section5.pdf"),
    "2019": ("FDIC 2019 Annual Report - Financial Section", "https://www.fdic.gov/media/170661"),
    **{
        year: (f"FDIC {year} Annual Report (combined; Financial Section embedded)",
               f"https://archive.fdic.gov/view/fdic/{aid}/fdic_{aid}_DS1.pdf")
        for year, aid in _ARCHIVE_ID.items()
    },
}


def report_filename(report_key: str) -> str:
    return f"fdic_{report_key}_annual_report.pdf"


def report_url(report_key: str) -> str:
    return REPORTS[report_key][1]


@dataclass
class DataPoint:
    """One calendar year's three headline DIF figures, each independently quote-verified against the report PDF."""

    report_key: str
    fund_balance_ending: int | None = None  # $ thousands, exact
    fund_balance_prior: int | None = None  # $ thousands, exact - this report's own stated prior-year figure
    fund_balance_quote: str = ""
    min_reserve_ratio_pct: float | None = None
    min_reserve_ratio_quote: str = ""
    insured_deposits_trillions: float | None = None
    insured_deposits_as_of: str = ""
    insured_deposits_quote: str = ""


@dataclass
class Report:
    report_key: str
    title: str
    point: DataPoint | None = None


# Hand-transcribed from each report's Financial Section. $ figures in thousands as printed ("Dollars in Thousands").
REPORT_POINTS: dict[str, DataPoint] = {
    "2006": DataPoint("2006", 50_165_307, 48_596_602,
                      "Fund Balance - Ending $ 50,165,307 $ 48,596,602",
                      1.15, "Establishes a range for the Designated Reserve Ratio (DRR) of 1.15 percent to 1.50 "
                            "percent, and allows the FDIC to manage the reserve ratio within this range.",
                      4.1, "September 30, 2006",
                      "As of September 30, 2006, the estimated insured deposits for DIF were $4.1 trillion."),
    "2007": DataPoint("2007", 52_413_036, 50_165_307,
                      "Fund Balance - Ending $ 52,413,036 $ 50,165,307",
                      1.15, "establish a range for the DRR from 1.15 to 1.50 percent of estimated insured deposits "
                            "and eliminate the fixed DRR of 1.25 percent.",
                      4.2, "September 30, 2007",
                      "As of September 30, 2007, the estimated insured deposits for DIF were $4.2 trillion."),
    "2008": DataPoint("2008", 17_276_289, 52_413_036,
                      "Fund Balance \u2013 Ending $17,276,289 $52,413,036",
                      1.15, "establishing a range for the DRR from 1.15 to 1.50 percent of estimated insured deposits.",
                      4.8, "December 31, 2008",
                      "As of December 31, 2008, the estimated insured deposits for DIF were $4.8 trillion."),
    "2009": DataPoint("2009", -20_861_797, 17_276_289,
                      "Fund Balance\u2014Ending $ (20,861,797) $ 17,276,289",
                      1.15, "mandated minimum reserve ratio of 1.15 percent of estimated insured deposits.",
                      5.4, "December 31, 2009",
                      "As of December 31, 2009, the estimated insured deposits for DIF were $5.4 trillion."),
    "2010": DataPoint("2010", -7_352_240, -20_861_797,
                      "Fund Balance - Ending $(7,352,240) $(20,861,797)",
                      1.35, "the statutory requirement that the fund reserve ratio increase from 1.15 percent to "
                            "1.35 percent by September 30, 2020",
                      6.2, "December 31, 2010",
                      "As of December 31, 2010, the estimated insured deposits for DIF were $6.2 trillion."),
    "2011": DataPoint("2011", 11_826_532, -7_352_240,
                      "Fund Balance - Ending $11,826,532 $(7,352,240)",
                      1.35, "The Act also requires that the FDIC offset the effect on institutions with less than "
                            "$10 billion in assets of increasing the reserve ratio from 1.15 percent to 1.35 percent.",
                      7.0, "December 31, 2011",
                      "As of December 31, 2011, estimated insured deposits for the DIF were $7.0 trillion."),
    "2012": DataPoint("2012", 32_957_767, 11_826_532,
                      "Fund Balance - Ending $32,957,767 $11,826,532",
                      1.35, "The Act also requires that the FDIC offset the effect on institutions with less than "
                            "$10 billion in assets of increasing the reserve ratio from 1.15 percent to 1.35 percent.",
                      7.3, "September 30, 2012",
                      "As of September 30, 2012 and December 31, 2011, estimated insured deposits for the DIF were "
                      "$7.3 trillion and $7.0 trillion, respectively, including $1.5 trillion and $1.4 trillion, "
                      "respectively, of noninterest-bearing transaction deposits that exceeded the basic limit of "
                      "$250,000 per account."),
    "2013": DataPoint("2013", 47_190_839, 32_957_767,
                      "Fund Balance - Ending $47,190,839 $32,957,767",
                      1.35, "The Act also requires that the FDIC offset the effect on institutions with less than "
                            "$10 billion in assets of increasing the reserve ratio from 1.15 percent to 1.35 percent.",
                      6.0, "December 31, 2013",
                      "As of December 31, 2013 and 2012, estimated insured deposits for the DIF were $6.0 trillion "
                      "and $7.4 trillion, respectively."),
    "2014": DataPoint("2014", 62_780_177, 47_190_839,
                      "Fund Balance - Ending $62,780,177 $47,190,839",
                      1.35, "The Act also requires that the FDIC offset the effect on institutions with less than "
                            "$10 billion in assets of increasing the reserve ratio from 1.15 percent to 1.35 percent.",
                      6.1, "September 30, 2014",
                      "As of September 30, 2014 and December 31, 2013, estimated insured deposits for the DIF were "
                      "$6.1 trillion and $6.0 trillion, respectively."),
    "2015": DataPoint("2015", 72_600_235, 62_780_177,
                      "Fund Balance - Ending $72,600,235 $62,780,177",
                      1.35, "The Dodd-Frank Act raised the minimum reserve ratio of the DIF from 1.15 percent to "
                            "1.35 percent and requires that the reserve ratio reach that level by September 30, 2020.",
                      6.4, "September 30, 2015",
                      "As of September 30, 2015 and December 31, 2014, estimated insured deposits for the DIF were "
                      "$6.4 trillion and $6.2 trillion, respectively."),
    "2016": DataPoint("2016", 83_161_515, 72_600_235,
                      "Fund Balance - Ending $ 83,161,515 $ 72,600,235",
                      1.35, "The Dodd-Frank Act raised the minimum reserve ratio of the DIF from 1.15 percent to "
                            "1.35 percent",
                      6.8, "September 30, 2016",
                      "As of September 30, 2016 and December 31, 2015, estimated insured deposits for the DIF were "
                      "$6.8 trillion and $6.5 trillion, respectively."),
    "2017": DataPoint("2017", 92_747_495, 83_161_515,
                      "Fund Balance - Ending $ 92,747,495 $ 83,161,515",
                      1.35, "Dodd-Frank Act, which increased the minimum reserve ratio of the DIF from 1.15 percent "
                            "to 1.35 percent, requires that the reserve ratio reach that level by September 30, 2020.",
                      7.1, "September 30, 2017",
                      "As of September 30, 2017 and December 31, 2016, estimated insured deposits for the DIF were "
                      "$7.1 trillion and $6.9 trillion, respectively."),
    "2018": DataPoint("2018", 102_608_924, 92_747_495,
                      "Fund Balance - Ending $ 102,608,924 $ 92,747,495",
                      1.35, "Minimum Reserve Ratio Section 334 of the Dodd-Frank Act, which increased the minimum "
                            "reserve ratio of the DIF from 1.15 percent to 1.35 percent, mandates that the reserve "
                            "ratio reach that level by September 30, 2020.",
                      7.4, "September 30, 2018",
                      "As of September 30, 2018 and December 31, 2017, estimated insured deposits for the DIF were "
                      "$7.4 trillion and $7.2 trillion, respectively."),
    "2019": DataPoint("2019", 110_346_938, 102_608_924,
                      "Fund Balance - Ending $ 110,346,938 $ 102,608,924",
                      1.35, "the Dodd-Frank Act increased the minimum reserve ratio from 1.15 percent to 1.35 percent.",
                      7.7, "September 30, 2019",
                      "As of September 30, 2019 and December 31, 2018, estimated insured deposits for the DIF were "
                      "$7.7 trillion and $7.5 trillion, respectively."),
    "2020": DataPoint("2020", 117_896_765, 110_346_938,
                      "Fund Balance - Ending $ 117,896,765 $ 110,346,938",
                      1.35, "The Dodd-Frank Act increased the minimum reserve ratio for the DIF to 1.35 percent, up "
                            "from the previous statutory minimum of 1.15 percent.",
                      8.9, "September 30, 2020",
                      "As of September 30, 2020 and December 31, 2019, estimated insured deposits for the DIF were "
                      "$8.9 trillion and $7.8 trillion, respectively."),
    # The 2021 report's Statement of Income and Fund Balance text-extracts with the Beginning-balance row's figures
    # immediately preceding the Ending-balance label (a PDF column-layout artifact, not a restatement); the anchor
    # below is the exact (whitespace-normalized) run of text as it appears, and the chain confirms the reading:
    # Ending = 123,141,040 (matches the 2022 report's own stated prior-year figure), prior = 117,896,765 (matches
    # the 2020 report's own Ending figure).
    "2021": DataPoint("2021", 123_141_040, 117_896_765,
                      "Fund Balance - Ending $ 117,896,765 123,141,040 $ 110,346,938 117,896,765",
                      1.35, "To implement this requirement, the FDIC provided for credits against quarterly "
                            "assessments to small banks for their contribution to the growth in the reserve ratio "
                            "from 1.15 percent to 1.35 percent.",
                      9.6, "September 30, 2021",
                      "As of September 30, 2021 and December 31, 2020, estimated insured deposits for the DIF were "
                      "$9.6 trillion and $9.1 trillion, respectively."),
    "2022": DataPoint("2022", 128_217_894, 123_141_040,
                      "Fund Balance - Ending $ 128,217,894 $ 123,141,040",
                      1.35, "The Dodd-Frank Act increased the minimum reserve ratio for the DIF to 1.35 percent, up "
                            "from the previous statutory minimum of 1.15 percent.",
                      9.9, "September 30, 2022",
                      "As of September 30, 2022 and December 31, 2021, estimated insured deposits for the DIF were "
                      "$9.9 trillion and $9.7 trillion, respectively."),
    "2023": DataPoint("2023", 121_777_980, 128_217_894,
                      "Fund Balance - Ending $ 121,777,980 $ 128,217,894",
                      1.35, "The Dodd-Frank Act increased the minimum reserve ratio for the DIF to 1.35 percent, up "
                            "from the previous statutory minimum of 1.15 percent.",
                      10.6, "September 30, 2023",
                      "As of September 30, 2023 and December 31, 2022, estimated insured deposits for the DIF were "
                      "$10.6 trillion and $10.3 trillion, respectively."),
    "2024": DataPoint("2024", 137_101_160, 121_777_980,
                      "Fund Balance - Ending $ 137,101,160 $ 121,777,980",
                      1.35, "The Dodd-Frank Act increased the minimum reserve ratio for the DIF to 1.35 percent, up "
                            "from the previous statutory minimum of 1.15 percent.",
                      10.6, "September 30, 2024",
                      "As of September 30, 2024 and December 31, 2023, estimated insured deposits for the DIF were "
                      "$10.6 trillion."),
}


def period_sort_key(report_key: str) -> int:
    return int(report_key[:4])


# ------------------------------------------------------------------ download
def fetch_missing(report_keys: list[str] | None = None) -> list[str]:
    """Download any report in `report_keys` (default: all of REPORTS) not already present in raw/fdic/."""
    dest_dir = config.RAW_DIR / "fdic"
    dest_dir.mkdir(parents=True, exist_ok=True)
    downloaded = []
    for key in sorted(report_keys or REPORTS):
        dest = dest_dir / report_filename(key)
        if dest.exists():
            continue
        url = report_url(key)
        r = requests.get(url, headers={"User-Agent": config.USER_AGENT}, timeout=180)
        r.raise_for_status()
        if not r.content.startswith(b"%PDF"):
            store.log_fetch(url, "fail", "response was not a PDF")
            log.warning("%s: response was not a PDF", url)
            continue
        dest.write_bytes(r.content)
        store.log_fetch(url, "ok", f"downloaded {len(r.content):,} bytes")
        log.info("downloaded %s -> %s", url, dest)
        downloaded.append(key)
    return downloaded


# ------------------------------------------------------------------ parsing: verify each quote against the PDF text
def _normalize(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def _full_text(path: Path) -> str:
    doc = pymupdf.open(path)
    return _normalize(" ".join(page.get_text() for page in doc))


def extract_report(path: str | Path, report_key: str) -> tuple[Report, list[str]]:
    """Re-verify each of the three transcribed quotes against the PDF's own extracted text. A quote that can no
    longer be found (e.g. the published PDF was revised) drops only that one value and is reported as a gap -
    the other two values for the same year are kept if their own quotes still verify."""
    path = Path(path)
    title = REPORTS[report_key][0]
    res = Report(report_key=report_key, title=title)
    gaps: list[str] = []
    src = REPORT_POINTS.get(report_key)
    if src is None:
        gaps.append(f"{title}: no transcribed data points for this report")
        return res, gaps
    text = _full_text(path)
    point = DataPoint(report_key=report_key)

    anchor = _normalize(src.fund_balance_quote.split(" ... ")[0])
    if anchor in text:
        point.fund_balance_ending = src.fund_balance_ending
        point.fund_balance_prior = src.fund_balance_prior
        point.fund_balance_quote = src.fund_balance_quote
    else:
        gaps.append(f"{title}: could not re-locate the Fund Balance - Ending sentence in the PDF text")

    anchor = _normalize(src.min_reserve_ratio_quote.split(" ... ")[0])
    if anchor in text:
        point.min_reserve_ratio_pct = src.min_reserve_ratio_pct
        point.min_reserve_ratio_quote = src.min_reserve_ratio_quote
    else:
        gaps.append(f"{title}: could not re-locate the Minimum Reserve Ratio sentence in the PDF text")

    anchor = _normalize(src.insured_deposits_quote.split(" ... ")[0])
    if anchor in text:
        point.insured_deposits_trillions = src.insured_deposits_trillions
        point.insured_deposits_as_of = src.insured_deposits_as_of
        point.insured_deposits_quote = src.insured_deposits_quote
    else:
        gaps.append(f"{title}: could not re-locate the Estimated Insured Deposits sentence in the PDF text")

    res.point = point
    return res, gaps


# ------------------------------------------------------------------ ingest / load
def ingest_all(raw_dir: Path | None = None, db=None, fetch=False) -> list[Report]:
    """Parse every FDIC Financial Section PDF found locally (raw/fdic/*.pdf), optionally downloading missing ones first."""
    raw_dir = raw_dir or (config.RAW_DIR / "fdic")
    if fetch:
        fetch_missing()
    results = []
    for report_key in REPORTS:
        path = raw_dir / report_filename(report_key)
        if not path.exists():
            continue
        try:
            res, gaps = extract_report(path, report_key)
        except Exception as e:  # noqa: BLE001 - keep going; record as a gap, never crash a full backfill
            res, gaps = Report(report_key=report_key, title=REPORTS[report_key][0]), [f"unexpected error parsing {report_key}: {e}"]
            log.exception("failed to parse %s", path)
        store.save_fdic(report_key, report_url(report_key), res, gaps, db)
        results.append(res)
    return results


def load_rows(db=None) -> list[dict]:
    return store.rows("SELECT * FROM fdic_annual ORDER BY report_key", (), db)


def load_gaps(db=None) -> list[dict]:
    return store.rows("SELECT * FROM fdic_gaps ORDER BY report_key", (), db)


# ------------------------------------------------------------------ validation (nothing is stored as "estimated")
def validate(rows: list[dict]) -> list[dict]:
    checks = []
    years = sorted({r["report_key"] for r in rows}, key=period_sort_key)
    expected_years = [str(y) for y in range(2006, 2025)]
    missing = [y for y in expected_years if y not in years]
    checks.append({"name": "Fund Balance - Ending, Minimum Reserve Ratio and Estimated Insured Deposits exist for every year 2006-2024",
                   "status": "warn" if missing else "pass",
                   "detail": f"missing years: {missing}" if missing else f"{len(years)} year(s) covered"})

    by_year = {r["report_key"]: r for r in rows}
    chain_breaks = []
    for y in years:
        r = by_year[y]
        prev_y = str(int(y) - 1)
        prev = by_year.get(prev_y)
        if prev is None or r["fund_balance_prior"] is None or prev["fund_balance_ending"] is None:
            continue
        if r["fund_balance_prior"] != prev["fund_balance_ending"]:
            chain_breaks.append(y)
    checks.append({"name": "Fund Balance - Ending chains: each year's reported prior-year figure matches the "
                           "previous year's own reported ending figure",
                   "status": "fail" if chain_breaks else "pass",
                   "detail": f"chain break(s) in: {chain_breaks}" if chain_breaks else f"{len(years)} year(s) chain consistently"})

    ratios = {r["report_key"]: r["min_reserve_ratio_pct"] for r in rows if r["min_reserve_ratio_pct"] is not None}
    mismatches = [y for y, v in ratios.items() if (int(y) <= 2009 and v != 1.15) or (int(y) >= 2010 and v != 1.35)]
    checks.append({"name": "Minimum Reserve Ratio matches the statutory floor (1.15% for 2006-2009, 1.35% for 2010-2024)",
                   "status": "fail" if mismatches else "pass",
                   "detail": f"unexpected value(s) in: {mismatches}" if mismatches else f"{len(ratios)} year(s) verified"})

    deposits = [r for r in rows if r["insured_deposits_trillions"] is not None]
    missing_asof = [r["report_key"] for r in deposits if not r["insured_deposits_as_of"]]
    checks.append({"name": "Estimated Insured Deposits carries an explicit 'as of' date for every year (not always December 31)",
                   "status": "fail" if missing_asof else "pass",
                   "detail": f"missing as-of date in: {missing_asof}" if missing_asof else f"{len(deposits)} year(s) with an as-of date"})
    return checks


def summary(rows: list[dict]) -> dict:
    years = sorted({r["report_key"] for r in rows}, key=period_sort_key)
    return {"years": len(years), "first_year": years[0] if years else None, "last_year": years[-1] if years else None,
            "reports": len(years)}
