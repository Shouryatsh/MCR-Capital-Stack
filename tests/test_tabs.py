"""Dashboard pages after the tab reorganisation: Benchmarks = former Overview, Overview = former Summary,
Summary = former Benchmarks (+ the GNMA Maximum Exposure to Loss section). Drives the real app.py with Streamlit's AppTest."""
import shutil
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from mcr import gnma, store
from mcr.models import ATA, CET1, Check, Observation, ParseResult

APP = str(Path(__file__).resolve().parent.parent / "app.py")
FIX = Path(__file__).parent / "fixtures"
PAGES = ["Overview", "Benchmarks", "Summary", "Data Sources", "Uploads", "Settings"]


def seed_observations():
    for prov, cet1, ata in (("Fannie Mae", 61_000, 4_552_448), ("Freddie Mac", 49_000, 3_833_729)):
        obs = {}
        for field, mm in ((CET1, cet1), (ATA, ata)):
            obs[field] = Observation(provider=prov, period="2025Q1", field=field, source_file=f"{prov}.pdf", table_name="Table",
                                     row_identifier="r", field_label=field, raw_value=str(mm), parsed_value=mm, units_detected="millions",
                                     value_mm=mm, location="p.1")
        store.save_result(ParseResult(prov, "2025Q1", obs, [Check("positive", "pass")]))


def seed_gnma(env):
    raw = env / "raw" / "ginnie"
    raw.mkdir(parents=True)
    for yy in (22, 23):
        shutil.copy(FIX / f"gnma_annual_report{yy}.pdf", raw / f"annual_report{yy}.pdf")
        gnma.ingest_report(2000 + yy, fetch=False)


@pytest.fixture()
def page(env):
    seed_observations()
    seed_gnma(env)

    def go(name):
        at = AppTest.from_file(APP, default_timeout=90).run()
        assert not at.exception
        if name != "Overview":
            at.sidebar.radio[0].set_value(name).run()
        assert not at.exception, at.exception
        return at

    return go


def labels(at, kind):
    return [w.label for w in getattr(at, kind)]


def test_navigation_lists_the_same_pages(page):
    assert page("Overview").sidebar.radio[0].options == PAGES


def test_benchmarks_page_shows_former_overview_content(page):
    at = page("Benchmarks")
    assert "Entity" in labels(at, "selectbox") and "Compare with" in labels(at, "multiselect")
    assert [s.value for s in at.subheader][1:] == ["Ratio history", "History"]
    assert at.subheader[0].value.startswith("Fannie Mae · 2025Q1")
    assert "Period" not in labels(at, "selectbox")  # nothing of the former Benchmarks/Summary content
    assert not at.header


def test_overview_page_shows_former_summary_content(page):
    at = page("Overview")
    assert labels(at, "selectbox") == ["Period"]
    assert any("benchmarks have data" in i.value and "highest CET1-based leverage ratio" in i.value for i in at.info)
    assert [b.proto.label for b in at.get("download_button")] == ["Download summary CSV"]
    assert not at.header  # the GNMA section is not duplicated here
    summary = at.dataframe[0].value
    assert {"Slot", "Benchmark", "Ratio (%)", "Rank", "Percentile", "CET1 provenance", "Failed checks"} <= set(summary.columns)
    assert len(summary) == 10


def test_summary_page_shows_former_benchmarks_content_and_gnma(page):
    at = page("Summary")
    assert labels(at, "selectbox") == ["Period"]
    assert any("benchmark slots have data" in c.value for c in at.caption)
    assert any("Rank 1 = highest ratio" in c.value for c in at.caption)
    assert [h.value for h in at.header] == ["GNMA · Maximum Exposure to Loss"]
    assert not [b for b in at.get("download_button") if b.proto.label == "Download summary CSV"]  # lives on Overview now
    assert [b.proto.label for b in at.get("download_button")] == ["Download GNMA exposure CSV"]


def test_gnma_section_values_dates_order_and_latest(page):
    at = page("Summary")
    table = next(d.value for d in at.dataframe if "Total Maximum Exposure to Loss (USD)" in d.value.columns)
    assert list(table["Fiscal year"]) == ["FY2021", "FY2022", "FY2023"]  # chronological, latest last
    assert list(table["Reporting date"]) == ["2021-09-30", "2022-09-30", "2023-09-30"]
    assert list(table["Latest"]) == ["comparative only", "", "◀ latest"]
    last, mid = table.iloc[-1], table.iloc[-2]
    assert last["Total Maximum Exposure to Loss (USD)"] == "$2,613,623,651,000"
    assert last["Total as published"] == "$2,613,623,651 (USD thousands)"
    assert (last["Outstanding MBS (USD)"], last["Outstanding MBS commitments (USD)"]) == ("$2,472,843,019,000", "$140,780,632,000")
    assert mid["Total Maximum Exposure to Loss (USD)"] == "$2,442,351,095,000"
    assert mid["Total as published"] == "$2,442,351,095 (USD thousands)"
    assert last["Page"] == "pdf p.3 · printed A-20" and last["Source report"].endswith("annual_report23.pdf")
    md = " ".join(m.value for m in at.markdown)
    assert "## $2,613,623,651" in md and "## $2,472,843,019" in md and "## $140,780,632" in md


def test_gnma_validation_panel_shows_reference_checks(page):
    at = page("Summary")
    panel = next(d.value for d in at.dataframe if list(d.value.columns) == ["Status", "Check", "Detail"])
    rows = {r["Check"]: r["Status"] for _, r in panel.iterrows()}
    assert rows["FY2023 equals the reference total $2,613,623,651 (USD thousands)"] == "✓ pass"
    assert rows["FY2022 equals the reference total $2,442,351,095 (USD thousands)"] == "✓ pass"
    assert rows["Total = Outstanding MBS + commitments (every observation)"] == "✓ pass"
    assert not at.error


def test_gnma_does_not_touch_other_entities(page):
    at = page("Benchmarks")
    assert at.selectbox[0].options == ["Fannie Mae", "Freddie Mac"]  # no GNMA entity among the CET1 providers
    assert store.rows("SELECT COUNT(*) AS n FROM observations")[0]["n"] == 4


def test_summary_without_cet1_data_still_shows_gnma(env):
    seed_gnma(env)
    at = AppTest.from_file(APP, default_timeout=90).run()
    at.sidebar.radio[0].set_value("Summary").run()
    assert not at.exception and any("No data yet" in w.value for w in at.warning)
    assert [h.value for h in at.header] == ["GNMA · Maximum Exposure to Loss"]


def test_summary_without_gnma_data_prompts_to_fetch(env):
    seed_observations()
    at = AppTest.from_file(APP, default_timeout=90).run()
    at.sidebar.radio[0].set_value("Summary").run()
    assert not at.exception and any("No GNMA data yet" in i.value for i in at.info)


def test_data_sources_has_gnma_fetch_button(page):
    at = page("Data Sources")
    assert "Fetch GNMA annual reports" in [b.label for b in at.button]
