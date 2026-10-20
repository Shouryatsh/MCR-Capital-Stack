"""FDIC Deposit Insurance Fund annual figures: data integrity of the hand-transcribed REPORT_POINTS dataset, quote
re-verification against the real source PDFs, and the ingest/validation pipeline.

Uses the real downloaded report PDFs in raw/fdic/ when present (the full 2006-2024 corpus); when they are not
present (e.g. a clean checkout without the large PDFs) the quote-verification tests are skipped, while the pure
data model tests (which don't need the PDFs) still run.
"""
from pathlib import Path

import pytest

from mcr import config, fdic

RAW = Path(__file__).resolve().parent.parent / "raw" / "fdic"
HAVE_PDFS = all((RAW / fdic.report_filename(k)).exists() for k in fdic.REPORTS)


def test_report_points_cover_every_year_2006_2024():
    assert set(fdic.REPORT_POINTS) == {str(y) for y in range(2006, 2025)}
    assert set(fdic.REPORTS) == {str(y) for y in range(2006, 2025)}


def test_every_data_point_has_a_quote_for_every_populated_value():
    for key, dp in fdic.REPORT_POINTS.items():
        assert dp.report_key == key
        if dp.fund_balance_ending is not None:
            assert dp.fund_balance_quote
        if dp.min_reserve_ratio_pct is not None:
            assert dp.min_reserve_ratio_quote
        if dp.insured_deposits_trillions is not None:
            assert dp.insured_deposits_quote


def test_minimum_reserve_ratio_matches_the_statutory_floor_not_the_discretionary_drr():
    for key, dp in fdic.REPORT_POINTS.items():
        year = int(key)
        expected = 1.15 if year <= 2009 else 1.35
        assert dp.min_reserve_ratio_pct == expected, key


def test_fund_balance_chain_has_zero_actual_restatements_2006_2024():
    by_year = {k: dp for k, dp in fdic.REPORT_POINTS.items()}
    for year in range(2007, 2025):
        key, prev_key = str(year), str(year - 1)
        assert by_year[key].fund_balance_prior == by_year[prev_key].fund_balance_ending, key


def test_report_url_uses_direct_fdic_gov_for_recent_years_and_archive_for_older_ones():
    assert fdic.report_url("2024") == "https://www.fdic.gov/financial-reports/2024-annual-report-section4.pdf"
    assert fdic.report_url("2006") == "https://archive.fdic.gov/view/fdic/635/fdic_635_DS1.pdf"


@pytest.mark.skipif(not HAVE_PDFS, reason="requires the downloaded raw/fdic/*.pdf report corpus")
def test_every_transcribed_quote_is_still_present_in_its_source_pdf():
    gaps = []
    for key in fdic.REPORT_POINTS:
        _, g = fdic.extract_report(RAW / fdic.report_filename(key), key)
        gaps.extend(g)
    assert gaps == []


@pytest.mark.skipif(not HAVE_PDFS, reason="requires the downloaded raw/fdic/*.pdf report corpus")
def test_ingest_all_persists_every_year_with_no_gaps(env):
    for f in RAW.glob("*.pdf"):
        dest = config.RAW_DIR / "fdic" / f.name
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(f.read_bytes())
    fdic.ingest_all()
    rows = fdic.load_rows()
    gaps = fdic.load_gaps()
    assert len(rows) == len(fdic.REPORT_POINTS)
    assert gaps == []

    s = fdic.summary(rows)
    assert s == {"years": 19, "first_year": "2006", "last_year": "2024", "reports": 19}

    checks = {c["name"]: c for c in fdic.validate(rows)}
    assert checks["Fund Balance - Ending, Minimum Reserve Ratio and Estimated Insured Deposits exist for every year 2006-2024"]["status"] == "pass"
    assert checks["Fund Balance - Ending chains: each year's reported prior-year figure matches the previous year's own reported ending figure"]["status"] == "pass"
    assert checks["Minimum Reserve Ratio matches the statutory floor (1.15% for 2006-2009, 1.35% for 2010-2024)"]["status"] == "pass"
    assert checks["Estimated Insured Deposits carries an explicit 'as of' date for every year (not always December 31)"]["status"] == "pass"
