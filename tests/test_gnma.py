"""GNMA Maximum Exposure to Loss: extraction, exact arithmetic, validation, reconciliation, storage, formatting.

Fixtures in tests/fixtures/gnma_annual_reportYY.pdf are the relevant pages copied unchanged from the official English
annual reports (https://www.ginniemae.gov/about_us/what_we_do/Annual_Reports/annual_reportYY.pdf), one per layout variant.
"""
import shutil
from dataclasses import replace
from pathlib import Path

import pytest

from mcr import gnma, store

FIX = Path(__file__).parent / "fixtures"


def fx(yy: int) -> Path:
    return FIX / f"gnma_annual_report{yy:02d}.pdf"


def extract(yy: int, fy: int):
    return gnma.extract_report(fx(yy), fy, gnma.report_url(fy))


def by_year(res, role="current"):
    return next(f for f in res.figures if f.role == role)


def check(checks, starts):
    return next(c for c in checks if c["name"].startswith(starts))


# ------------------------------------------------------------------ the 2023 reference report (page A-20)
def test_fy2023_matches_reference_values_exactly():
    r = extract(23, 2023)
    cur, prior = by_year(r), by_year(r, "comparative")
    # the report prints USD thousands; dashboard values are exact integer dollars
    assert (cur.mbs_usd, cur.commitments_usd, cur.total_usd) == (2_472_843_019_000, 140_780_632_000, 2_613_623_651_000)
    assert (prior.mbs_usd, prior.commitments_usd, prior.total_usd) == (2_284_456_605_000, 157_894_490_000, 2_442_351_095_000)
    assert cur.as_published_total() == "$2,613,623,651 (USD thousands)"
    assert prior.as_published_total() == "$2,442,351,095 (USD thousands)"
    assert cur.total_usd == cur.mbs_usd + cur.commitments_usd == cur.reported_total_usd
    assert (cur.fiscal_year, cur.reporting_date, prior.fiscal_year, prior.reporting_date) == (2023, "2023-09-30", 2022, "2022-09-30")
    assert cur.units == "thousands" and cur.mbs_raw == "2,472,843,019" and cur.total_raw == "2,613,623,651"


def test_fy2023_traceability():
    cur = by_year(extract(23, 2023))
    assert cur.source_report == "gnma_annual_report23.pdf"
    assert cur.source_url.endswith("/Annual_Reports/annual_report23.pdf")
    assert cur.printed_page == "A-20"  # "Notes to the Financial Statements, page A-20"
    assert cur.pdf_page == 3  # position inside the page-subset fixture
    assert cur.note.startswith("Note 2: Summary of Significant Accounting Policies")
    assert cur.table_kind == "maximum_exposure_to_loss" and cur.table_title == "Maximum exposure to loss"
    assert cur.ok and not [f for f in cur.flags if f.startswith(("FAIL", "WARN"))]


def test_rounded_billions_table_in_same_report_is_cross_checked_not_confused():
    # Note 4 repeats the figures rounded to $ billions (2,473 / 141 / 2,614); the exact $ thousands table must win
    cur = by_year(extract(23, 2023))
    assert cur.mbs_usd == 2_472_843_019_000 and cur.precision_usd == 1_000 and cur.ok


def test_fy2022_report_and_comparative():
    r = extract(22, 2022)
    cur, prior = by_year(r), by_year(r, "comparative")
    assert cur.total_usd == 2_442_351_095_000 and cur.as_published_total() == "$2,442,351,095 (USD thousands)"
    assert (prior.fiscal_year, prior.total_usd) == (2021, 2_426_614_893_000)


# ------------------------------------------------------------------ layout / terminology variants
def test_overprinted_glyph_fragments_and_header_on_previous_page():
    # FY2020: duplicate 'MBS securities' glyphs and stray fragments ('9,399', ',731', '6,130'); unit + header on the page before
    f = by_year(extract(20, 2020))
    assert (f.mbs_usd, f.commitments_usd, f.total_usd) == (2_117_699_399_000, 234_376_731_000, 2_352_076_130_000)
    assert f.units == "thousands" and f.ok


def test_single_column_report_with_header():
    f = by_year(extract(19, 2019))
    assert (f.fiscal_year, f.total_usd) == (2019, 2_208_609_755_000)
    assert not any(gnma.YEAR_ASSUMED in x for x in f.flags)


def test_unreadable_year_header_is_flagged_and_needs_confirmation(tmp_path):
    # The original FY2024 PDF loses its "2024" column header in the text layer; reproduce that by redacting it from the fixture
    import pymupdf
    doc = pymupdf.open(fx(24))
    page = doc[1]
    for rect in page.search_for("2024", clip=pymupdf.Rect(0, 130, 700, 160)):
        page.add_redact_annot(rect)
    page.apply_redactions()
    broken = tmp_path / "annual_report24.pdf"
    doc.save(broken)
    r24 = gnma.extract_report(broken, 2024, gnma.report_url(2024))
    cur, prior = by_year(r24), by_year(r24, "comparative")
    assert (cur.fiscal_year, cur.total_usd) == (2024, 2_788_416_965_000)
    assert (prior.fiscal_year, prior.total_usd) == (2023, 2_613_623_651_000)
    assert all(any(gnma.YEAR_ASSUMED in x for x in f.flags) for f in (cur, prior))
    alone = check(gnma.validate(r24.figures), "Columns with an unreadable year header")
    assert alone["status"] == "fail"  # nothing else confirms the assumed mapping
    both = check(gnma.validate(r24.figures + extract(23, 2023).figures), "Columns with an unreadable year header")
    # the FY2023 column is confirmed by FY2023's own report; the FY2024 column awaits the FY2025 report
    assert both["status"] == "fail" and "(2024," in both["detail"] and "(2023," not in both["detail"]


def test_billions_era_without_total_row_or_maximum_exposure_heading():
    r = extract(14, 2014)
    cur, prior = by_year(r), by_year(r, "comparative")
    assert (cur.mbs_raw, cur.commitments_raw, cur.units) == ("1,526.5", "97.8", "billions")
    assert cur.mbs_usd == 1_526_500_000_000 and cur.commitments_usd == 97_800_000_000
    assert cur.total_usd == 1_624_300_000_000 and cur.reported_total_usd is None and cur.total_raw == ""
    assert cur.as_published_total() == "$1,624.3 (USD billions)" and cur.precision_usd == 100_000_000
    assert cur.table_kind == "off_balance_sheet_table"
    assert any(x.startswith("INFO") and "no total row" in x for x in cur.flags)
    assert (prior.fiscal_year, prior.total_usd) == (2013, 1_575_200_000_000)


def test_landscape_two_column_page_does_not_mix_in_prose_numbers():
    r = extract(16, 2016)
    cur, prior = by_year(r), by_year(r, "comparative")
    assert (cur.mbs_usd, cur.commitments_usd, cur.total_usd) == (1_728_000_000_000, 96_000_000_000, 1_824_000_000_000)
    assert (prior.fiscal_year, prior.mbs_usd, prior.commitments_usd) == (2015, 1_609_000_000_000, 160_000_000_000)
    assert cur.note.startswith("Note 6: Financial Guarantees")


# ------------------------------------------------------------------ gaps are documented, never estimated
def test_table_without_text_layer_is_reported_as_gap():
    r = extract(99, 1999)
    assert r.figures == [] and any("not machine-readable" in g for g in r.gaps)


def test_report_without_the_table_is_reported_as_gap():
    r = extract(11, 2011)
    assert r.figures == [] and any("no 'Outstanding MBS'" in g for g in r.gaps)


# ------------------------------------------------------------------ reconciliation of comparatives
def test_reconcile_matching_comparatives():
    figs = extract(23, 2023).figures + extract(22, 2022).figures
    rec = [r for r in gnma.reconcile(figs) if r["fiscal_year"] == 2022]
    assert {r["component"] for r in rec} == {"Outstanding MBS", "Outstanding MBS commitments", "Total"}
    assert all(r["status"] == "match" and r["difference_usd"] == 0 for r in rec)


def test_reconcile_flags_restated_commitments_and_rounding():
    figs = extract(15, 2015).figures + extract(16, 2016).figures + extract(14, 2014).figures
    rec = {(r["fiscal_year"], r["component"]): r for r in gnma.reconcile(figs)}
    restated = rec[(2015, "Outstanding MBS commitments")]
    assert restated["status"] == "MISMATCH" and restated["difference_usd"] == -31_000_000_000  # $129bn vs restated $160bn
    assert rec[(2015, "Outstanding MBS")]["status"] == "match"
    assert rec[(2014, "Outstanding MBS")]["status"] == "match within rounding"  # 1,526.5 vs 1,527
    warn = check(gnma.validate(figs), "Comparative figures in successive reports reconcile")
    assert warn["status"] == "warn" and "FY2015" in warn["detail"]


# ------------------------------------------------------------------ validation rules
def test_validation_passes_for_reference_years():
    figs = extract(23, 2023).figures + extract(22, 2022).figures
    checks = gnma.validate(figs)
    assert check(checks, "Total = Outstanding MBS")["status"] == "pass"
    assert check(checks, "FY2023 equals the reference")["status"] == "pass"
    assert check(checks, "FY2022 equals the reference")["status"] == "pass"
    assert check(checks, "No extraction failures")["status"] == "pass"


def test_validation_detects_wrong_total_and_wrong_reference():
    good = extract(23, 2023).figures
    bad_total = [replace(f, total_usd=f.total_usd + 1_000) if f.role == "current" else f for f in good]
    assert check(gnma.validate(bad_total), "Total = Outstanding MBS")["status"] == "fail"
    assert check(gnma.validate(bad_total), "Printed total equals")["status"] == "fail"
    off_by_one_thousand = [replace(f, mbs_usd=f.mbs_usd + 1_000, total_usd=f.total_usd + 1_000, reported_total_usd=f.reported_total_usd + 1_000)
                           if f.role == "current" else f for f in good]
    assert check(gnma.validate(off_by_one_thousand), "FY2023 equals the reference")["status"] == "fail"
    assert check(gnma.validate(good[:1]), "FY2022 equals the reference")["status"] == "fail"  # missing year is flagged, not skipped


def test_inconsistent_printed_total_is_a_failure(monkeypatch):
    real = gnma._figures

    def tampered(t, *a):
        t.total = [(str(int(v.replace(",", "")) + 1), x) for v, x in t.total] if t.total else t.total
        return real(t, *a)

    monkeypatch.setattr(gnma, "_figures", tampered)
    r = extract(23, 2023)
    assert not by_year(r).ok and any("printed total" in g for g in r.gaps)
    assert gnma.headline_series(r.figures) == []  # a failed observation never reaches the dashboard series


# ------------------------------------------------------------------ exact numeric handling and formatting
def test_decimal_arithmetic_is_exact():
    assert gnma.to_usd("1,341.4", "billions") == 1_341_400_000_000
    assert gnma.to_usd("2,472,843,019", "thousands") == 2_472_843_019_000
    assert gnma.to_usd("0.1", "billions") + gnma.to_usd("0.2", "billions") == gnma.to_usd("0.3", "billions")  # 0.1+0.2 != 0.3 in floats
    with pytest.raises(ValueError):
        gnma.to_usd("1.0000000001", "billions")  # not a whole number of dollars: refuse rather than round


def test_usd_formatting_has_thousands_separators_and_no_rounding():
    assert gnma.fmt_usd(2_613_623_651_000) == "$2,613,623,651,000"
    assert gnma.fmt_usd(2_613_623_651_001) == "$2,613,623,651,001"
    assert gnma.fmt_usd(None) == "—"
    f = by_year(extract(14, 2014))
    assert f.published(f.mbs_usd) == "$1,526.5" and f.published(f.commitments_usd) == "$97.8"


# ------------------------------------------------------------------ storage, series, isolation
@pytest.fixture()
def loaded(env):
    (config_raw := env / "raw" / "ginnie").mkdir(parents=True)
    for yy in (22, 23):
        shutil.copy(fx(yy), config_raw / f"annual_report{yy}.pdf")
    return [gnma.ingest_report(fy, fetch=False) for fy in (2022, 2023)]


def test_store_round_trip_keeps_exact_integers(loaded):
    figs = gnma.load_figures()
    cur = next(f for f in figs if f.fiscal_year == 2023 and f.role == "current")
    assert isinstance(cur.total_usd, int) and cur.total_usd == 2_613_623_651_000
    assert (cur.source_report, cur.printed_page, cur.reporting_date) == ("annual_report23.pdf", "A-20", "2023-09-30")
    assert [d["type"] for d in store.rows("SELECT typeof(total_usd) AS type FROM gnma_exposure LIMIT 1")] == ["text"]  # never a float


def test_headline_series_is_chronological_with_latest_last(loaded):
    series = gnma.headline_series(gnma.load_figures())
    assert [f.fiscal_year for f in series] == [2021, 2022, 2023]
    assert series[-1].total_usd == 2_613_623_651_000
    # FY2022 uses its own report, not the FY2023 comparative; FY2021 only exists as a comparative and is labelled so
    assert series[1].source_report == "annual_report22.pdf" and series[1].role == "current"
    assert series[0].role == "comparative" and any("comparative figure from a later report" in x for x in series[0].flags)


def test_reingest_replaces_instead_of_duplicating(loaded):
    gnma.ingest_report(2023, fetch=False)
    assert store.rows("SELECT COUNT(*) AS n FROM gnma_exposure WHERE source_report='annual_report23.pdf'")[0]["n"] == 2


def test_gnma_data_never_mixes_with_other_entities(loaded):
    assert store.get_observations() == [] and store.rows("SELECT DISTINCT provider FROM observations") == []
    assert [s for s in store.rows("SELECT * FROM checks")] == []


def test_missing_and_unpublished_reports_are_recorded_as_gaps(env, monkeypatch):
    r = gnma.ingest_report(2024, fetch=False)
    assert r.figures == [] and "not in raw/ginnie" in r.gaps[0]

    class Html:
        content, headers = b"<html></html>", {"Content-Type": "text/html"}

        def raise_for_status(self):
            pass

    monkeypatch.setattr(gnma.requests, "get", lambda *a, **k: Html())
    r = gnma.ingest_report(2026, fetch=True)
    assert r.figures == [] and "not a PDF" in r.gaps[0]
    assert {g["fiscal_year"] for g in gnma.load_gaps()} == {2024, 2026}


def test_default_range_stops_at_last_completed_fiscal_year():
    from datetime import date
    assert gnma.current_fiscal_year(date(2026, 10, 13)) == 2027 and gnma.current_fiscal_year(date(2026, 9, 30)) == 2026
