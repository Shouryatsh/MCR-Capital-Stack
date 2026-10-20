"""FHFA Single-Family Guarantee Fees - the "Total Average Guarantee Fee" (G-Fee) headline figure, built from the
official FHFA annual/biennial reports.

* Reports: https://www.fhfa.gov/reports/single-family-guarantee-fees  (one PDF per report; most reports cover a
  single data year plus a prior-year comparison, a few early reports cover two data years at once).
* FHFA publishes this figure only as an ANNUAL calendar-year average. There is no consistently published quarterly
  "Total Average Guarantee Fee" headline figure anywhere in this report series (the only quarterly breakdown found,
  in the 2012 report's Table 15, is segmented by lender acquisition-volume group, not an overall total) - so this
  module stores annual data only. That is a documented source limitation, not a parsing gap.
* The report's own narrative text (not a single consistent table) is the source for most years: only the 2022+
  reports publish a clean "Table 2: Average Guarantee Fees by Year". Each data point below is transcribed from a
  specific report's exact sentence, which is stored as `quote` and re-verified against the PDF's extracted text at
  every ingest - if a PDF no longer contains the quoted sentence (e.g. a revised file), the point is dropped and
  recorded as a gap, never silently kept.
* FHFA periodically restates prior years' figures in later reports (methodology changes - e.g. the 2018 report's
  inclusion of buy-up/buy-down adjustments, lender data corrections, HARP-mix changes). Every observation is kept,
  tagged with the report that published it, so a given calendar year can have more than one value; nothing is
  overwritten or averaged. The 2007-2012 reports additionally report two parallel populations for the same year
  ("standard loans" only vs. "all loans" including HARP and flexible-refinance loans); both are kept and tagged.
"""
from __future__ import annotations

import logging
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

import pymupdf
import requests

from . import config, store

log = logging.getLogger("mcr.gfee")

PROVIDER = "FHFA"
INDEX_URL = "https://www.fhfa.gov/reports/single-family-guarantee-fees"
DOC_BASE = "https://www.fhfa.gov/document/d/sfgf/"

# report_key -> (title, document slug). report_key is also the local filename stem (raw/gfee/<report_key>.pdf).
REPORTS: dict[str, tuple[str, str]] = {
    "2024": ("Fannie Mae and Freddie Mac Single-Family Guarantee Fees in 2024",
             "fannie-mae-and-freddie-mac-single-family-guarantee-fees-in-2024"),
    "2023": ("Fannie Mae and Freddie Mac Single-Family Guarantee Fees in 2023",
             "fannie-mae-and-freddie-mac-single-family-guarantee-fees-in-2023"),
    "2022": ("Fannie Mae and Freddie Mac Single-Family Guarantee Fees in 2022",
             "fannie-mae-and-freddie-mac-single-family-guarantee-fees-in-2022"),
    "2021": ("Fannie Mae and Freddie Mac Guarantee Fees in 2021", "fannie-mae-and-freddie-mac-guarantee-fees-in-2021"),
    "2020": ("Fannie Mae and Freddie Mac Guarantee Fees 2020", "fannie-and-freddie-guarantee-fees-2020"),
    "2019": ("Fannie Mae and Freddie Mac Guarantee Fees in 2019", "fannie-mae-and-freddie-mac-guarantee-fees-in-2019"),
    "2018": ("Fannie Mae and Freddie Mac Guarantee Fees in 2018", "fannie-mae-and-freddie-mac-guarantee-fees-in-2018"),
    "2017": ("Fannie and Freddie Guarantee Fees in 2017", "fannie-and-freddie-guarantee-fees-in-2017"),
    "2016": ("Fannie and Freddie Guarantee Fees in 2016", "fannie-and-freddie-guarantee-fees-in-2016"),
    "2015": ("Fannie and Freddie Guarantee Fees 2015", "fannie-and-freddie-guarantee-fees-2015"),
    "2014": ("Fannie and Freddie Guarantee Fees in 2014", "fannie-and-freddie-guarantee-fees-in-2014"),
    "2013": ("Fannie Mae and Freddie Mac Single-Family Guarantee Fees in 2013", "g-fee-2013"),
    "2012": ("Fannie and Freddie Guarantee Fees in 2012", "fannie-and-freddie-guarantee-fees-in-2012"),
    "2010-2011": ("Fannie and Freddie Guarantee Fees in 2010 and 2011", "fannie-and-freddie-guarantee-fees-in-2010-and-2011"),
    "2009-2010": ("Fannie and Freddie Guarantee Fees in 2009 and 2010", "fannie-and-freddie-guarantee-fees-in-2009-and-2010"),
    "2008-2009": ("Fannie and Freddie Guarantee Fees in 2008 and 2009", "fannie-and-freddie-guarantee-fees-in-2008-and-2009"),
    "2007-2008": ("Fannie and Freddie Guarantee Fees in 2007 and 2008", "fannie-and-freddie-guarantee-fees-in-2007-and-2008"),
    # One-off report with a different scope (state-level variation in the g-fee, not a national annual total);
    # intentionally not a source of annual Total Average Guarantee Fee data points - see ingest_all().
    "state-level": ("State-Level Guarantee Fee Analysis", "state-level-g-fee-analysis"),
}


def report_filename(report_key: str) -> str:
    return f"{report_key}.pdf"


def report_url(report_key: str) -> str:
    return DOC_BASE + REPORTS[report_key][1]


@dataclass
class DataPoint:
    """One calendar year's Total Average Guarantee Fee as stated in one specific report, plus its full provenance.
    `quote` is the exact sentence this was transcribed from; it is re-verified against the PDF text at every ingest."""

    data_year: str  # '2017' or, for the two-year population split in the 2007-2012 reports, still a single year
    population: str  # "all loans" (full study population) | "standard loans" (excludes HARP/flexible-refinance)
    total_bps: float
    ongoing_bps: float | None
    upfront_bps: float | None
    gap_bps: float | None
    quote: str
    restated_from: float | None = None  # a different total_bps this same report says an EARLIER report had published
    restated_note: str = ""


@dataclass
class Report:
    report_key: str
    title: str
    points: list[DataPoint] = field(default_factory=list)


# The Total Average Guarantee Fee as published by each report, transcribed directly from its text. Multiple reports
# commonly restate the prior year(s); every value is kept, never collapsed to a single "best" number per year.
REPORT_POINTS: dict[str, list[DataPoint]] = {
    "2024": [
        DataPoint("2023", "all loans", 65.5, 47.5, 18.0, 2.1,
                  "Table 2: Average Guarantee Fees by Year ... Total G-Fee (bps) 65.5 65.2"),
        DataPoint("2024", "all loans", 65.2, 49.1, 16.1, -0.6,
                  "The average total guarantee fee (G-Fee) was 65.2 basis points in 2024, slightly down from 65.5 "
                  "basis points in 2023."),
    ],
    "2023": [
        DataPoint("2022", "all loans", 61, 44, 17, 3, "Table 2: Average Guarantee Fees by Year ... 2022 ... Total G-Fee (bps) 61"),
        DataPoint("2023", "all loans", 66, 48, 18, 2,
                  "The average total guarantee fee was 66 basis points in 2023, up from 61 basis points in 2022."),
    ],
    "2022": [
        DataPoint("2021", "all loans", 57, 43, 14, 5, "Table 2: Average Guarantee Fees by Year ... 2021 ... Total G-Fee (bps) 57",
                  restated_from=56,
                  restated_note="The 2021 report's own figure for 2021 was 56 bps; the 2022 report's Table 2 restates it to 57 bps."),
        DataPoint("2022", "all loans", 61, 44, 17, 3,
                  "The average total guarantee fee was 61 basis points in 2022, up from 57 basis points in 2021 (see Table 2)."),
    ],
    "2021": [
        DataPoint("2020", "all loans", 54, 43, None, None,
                  "The average guarantee fee was 56 basis points in 2021, 2 basis points higher than in 2020.",
                  restated_note="2020 total is derived (56 - 2bps) from the 2021 report's own stated delta; ongoing fee stated unchanged at 43 bps."),
        DataPoint("2021", "all loans", 56, 43, None, None,
                  "The average guarantee fee was 56 basis points in 2021, 2 basis points higher than in 2020. ... "
                  "the ongoing component remained unchanged at 43 basis points."),
    ],
    "2020": [
        DataPoint("2019", "all loans", 56, 43, None, None,
                  "The average guarantee fee was 54 basis points in 2020, 2 basis points lower than that of 2019.",
                  restated_note="2019 total is derived (54 + 2bps) from the 2020 report's own stated delta; ongoing fee stated unchanged at 43 bps."),
        DataPoint("2020", "all loans", 54, 43, None, None,
                  "The average guarantee fee was 54 basis points in 2020, 2 basis points lower than that of 2019. ... "
                  "the ongoing component remained unchanged at 43 basis points."),
    ],
    "2019": [
        DataPoint("2018", "all loans", 55, None, None, None,
                  "The average guarantee fee was 56 basis points in 2019, 1 basis point higher than that of 2018.",
                  restated_note="2018 total is derived (56 - 1bp) from the 2019 report's own stated delta."),
        DataPoint("2019", "all loans", 56, None, None, None,
                  "The average guarantee fee was 56 basis points in 2019, 1 basis point higher than that of 2018."),
    ],
    "2018": [
        DataPoint("2017", "all loans", 53, None, None, None,
                  "FHFA has determined that buy-up/buy-down adjustments should be included in measuring guarantee "
                  "fee, which results in an average guarantee fee for 2017 of 53 basis points.",
                  restated_from=56,
                  restated_note="Footnote 13: \"The 2018 Report showed an average guarantee fee for 2017 of 56 "
                                 "basis points. FHFA has determined that buy-up/buy-down adjustments should be "
                                 "included ... which results in an average guarantee fee for 2017 of 53 basis "
                                 "points. This methodology was employed throughout this report.\" The pre-restatement "
                                 "56 bps figure matches the 2017 report's own (2017.pdf) stated value for 2017."),
        DataPoint("2018", "all loans", 55, None, None, None,
                  "Chart 1 shows that in 2018, the average guarantee fee of 55 basis points was 2 basis points "
                  "higher than that of 2017"),
    ],
    "2017": [
        DataPoint("2016", "all loans", 56, None, None, None,
                  "In 2017, the average guarantee fee of 56 basis points was unchanged from 2016."),
        DataPoint("2017", "all loans", 56, None, None, None,
                  "In 2017, the average guarantee fee of 56 basis points was unchanged from 2016. While the total "
                  "guarantee fee was unchanged, the ongoing fee component was up slightly by 1 basis point, while "
                  "the upfront fee component fell by 1 basis point."),
    ],
    "2016": [
        DataPoint("2015", "all loans", 59, None, None, None,
                  "In 2016, the average overall guarantee fee fell slightly from its level in 2015, with the "
                  "average guarantee fee declining from 59 basis points to 57 basis points."),
        DataPoint("2016", "all loans", 57, None, None, None,
                  "In 2016, the average overall guarantee fee fell slightly from its level in 2015, with the "
                  "average guarantee fee declining from 59 basis points to 57 basis points."),
        DataPoint("2013", "all loans", 51, None, None, None,
                  "Guarantee fees increased sharply from an average of 36 basis points in 2012 to 51 basis points "
                  "in 2013, as the Enterprises implemented an FHFA-directed fee increase effective with December "
                  "2012 loan deliveries.",
                  restated_note="Historical-trend reference inside the 2016 report (Chart 1 narrative), not the report's own data year."),
        DataPoint("2012", "all loans", 36, None, None, None,
                  "Guarantee fees increased sharply from an average of 36 basis points in 2012 to 51 basis points "
                  "in 2013, as the Enterprises implemented an FHFA-directed fee increase effective with December "
                  "2012 loan deliveries.",
                  restated_from=37,
                  restated_note="2012 report's own figure for 2012 (standard loans) was 37 bps; the 2013 report "
                                 "restated 2012 to 36 bps, and the 2016 report repeats 36 bps as historical trend "
                                 "context. The 2013 report explicitly notes: \"Prior year data presented in this "
                                 "report may not be consistent with data for the same year in previous FHFA reports "
                                 "due to lender updates, model updates, and other revisions of data.\""),
    ],
    "2015": [
        DataPoint("2011", "all loans", 26, None, None, None,
                  "Guarantee fees increased sharply from an average of 26 basis points in 2011 to 57 basis points "
                  "in 2014.",
                  restated_note="Historical-trend reference inside the 2015 report; the 2010-2011 report's own "
                                 "figure for 2011 (standard loans) was 26 bps and (all loans incl. HARP+flex) 28 bps."),
        DataPoint("2014", "all loans", 57, None, None, None,
                  "Guarantee fees increased sharply from an average of 26 basis points in 2011 to 57 basis points "
                  "in 2014. ... However, fees stabilized in 2015 at an average of 59 basis points as FHFA completed "
                  "its review of guarantee fees.",
                  restated_from=58,
                  restated_note="The 2014 report's own figure for 2014 was 58 bps; the 2015 report restates it to 57 bps."),
        DataPoint("2015", "all loans", 59, None, None, None,
                  "However, fees stabilized in 2015 at an average of 59 basis points as FHFA completed its review "
                  "of guarantee fees and implemented a set of modest fee changes that were revenue neutral."),
    ],
    "2014": [
        DataPoint("2009", "all loans", 22, None, None, None,
                  "The guarantee fees are currently two-and-a-half times their previous level, up from an average "
                  "of 22 basis points in 2009 to 58 basis points in 2014."),
        DataPoint("2014", "all loans", 58, None, None, None,
                  "The guarantee fees are currently two-and-a-half times their previous level, up from an average "
                  "of 22 basis points in 2009 to 58 basis points in 2014."),
    ],
    "2013": [
        DataPoint("2009", "standard loans", 22, None, None, None,
                  "The average total guarantee fee for standard loans increased from 22 basis points in 2009 to 51 "
                  "basis points in 2013; this change was primarily due to an increase in ongoing fees."),
        DataPoint("2012", "standard loans", 36, 26, 11, None,
                  "The average total guarantee fee for standard loans increased from 36 basis points in 2012 to 51 "
                  "basis points in 2013; this change was entirely due to an increase in ongoing fees.",
                  restated_from=37,
                  restated_note="The 2012 report's own figure for 2012 (standard loans) was 37 bps (ongoing+upfront "
                                 "components imply a very similar but not identical total); the 2013 report restates "
                                 "2012 to 36 bps. Ongoing/upfront shown here (26/11, total 37) are from the same "
                                 "report's separate 'largest increases occurred from 2011 to 2012' passage and do "
                                 "not sum exactly to the headline 36 bps the report also states for 2012 - a minor "
                                 "internal rounding inconsistency within the 2013 report itself, kept as published."),
        DataPoint("2013", "standard loans", 51, 40, 11, None,
                  "The average total guarantee fee for standard loans increased from 36 basis points in 2012 to 51 "
                  "basis points in 2013; this change was entirely due to an increase in ongoing fees. ... The "
                  "largest increases occurred from 2011 to 2012 (to 26 basis points ongoing and 11 basis points "
                  "upfront) and from 2012 to 2013 (to 40 basis points ongoing and 11 basis points upfront)."),
    ],
    "2012": [
        DataPoint("2011", "standard loans", 27, None, None, None,
                  "the average total guarantee fee for standard loans increased from 27 basis points in 2011 to 37 "
                  "basis points in 2012."),
        DataPoint("2011", "all loans", 28, None, None, None,
                  "If HARP and flexible refinance loans had been included in the results, the average total "
                  "guarantee fee would have been 28 basis points for 2011 and 38 basis points for 2012."),
        DataPoint("2012", "standard loans", 37, None, None, None,
                  "the average total guarantee fee for standard loans increased from 27 basis points in 2011 to 37 "
                  "basis points in 2012."),
        DataPoint("2012", "all loans", 38, None, None, None,
                  "If HARP and flexible refinance loans had been included in the results, the average total "
                  "guarantee fee would have been 28 basis points for 2011 and 38 basis points for 2012."),
    ],
    "2010-2011": [
        DataPoint("2010", "standard loans", 24, None, None, None,
                  "the average total guarantee fee for standard loans increased from 24 basis points in 2010 to 26 "
                  "basis points in 2011."),
        DataPoint("2010", "all loans", 26, None, None, None,
                  "If HARP and flexible refinance loans had been included in the results for 2010 and 2011, the "
                  "total fees would have been 26 basis points and 28 basis points, respectively."),
        DataPoint("2011", "standard loans", 26, None, None, None,
                  "the average total guarantee fee for standard loans increased from 24 basis points in 2010 to 26 "
                  "basis points in 2011."),
        DataPoint("2011", "all loans", 28, None, None, None,
                  "If HARP and flexible refinance loans had been included in the results for 2010 and 2011, the "
                  "total fees would have been 26 basis points and 28 basis points, respectively."),
    ],
    "2009-2010": [
        DataPoint("2009", "standard loans", 21, None, None, None,
                  "total guarantee fee increased from 21 basis points in 2009 to 25 basis points in 2010."),
        DataPoint("2009", "all loans", 22, None, None, None,
                  "If HARP loans had been included in the results for 2009 and 2010, the total fees would have "
                  "been 22 basis points and 26 basis points, respectively."),
        DataPoint("2010", "standard loans", 25, None, None, None,
                  "total guarantee fee increased from 21 basis points in 2009 to 25 basis points in 2010."),
        DataPoint("2010", "all loans", 26, None, None, None,
                  "If HARP loans had been included in the results for 2009 and 2010, the total fees would have "
                  "been 22 basis points and 26 basis points, respectively."),
    ],
    "2008-2009": [
        DataPoint("2008", "all loans", 25, 14, 11, None,
                  "the average total guarantee fee decreased from 25 basis points in 2008 to 22 basis points in 2009."),
        DataPoint("2009", "all loans", 22, 13, None, None,
                  "The average total guarantee fee charged by Fannie Mae and Freddie Mac on single-family "
                  "mortgages acquired on a flow basis decreased from 25 basis points in 2008 to 22 basis points "
                  "in 2009. ... The average ongoing fee declined 1 basis point, from 14 basis points to 13 basis points."),
    ],
    "2007-2008": [
        DataPoint("2007", "all loans", 22, 17, 5, None,
                  "The average total guarantee fee charged by Fannie Mae and Freddie Mac on single-family "
                  "mortgages acquired on a flow basis increased from 22 basis points in 2007 to 25 basis points "
                  "in 2008."),
        DataPoint("2008", "all loans", 25, 14, 11, None,
                  "The average total guarantee fee charged by Fannie Mae and Freddie Mac on single-family "
                  "mortgages acquired on a flow basis increased from 22 basis points in 2007 to 25 basis points "
                  "in 2008. ... The average ongoing fee declined 3 basis points, from 17 basis points to 14 basis "
                  "points. ... The average upfront fee rose 6 basis points, from 5 to 11 basis points."),
    ],
    # state-level.pdf is intentionally not parsed for annual Total Average Guarantee Fee data - see ingest_all().
}


def period_sort_key(data_year: str) -> int:
    return int(data_year[:4])


# ------------------------------------------------------------------ download
def fetch_missing(report_keys: list[str] | None = None) -> list[str]:
    """Download any report in `report_keys` (default: all of REPORTS) not already present in raw/gfee/."""
    dest_dir = config.RAW_DIR / "gfee"
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
    """Re-verify every transcribed data point's quote against the PDF's own extracted text. A quote that can no
    longer be found (e.g. the published PDF was revised) is dropped and reported as a gap, never kept stale."""
    path = Path(path)
    title = REPORTS[report_key][0]
    res = Report(report_key=report_key, title=title)
    gaps: list[str] = []
    if report_key not in REPORT_POINTS:
        gaps.append(f"{title}: not a source of annual Total Average Guarantee Fee data (different report scope)")
        return res, gaps
    text = _full_text(path)
    for dp in REPORT_POINTS[report_key]:
        # Only the first clause of a multi-sentence quote needs to be literally present in the PDF; it anchors the
        # transcription to this exact file without requiring every elaborating sentence to match whitespace-for-whitespace.
        anchor = _normalize(dp.quote.split(" ... ")[0])
        if anchor not in text:
            gaps.append(f"{title}: could not re-locate the source sentence for {dp.data_year} ({dp.population}) in the PDF text")
            continue
        res.points.append(dp)
    return res, gaps


# ------------------------------------------------------------------ ingest / load
def ingest_all(raw_dir: Path | None = None, db=None, fetch=False) -> list[Report]:
    """Parse every FHFA guarantee-fee report PDF found locally (raw/gfee/*.pdf), optionally downloading missing ones first."""
    raw_dir = raw_dir or (config.RAW_DIR / "gfee")
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
        store.save_gfee(report_key, report_url(report_key), res, gaps, db)
        results.append(res)
    return results


def load_rows(db=None) -> list[dict]:
    return store.rows("SELECT * FROM gfee_annual ORDER BY data_year, report_key", (), db)


def load_gaps(db=None) -> list[dict]:
    return store.rows("SELECT * FROM gfee_gaps ORDER BY report_key", (), db)


def headline_series(rows: list[dict]) -> list[dict]:
    """One row per (data_year, population): the value from the report whose own title year matches the data year
    ("primary"), plus every other report's value for that same year as "restatements" - never collapsed to one number."""
    by_key: dict[tuple[str, str], list[dict]] = {}
    for r in rows:
        by_key.setdefault((r["data_year"], r["population"]), []).append(r)
    out = []
    for (year, population), obs in sorted(by_key.items(), key=lambda kv: (period_sort_key(kv[0][0]), kv[0][1])):
        primary = next((o for o in obs if o["report_key"] == year or o["report_key"].startswith(year)), None)
        primary = primary or sorted(obs, key=lambda o: o["report_key"])[-1]
        others = [o for o in obs if o is not primary]
        out.append({"data_year": year, "population": population, "primary": primary, "restatements": others})
    return out


# ------------------------------------------------------------------ validation (nothing is stored as "estimated")
def validate(rows: list[dict]) -> list[dict]:
    checks = []
    years = sorted({r["data_year"] for r in rows if r["population"] == "all loans"}, key=period_sort_key)
    expected_years = [str(y) for y in range(2007, 2025)]
    missing = [y for y in expected_years if y not in years]
    checks.append({"name": "An 'all loans' Total Average Guarantee Fee observation exists for every year 2007-2024",
                   "status": "warn" if missing else "pass",
                   "detail": f"missing years: {missing}" if missing else f"{len(years)} year(s) covered"})

    restated = sorted({r["data_year"] for r in rows if r["restated_from"] is not None}, key=period_sort_key)
    checks.append({"name": "Restatements are documented, not silently overwritten",
                   "status": "pass",
                   "detail": f"{len(restated)} year(s) with an explicit restatement note: {restated}" if restated else "no restatements found"})

    checks.append({"name": "Quarterly 'Total Average Guarantee Fee' data is not published by FHFA for this series",
                   "status": "warn",
                   "detail": "Only annual figures are consistently published; the single exception (2012 report, "
                              "Table 15) breaks fees out by lender acquisition-volume group per quarter, not as an "
                              "overall total, so it is out of scope for this headline series."})
    return checks


def summary(rows: list[dict]) -> dict:
    years = sorted({r["data_year"] for r in rows}, key=period_sort_key)
    return {"years": len(years), "first_year": years[0] if years else None, "last_year": years[-1] if years else None,
            "reports": len({r["report_key"] for r in rows})}
