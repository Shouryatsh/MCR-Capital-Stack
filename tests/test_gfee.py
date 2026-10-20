"""FHFA Single-Family Guarantee Fees (Total Average Guarantee Fee): data integrity of the hand-transcribed
REPORT_POINTS dataset, quote re-verification against the real source PDFs, and the headline/validation pipeline.

Uses the real downloaded report PDFs in raw/gfee/ when present (the full annual corpus 2007-2024); when they are not
present (e.g. a clean checkout without the large PDFs) the quote-verification tests are skipped, while the pure data
model tests (which don't need the PDFs) still run.
"""
from pathlib import Path

import pytest

from mcr import config, gfee, store

RAW = Path(__file__).resolve().parent.parent / "raw" / "gfee"
HAVE_PDFS = all((RAW / gfee.report_filename(k)).exists() for k in gfee.REPORTS)


def test_report_points_cover_every_year_2007_2024_with_all_loans_population():
    years = {dp.data_year for pts in gfee.REPORT_POINTS.values() for dp in pts if dp.population == "all loans"}
    assert years == {str(y) for y in range(2007, 2025)}


def test_state_level_report_is_metadata_only_not_a_data_source():
    assert "state-level" in gfee.REPORTS
    assert "state-level" not in gfee.REPORT_POINTS


def test_restatements_are_tagged_not_silently_overwritten():
    restated = [(key, dp.data_year, dp.restated_from, dp.total_bps)
                for key, pts in gfee.REPORT_POINTS.items() for dp in pts if dp.restated_from is not None]
    assert ("2018", "2017", 56, 53) in restated  # buy-up/buy-down methodology change, explicit footnote 13
    assert ("2013", "2012", 37, 36) in restated
    # every restated point must carry an explanatory note - never a bare number change
    assert all(dp.restated_note for pts in gfee.REPORT_POINTS.values() for dp in pts if dp.restated_from is not None)


def test_report_url_uses_the_recovered_fhfa_document_slugs():
    assert gfee.report_url("2024") == "https://www.fhfa.gov/document/d/sfgf/fannie-mae-and-freddie-mac-single-family-guarantee-fees-in-2024"
    assert gfee.report_url("2007-2008") == "https://www.fhfa.gov/document/d/sfgf/fannie-and-freddie-guarantee-fees-in-2007-and-2008"


@pytest.mark.skipif(not HAVE_PDFS, reason="requires the downloaded raw/gfee/*.pdf report corpus")
def test_every_transcribed_quote_is_still_present_in_its_source_pdf():
    gaps = []
    for key in gfee.REPORT_POINTS:
        _, g = gfee.extract_report(RAW / gfee.report_filename(key), key)
        gaps.extend(g)
    assert gaps == []


@pytest.mark.skipif(not HAVE_PDFS, reason="requires the downloaded raw/gfee/*.pdf report corpus")
def test_ingest_all_persists_every_point_and_flags_only_the_known_state_level_gap(env):
    for f in RAW.glob("*.pdf"):
        dest = config.RAW_DIR / "gfee" / f.name
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(f.read_bytes())
    gfee.ingest_all()
    rows = gfee.load_rows()
    gaps = gfee.load_gaps()
    assert len(rows) == sum(len(pts) for pts in gfee.REPORT_POINTS.values())
    assert [g["report_key"] for g in gaps] == ["state-level"]

    s = gfee.summary(rows)
    assert s == {"years": 18, "first_year": "2007", "last_year": "2024", "reports": 17}

    series = gfee.headline_series(rows)
    y2024 = next(s for s in series if s["data_year"] == "2024" and s["population"] == "all loans")
    assert y2024["primary"]["total_bps"] == 65.2 and y2024["restatements"] == []
    y2021 = next(s for s in series if s["data_year"] == "2021" and s["population"] == "all loans")
    assert y2021["primary"]["total_bps"] == 56.0
    assert any(r["total_bps"] == 57.0 and r["restated_from"] == 56.0 for r in y2021["restatements"])

    checks = {c["name"]: c for c in gfee.validate(rows)}
    assert checks["An 'all loans' Total Average Guarantee Fee observation exists for every year 2007-2024"]["status"] == "pass"
    assert checks["Restatements are documented, not silently overwritten"]["status"] == "pass"
    assert checks["Quarterly 'Total Average Guarantee Fee' data is not published by FHFA for this series"]["status"] == "warn"
