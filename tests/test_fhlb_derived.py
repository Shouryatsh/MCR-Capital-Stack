"""FHLB derived columns: Total Assets and Actual Risk Based Capital Ratio."""
import pytest

from mcr import fhlb


def test_derive_boston_2026q2():
    d = fhlb.derive({"t91_min_mm": 755.0, "t91_actual_mm": 4213.0, "t92_actual_ratio_pct": 5.45})
    assert d["derived_total_assets_mm"] == pytest.approx(4213 / 0.0545)  # ratio is in percent
    assert d["derived_actual_rbc_ratio_pct"] == pytest.approx(755 / (4213 / 0.0545) * 100)
    assert round(d["derived_total_assets_mm"]) == 77303 and round(d["derived_actual_rbc_ratio_pct"], 2) == 0.98


def test_derive_omits_values_when_inputs_are_missing_or_unusable():
    assert fhlb.derive({"t91_min_mm": 755.0}) == {}
    assert fhlb.derive({"t91_actual_mm": 4213.0, "t92_actual_ratio_pct": 0.0}) == {}
    only_assets = fhlb.derive({"t91_actual_mm": 4213.0, "t92_actual_ratio_pct": 5.45})
    assert "derived_total_assets_mm" in only_assets and "derived_actual_rbc_ratio_pct" not in only_assets


def test_api_adds_derived_cells_and_flags_them(monkeypatch):
    from mcr import api
    row = lambda f, v: {"period": "2026Q2", "report_date": "2026-06-30", "fhlbank": "Boston", "field": f, "parsed_value": v,
                        "unit": "percent" if f.endswith("pct") else "USD millions", "raw_value": str(v), "source_file": "x.pdf",
                        "source_url": "", "table_name": "T", "location": "p.1"}
    rows = [row("t91_min_mm", 755.0), row("t91_actual_mm", 4213.0), row("t92_actual_ratio_pct", 5.45)]
    monkeypatch.setattr(fhlb, "load_rows", lambda db=None: rows)
    monkeypatch.setattr(fhlb, "load_gaps", lambda db=None: [])
    out = api.fhlb_data()
    cells = out["periods"][0]["banks"]["Boston"]
    assert cells["derived_total_assets_mm"]["text"] == "77,303" and cells["derived_total_assets_mm"]["derived"] is True
    assert cells["derived_actual_rbc_ratio_pct"]["text"] == "0.98%"
    assert [f["field"] for f in out["fields"] if f.get("derived")] == ["derived_total_assets_mm", "derived_actual_rbc_ratio_pct"]
    assert out["periods"][0]["derived_banks"] == []  # only 1 bank here, so no Combined can be derived


def _eleven_banks():
    return {b: {"t91_min_mm": 100.0, "t91_actual_mm": 500.0, "t92_min_mm": 400.0, "t92_actual_mm": 500.0, "t92_actual_ratio_pct": 5.0}
            for b in fhlb.BANKS}


def test_derive_combined_sums_banks_and_weights_the_ratio():
    banks = _eleven_banks()
    banks["Boston"] |= {"t92_actual_mm": 1000.0, "t92_actual_ratio_pct": 20.0}  # $5,000mm of assets; the others have $10,000mm each
    c = fhlb.derive_combined(banks)
    assert c["t91_min_mm"] == 1100.0 and c["t91_actual_mm"] == 5500.0 and c["t92_min_mm"] == 4400.0 and c["t92_actual_mm"] == 6000.0
    assets = 1000 / 0.20 + 10 * (500 / 0.05)
    assert c["t92_actual_ratio_pct"] == pytest.approx(6000 / assets * 100)
    assert abs(c["t92_actual_ratio_pct"] - (20 + 10 * 5) / 11) > 0.5  # not the simple average of the ratios
    assert "t92_min_ratio_pct" not in c


def test_derive_combined_needs_all_eleven_banks():
    banks = _eleven_banks()
    del banks["Topeka"]
    assert fhlb.derive_combined(banks) == {}
    banks = _eleven_banks()
    banks["Dallas"]["t92_actual_ratio_pct"] = None
    assert fhlb.derive_combined(banks) == {}


def test_api_derives_combined_only_when_not_published(monkeypatch):
    from mcr import api
    rows = []
    for period in ("2024Q4", "2025Q4"):
        for bank, vals in _eleven_banks().items():
            for f, v in vals.items():
                rows.append({"period": period, "report_date": "2025-12-31", "fhlbank": bank, "field": f, "parsed_value": v,
                             "unit": "percent" if f.endswith("pct") else "USD millions", "raw_value": str(v), "source_file": "x.pdf",
                             "source_url": "", "table_name": "T", "location": "p.1"})
    published = {"t91_min_mm": 1.0, "t91_actual_mm": 2.0, "t92_min_mm": 3.0, "t92_actual_mm": 4.0, "t92_actual_ratio_pct": 5.0}
    for f, v in published.items():
        rows.append({"period": "2024Q4", "report_date": "2024-12-31", "fhlbank": "Combined", "field": f, "parsed_value": v,
                     "unit": "percent" if f.endswith("pct") else "USD millions", "raw_value": str(v), "source_file": "x.pdf",
                     "source_url": "", "table_name": "T", "location": "p.1"})
    monkeypatch.setattr(fhlb, "load_rows", lambda db=None: rows)
    monkeypatch.setattr(fhlb, "load_gaps", lambda db=None: [])
    by = {p["period"]: p for p in api.fhlb_data()["periods"]}
    assert by["2024Q4"]["derived_banks"] == [] and by["2024Q4"]["banks"]["Combined"]["t91_min_mm"]["value"] == 1.0  # published value kept
    assert not by["2024Q4"]["banks"]["Combined"]["t91_min_mm"].get("derived")
    derived = by["2025Q4"]
    assert derived["derived_banks"] == ["Combined"]
    comb = derived["banks"]["Combined"]
    assert comb["t91_min_mm"]["value"] == 1100.0 and comb["t91_min_mm"]["derived"] is True
    assert comb["derived_total_assets_mm"]["derived"] is True and "derived_actual_rbc_ratio_pct" in comb

