import fitz  # PyMuPDF: only used to build the "label removed" fixtures
import pytest

from mcr.mappings import load_mappings
from mcr.models import ATA, CET1, FieldNotFoundError
from mcr.pdf_extract import detect_pdf_provider, infer_period, parse_pdf


def parse(path, env):
    m = load_mappings()
    prov = detect_pdf_provider(str(path), m)
    return parse_pdf(str(path), prov, m[prov])


def test_fannie_values_and_provenance(env, fannie_pdf):
    r = parse(fannie_pdf, env)
    assert (r.provider, r.period) == ("Fannie Mae", "2023Q4")
    c, a = r.observations[CET1], r.observations[ATA]
    assert c.value_mm == 61_000 and c.raw_value == "61" and c.units_detected == "billions"
    assert c.value_mm not in (-74_000, -73_965)  # never Available Capital (Deficit) or Exhibit 1.1
    assert a.value_mm == 4_552_448 and a.units_detected == "millions"
    assert "Exhibit 2.2" in c.table_name and c.column_name == "Minimum Capital Requirement" and c.location == "p.10"
    assert "Exhibit 11.1" in a.table_name and "Line 7" in a.field_label and a.location == "p.31"
    assert c.source_file == "fannie_2023Q4.pdf"
    assert r.ok


def test_freddie_takes_first_column_not_second(env, freddie_pdf):
    # Freddie's Table 2.2 lists Minimum Capital Requirement FIRST (49), then buffers ($59), total (108)
    r = parse(freddie_pdf, env)
    assert (r.provider, r.period) == ("Freddie Mac", "2025Q1")
    c, a = r.observations[CET1], r.observations[ATA]
    assert c.value_mm == 49_000 and c.value_mm != 59_000
    assert a.value_mm == 3_833_729 and a.raw_value == "$3,833,729"
    assert "Table 2.2" in c.table_name and "Table 11.1" in a.table_name
    assert r.ok


def test_period_inference():
    assert infer_period("fnma-capital-disclosures-2023q4-022724.pdf", "") == "2023Q4"
    assert infer_period("2Q26_ercf_public_disclosure.pdf", "") == "2026Q2"
    assert infer_period("x.pdf", "For the quarterly period ended December 31, 2023") == "2023Q4"


def _redact(src, dst, words, page_idx):
    doc = fitz.open(src)
    page = doc[page_idx]
    for w in words:
        for r in page.search_for(w):
            page.add_redact_annot(r)
    page.apply_redactions()
    doc.save(dst)


def test_missing_fannie_cet1_label_raises_named_error(env, fannie_pdf, tmp_path):
    bad = tmp_path / "bad.pdf"
    _redact(fannie_pdf, bad, ["Common"], 9)
    with pytest.raises(FieldNotFoundError) as e:
        parse(bad, env)
    assert "CET1_amount" in str(e.value) and "bad.pdf" in str(e.value)


def test_missing_freddie_cet1_label_raises_named_error(env, freddie_pdf, tmp_path):
    bad = tmp_path / "bad_freddie.pdf"
    _redact(freddie_pdf, bad, ["CET1"], 9)
    with pytest.raises(FieldNotFoundError) as e:
        parse(bad, env)
    assert "CET1_amount" in str(e.value)
