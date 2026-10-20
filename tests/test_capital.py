"""Minimum capital ratio, total RWA and credit RWA from the Fannie Mae / Freddie Mac disclosures, and the Source values payload."""
import pymupdf
import pytest
from fastapi.testclient import TestClient

from mcr import api, capital, pdf_extract, source_values as sv, store
from mcr.ingest import ingest_file

FIX = __import__("pathlib").Path(__file__).parent / "fixtures"
_LINES: dict[str, list] = {}


@pytest.fixture(autouse=True)
def cached_pdf_lines(monkeypatch):
    """Parsing a PDF with pdfplumber is slow; parse each fixture once per session. The extractor itself is untouched."""
    real = capital.read_lines

    def cached(path):
        if str(path) not in _LINES:
            _LINES[str(path)] = real(path)
        return _LINES[str(path)]

    monkeypatch.setattr(capital, "read_lines", cached)
    monkeypatch.setattr(pdf_extract, "read_lines", cached)  # the CET1 / assets parse used by normal ingest


def page_text(pdf, page):
    return pymupdf.open(pdf)[page - 1].get_text()


# ------------------------------------------------------------------ Fannie Mae, December 2023 (the verification period)
def test_fannie_dec_2023_matches_the_verification_values(fannie_pdf, env):
    r = capital.extract(fannie_pdf, "Fannie Mae")
    m = r.metrics
    assert r.period == "2023Q4"
    assert (m["min_capital_ratio"].value, m["total_rwa"].value, m["credit_rwa"].value) == ("4.5", "1357097", "1240896")
    assert (m["min_capital_ratio"].unit, m["total_rwa"].unit, m["credit_rwa"].unit) == ("percent", "USD millions", "USD millions")
    assert r.ok and [c.status for c in r.checks] == ["pass"] * 3


def test_fannie_uses_the_unrounded_millions_table_not_the_rounded_billions_one(fannie_pdf, env):
    m = capital.extract(fannie_pdf, "Fannie Mae").metrics
    assert m["total_rwa"].value != "1357000" and m["total_rwa"].raw_value == "1,357,097"  # Exhibit 2.2 shows 1,357 ($ billions)
    assert "Exhibit 2.1" in m["total_rwa"].table_name and "RWA Summary" in m["total_rwa"].table_name
    assert m["total_rwa"].units_detected == "millions" and m["total_rwa"].location == "p.10"
    # the ratio is the CET1 row's Minimum Capital Ratio Requirement, not the 6.0 / 8.0 / 2.5 of other rows or the 10.3 incl. buffers
    assert m["min_capital_ratio"].column_name == "Minimum Capital Ratio Requirement" and m["min_capital_ratio"].raw_value == "4.5"
    assert "Exhibit 2.2" in m["min_capital_ratio"].table_name


def test_fannie_values_are_on_the_printed_page(fannie_pdf):
    text = page_text(fannie_pdf, 10)  # independent of the extractor: plain page text
    for printed in ("1,357,097", "1,240,896", "30,843", "85,358"):
        assert printed in text
    assert 1_240_896 + 30_843 + 85_358 == 1_357_097  # credit + market + operational = total


# ------------------------------------------------------------------ Freddie Mac
def test_freddie_1q25_values_and_provenance(freddie_pdf, env):
    r = capital.extract(freddie_pdf, "Freddie Mac")
    m = r.metrics
    assert r.period == "2025Q1" and r.ok
    assert (m["min_capital_ratio"].value, m["total_rwa"].value, m["credit_rwa"].value) == ("4.5", "1098727", "969014")
    assert "Table 2.1" in m["total_rwa"].table_name and m["total_rwa"].line_item == "Risk-weighted Assets (Standardized Approach)"
    assert "Table 2.2" in m["min_capital_ratio"].table_name and m["min_capital_ratio"].column_name == "Minimum Capital Requirement"


def test_freddie_values_are_on_the_printed_pages(freddie_pdf):
    doc = pymupdf.open(freddie_pdf)
    text = " ".join(p.get_text() for p in doc)
    for printed in ("1,098,727", "969,014"):
        assert printed in text
    assert "4.5" in text


def test_freddie_ratio_is_the_ratio_row_not_the_amount_row(freddie_pdf, env):
    # Table 2.2 lists CET1 twice: amounts ($45 ...) and ratios (4.5 ...). The amounts row must not be mistaken for the ratio.
    m = capital.extract(freddie_pdf, "Freddie Mac").metrics
    assert m["min_capital_ratio"].value == "4.5"
    assert m["min_capital_ratio"].value not in ("49", "49.0")  # the 1Q25 CET1 minimum requirement amount in $ billions


# ------------------------------------------------------------------ flagged, never silent
def test_unreadable_value_is_flagged_and_not_stored(fannie_pdf, tmp_path, env):
    bad = tmp_path / "2023Q4.pdf"
    doc = pymupdf.open(fannie_pdf)
    page = doc[9]
    for r in page.search_for("Credit risk"):
        page.add_redact_annot(r)
    page.apply_redactions()
    doc.save(bad)
    r = capital.extract(bad, "Fannie Mae")
    assert "credit_rwa" not in r.metrics and "total_rwa" in r.metrics
    assert not r.ok and any(c.name == "credit_rwa_readable" and c.status == "fail" for c in r.checks)


def test_inconsistent_components_fail_the_sum_check(fannie_pdf, monkeypatch, env):
    real = capital.lookup

    def tampered(lines, spec, src, name, period):
        out = real(lines, spec, src, name, period)
        return ("1,240,897",) + out[1:] if name == capital.CREDIT_RWA else out

    monkeypatch.setattr(capital, "lookup", tampered)
    r = capital.extract(fannie_pdf, "Fannie Mae")
    sums = next(c for c in r.checks if c.name == "rwa_components_sum_to_total")
    assert sums.status == "fail" and "1,357,098" in sums.detail and not r.ok


def test_credit_rwa_above_total_fails(fannie_pdf, monkeypatch, env):
    real = capital.lookup
    monkeypatch.setattr(capital, "lookup", lambda l, s, src, n, p: ("9,999,999",) + real(l, s, src, n, p)[1:] if n == capital.CREDIT_RWA else real(l, s, src, n, p))
    assert next(c for c in capital.extract(fannie_pdf, "Fannie Mae").checks if c.name == "credit_rwa_within_total").status == "fail"


def test_wrong_minimum_ratio_fails_the_cet1_cross_check(fannie_pdf, monkeypatch, env):
    real = capital.lookup
    monkeypatch.setattr(capital, "lookup", lambda l, s, src, n, p: ("6.0",) + real(l, s, src, n, p)[1:] if n == capital.MIN_RATIO else real(l, s, src, n, p))
    c = next(c for c in capital.extract(fannie_pdf, "Fannie Mae").checks if c.name == "min_ratio_matches_cet1_requirement")
    assert c.status == "fail"  # 6.0% x RWA is far from the published $61bn CET1 minimum


# ------------------------------------------------------------------ storage and ingest
def test_store_round_trip_is_exact_text_and_replaces(fannie_pdf, env):
    capital.ingest(fannie_pdf, "Fannie Mae")
    capital.ingest(fannie_pdf, "Fannie Mae")  # re-ingest must not duplicate
    rows = store.rows("SELECT field, value, unit, typeof(value) AS t FROM capital_metrics ORDER BY field")
    assert [(r["field"], r["value"], r["unit"], r["t"]) for r in rows] == [
        ("credit_rwa", "1240896", "USD millions", "text"), ("min_capital_ratio", "4.5", "percent", "text"), ("total_rwa", "1357097", "USD millions", "text")]
    assert store.rows("SELECT COUNT(*) AS n FROM capital_checks")[0]["n"] == 3
    loaded = capital.load("Fannie Mae")
    assert [p["period"] for p in loaded] == ["2023Q4"] and loaded[0]["metrics"]["total_rwa"]["source_file"] == "fannie_2023Q4.pdf"


def test_normal_ingest_also_stores_the_capital_metrics(fannie_pdf, env):
    out = ingest_file(fannie_pdf, "Fannie Mae")
    assert out.status == "ok" and out.provider == "Fannie Mae"
    assert {r["field"] for r in store.rows("SELECT field FROM capital_metrics")} == {"min_capital_ratio", "total_rwa", "credit_rwa"}
    assert len(store.get_observations()) == 2  # CET1 and adjusted total assets are unchanged and separate


def test_gse_only_pdf_providers_get_capital_specs():
    assert set(capital.SPECS) == {"Fannie Mae", "Freddie Mac"}


# ------------------------------------------------------------------ Source values payload
@pytest.fixture()
def loaded(env, fannie_pdf, freddie_pdf):
    ingest_file(fannie_pdf)
    ingest_file(freddie_pdf)
    return env


def test_payload_for_fannie_has_all_five_values_with_provenance(loaded):
    p = sv.build_entity("fannie-mae")
    assert [m["field"] for m in p["metrics"]] == ["CET1_amount", "Adjusted_total_assets", "min_capital_ratio", "total_rwa", "credit_rwa"]
    row = p["periods"][0]
    assert (row["period"], row["label"], row["period_end"]) == ("2023Q4", "December 2023", "2023-12-31")
    v = row["values"]
    assert (v["min_capital_ratio"]["text"], v["total_rwa"]["text"], v["credit_rwa"]["text"]) == ("4.5%", "1,357,097", "1,240,896")
    assert (v["CET1_amount"]["text"], v["Adjusted_total_assets"]["text"]) == ("61,000", "4,552,448")
    assert v["total_rwa"]["source_file"] == "fannie_2023Q4.pdf" and v["total_rwa"]["location"] == "p.10"


def test_payload_verifies_against_the_supplied_reference(loaded):
    p = sv.build_entity("fannie-mae")
    assert p["reference"]["matches"] is True and p["reference"]["label"] == "December 2023"
    status = {c["name"][:40]: c["status"] for c in p["validation"]}
    assert all(s == "pass" for s in status.values())
    f = sv.build_entity("freddie-mac")
    assert f["reference"] is None and any(c["name"] == "Independent verification values" and c["status"] == "warn" for c in f["validation"])


def test_payload_flags_a_reference_mismatch(loaded):
    store.rows("SELECT 1")  # ensure schema
    with store.conn() as c:
        c.execute("UPDATE capital_metrics SET value='1357098' WHERE provider='Fannie Mae' AND field='total_rwa'")
    p = sv.build_entity("fannie-mae")
    assert p["reference"]["matches"] is False
    assert any(c["status"] == "fail" and "matches the verification values" in c["name"] for c in p["validation"])


def test_entities_are_ordered_and_empty_ones_are_honest(loaded):
    idx = sv.build_index()
    assert [e["name"] for e in idx] == ["Fannie Mae", "GNMA", "Freddie Mac", "FHLBs", "GSE GFEE", "FDIC"]
    status = {e["key"]: e["status"] for e in idx}
    assert status == {"fannie-mae": "data", "gnma": "empty", "freddie-mac": "data", "fhlbs": "empty", "gse-gfee": "empty", "fdic": "empty"}
    fhlb = sv.build_entity("fhlbs")
    assert fhlb["periods"] == [] and fhlb["metrics"] == [] and sv.build_entity("nope") is None


def test_period_info_and_formatting():
    assert sv.period_info("2025Q3") == ("September 2025", "2025-09-30") and sv.period_info("2024Q1") == ("March 2024", "2024-03-31")
    assert sv.fmt_value("4.5", "percent") == "4.5%" and sv.fmt_value("1357097", "USD millions") == "1,357,097"
    assert sv.fmt_value("4.50", "percent") == "4.5%" and sv.fmt_value("1000", "USD millions") == "1,000"


def test_entity_list_is_configurable(env):
    import json
    (env / "config").mkdir(exist_ok=True)
    (env / "config" / "source_entities.json").write_text(json.dumps([{"key": "x", "name": "Other", "kind": "placeholder"}]))
    assert [e["name"] for e in sv.build_index()] == ["Other"]


# ------------------------------------------------------------------ API
def test_api_source_values(loaded):
    c = TestClient(api.create_app(dist=loaded / "nodist"))
    idx = c.get("/api/source-values").json()["entities"]
    assert [e["name"] for e in idx] == ["Fannie Mae", "GNMA", "Freddie Mac", "FHLBs", "GSE GFEE", "FDIC"]
    f = c.get("/api/source-values/fannie-mae").json()
    assert f["periods"][0]["values"]["total_rwa"]["text"] == "1,357,097" and f["reference"]["matches"] is True
    assert c.get("/api/source-values/fdic").json()["periods"] == []
    assert c.get("/api/source-values/nope").status_code == 404
