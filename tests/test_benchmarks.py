"""Benchmark calculation engine: exact units, Benchmark 1 reference values, recalculation, dependencies, validation."""
import copy
from decimal import Decimal, localcontext
import pytest
from fastapi.testclient import TestClient

from mcr import api, benchmarks as bm, store
from mcr.models import ATA, CET1, Check, Observation, ParseResult
from test_tabs import seed_gnma


@pytest.fixture()
def loaded(env):
    seed_gnma(env)  # FY2022 + FY2023 official reports (+ FY2021 as a comparative), from the real report pages
    return env


def seed_q3_2023():
    for prov, cet1, ata in (("Fannie Mae", "61", "4,552,448"), ("Freddie Mac", "49", "3,833,729")):
        obs = {}
        for field, raw, units in ((CET1, cet1, "billions"), (ATA, ata, "millions")):
            obs[field] = Observation(provider=prov, period="2023Q3", field=field, source_file=f"{prov}_2023Q3.pdf", table_name="Table",
                                     row_identifier="r", field_label=field, raw_value=raw, parsed_value=float(raw.replace(",", "")),
                                     units_detected=units, value_mm=0.0, location="p.9")
        store.save_result(ParseResult(prov, "2023Q3", obs, [Check("positive", "pass")]))
    # a non-Q3 quarter must never be used for a fiscal-year-end benchmark
    obs = {f: Observation(provider="Fannie Mae", period="2023Q4", field=f, source_file="x.pdf", table_name="T", row_identifier="r", field_label=f,
                          raw_value="1", parsed_value=1.0, units_detected="billions", value_mm=0.0) for f in (CET1, ATA)}
    store.save_result(ParseResult("Fannie Mae", "2023Q4", obs, []))


def res(payload, number, fy):
    return next(r for r in payload["results"] if r["number"] == number and r["fiscal_year"] == fy)


def check(payload, starts):
    return next(c for c in payload["validation"] if c["name"].startswith(starts))


# ------------------------------------------------------------------ Benchmark 1
def test_benchmark_1_fy2023_is_exact_and_reconciles_to_the_specified_number(loaded):
    r = res(bm.build_payload(), 1, 2023)
    assert r["name"] == "Leverage based CET1 (GSEs)" and r["status"] == "ok" and r["reporting_date"] == "2023-09-30"
    assert r["result_usd"] == "26136236510"  # 1% of $2,613,623,651,000
    assert r["result_billions"] == "26.13623651"  # unrounded, available in the calculation details
    assert r["result_billions_text"] == "$26.14B"
    assert r["result_thousands_text"] == "$26,136,236.51"  # the figure in the business specification, in USD thousands as published
    assert r["calculation"] == "2,613,623,651,000 × 0.01 = 26,136,236,510"
    assert r["formula"] == "gnma_total_exposure * adjustment_pct" and r["assumptions"] == {"adjustment_pct": "0.01"}
    assert [i["name"] for i in r["inputs"]] == ["gnma_total_exposure"]


def test_benchmark_1_is_not_scaled_by_1e3(loaded):
    # The report prints USD *thousands*; reading $2,613,623,651 as dollars would give $0.03B, which is 1,000x too small.
    r = res(bm.build_payload(), 1, 2023)
    assert r["result_billions_text"] != "$0.03B"
    assert bm.fmt_billions(Decimal("26136236.51")) == "$0.03B"  # what the mis-scaled reading would show
    assert bm.fmt_billions(Decimal("26136236510")) == "$26.14B"


def test_every_historical_year_uses_its_own_exposure(loaded):
    p = bm.build_payload()
    got = {r["fiscal_year"]: r["result_usd"] for r in p["results"] if r["number"] == 1}
    assert got == {2021: "24266148930", 2022: "24423510950", 2023: "26136236510"}  # 1% of each year's own exposure
    assert [r["fiscal_year"] for r in p["results"] if r["number"] == 1] == [2021, 2022, 2023]  # chronological


def test_summary_latest_prior_and_unrounded_yoy(loaded):
    s = bm.build_payload()["summary"][0]
    assert s["latest"]["fiscal_year"] == 2023 and s["prior"]["fiscal_year"] == 2022
    y = s["yoy"]
    assert y["abs_usd"] == "1712725560" and y["abs_billions_text"] == "+$1.71B"
    assert y["pct"] == round((26136236510 - 24423510950) / 24423510950 * 100, 4) == 7.0126  # from unrounded values
    first = bm.summarize(bm.load_definitions(), [r for r in bm.build_payload()["results"] if r["fiscal_year"] == 2021])[0]
    assert first["yoy"] is None  # no FY2020 value: no fabricated change


# ------------------------------------------------------------------ Benchmark 2
def test_benchmark_2_fy2023_is_exact(loaded):
    r = res(bm.build_payload(), 2, 2023)
    assert r["name"] == "GSE Risk Based Capital" and r["status"] == "ok" and r["reporting_date"] == "2023-09-30"
    assert r["result_usd"] == "19994220930.15"  # $2,613,623,651,000 x 17% x 4.5%
    assert r["result_billions"] == "19.99422093015"
    assert r["result_billions_text"] == "$19.99B"
    assert r["formula"] == "gnma_total_exposure * risk_weight_pct * minimum_cet1_ratio_pct"
    assert r["assumptions"] == {"risk_weight_pct": "0.17", "minimum_cet1_ratio_pct": "0.045"}
    assert [i["name"] for i in r["inputs"]] == ["gnma_total_exposure"]


def test_benchmark_2_every_historical_year_uses_its_own_exposure(loaded):
    p = bm.build_payload()
    got = {r["fiscal_year"]: r["result_usd"] for r in p["results"] if r["number"] == 2}
    assert got == {2021: "18563603931.45", 2022: "18683985876.75", 2023: "19994220930.15"}  # 17% x 4.5% of each year's own exposure


# ------------------------------------------------------------------ Benchmark 4
def test_benchmark_4_fy2023_is_exact(loaded):
    r = res(bm.build_payload(), 4, 2023)
    assert r["name"] == "FHA Minimum Capital Requirement" and r["status"] == "ok" and r["reporting_date"] == "2023-09-30"
    assert r["result_usd"] == "13068118255"  # $2,613,623,651,000 x 25% x 2%
    assert r["result_billions_text"] == "$13.07B"
    assert r["formula"] == "gnma_total_exposure * position_in_line_pct * fha_min_capital_pct"
    assert r["assumptions"] == {"position_in_line_pct": "0.25", "fha_min_capital_pct": "0.02"}
    assert [i["name"] for i in r["inputs"]] == ["gnma_total_exposure"]
    assert r["calculation"] == "(2,613,623,651,000 × 0.25) × 0.02 = 13,068,118,255"


def test_benchmark_4_every_historical_year_and_editable_assumptions(loaded):
    got = {r["fiscal_year"]: r["result_usd"] for r in bm.build_payload()["results"] if r["number"] == 4}
    assert got == {2021: "12133074465", 2022: "12211755475", 2023: "13068118255"}
    bm.set_assumption(4, "fha_min_capital_pct", "0.03")
    assert res(bm.build_payload(), 4, 2023)["result_usd"] == "19602177382.5"  # 2,613,623,651,000 x 25% x 3%
    bm.reset_assumption(4, "fha_min_capital_pct")
    assert res(bm.build_payload(), 4, 2023)["result_usd"] == "13068118255"


# ------------------------------------------------------------------ Benchmarks 3 and 5 (FHLB ratios)
def seed_fhlb(period, combined=None):
    """11 FHLBanks with distinct figures (+ an optional published Combined row), saved like a real ingest."""
    from mcr import fhlb
    banks = {b: {"t91_min_mm": 100.0 + i, "t91_actual_mm": 500.0 + 10 * i, "t92_min_ratio_pct": 4.0,
                 "t92_actual_ratio_pct": 5.0 + 0.1 * i, "t92_min_mm": 400.0, "t92_actual_mm": 500.0 + 10 * i} for i, b in enumerate(fhlb.BANKS)}
    if combined:
        banks["Combined"] = combined
    obs = [fhlb.Observation(period, "", b, f, f, str(v), v, "percent" if f.endswith("pct") else "USD millions", "fhlb.pdf", "", "Table 9.x", "p.1")
           for b, vals in banks.items() for f, v in vals.items()]
    store.save_fhlb(period, fhlb.FhlbResult(period, "", obs))
    return banks


def inp(r, name):
    return next(i for i in r["inputs"] if i["name"] == name)


def test_benchmark_3_uses_the_fhlb_minimum_regulatory_capital_ratio(loaded):
    seed_fhlb("2023Q3")
    r = res(bm.build_payload(), 3, 2023)
    assert r["name"] == "FHLB Minimum Regulatory Capital (GNMA)" and r["status"] == "ok"
    assert r["formula"] == "gnma_total_exposure * credit_risk_density_pct * fhlb_regulatory_capital_min_ratio"
    assert r["assumptions"] == {"credit_risk_density_pct": "0.17"}
    assert r["result_usd"] == "17772640826.8"  # $2,613,623,651,000 x 17% x 4.00%
    assert r["calculation"] == "(2,613,623,651,000 × 0.17) × 0.04 = 17,772,640,826.8"
    assert sorted(i["name"] for i in r["inputs"]) == ["fhlb_regulatory_capital_min_ratio", "gnma_total_exposure"]
    ratio = inp(r, "fhlb_regulatory_capital_min_ratio")
    assert ratio["unit"] == "ratio" and ratio["usd"] == "0.04" and ratio["billions_text"] == "4.00%" and ratio["kind"] == "official"


def test_benchmark_5_derives_the_combined_row_when_it_is_not_published(loaded):
    from mcr import fhlb
    banks = seed_fhlb("2023Q3")
    members = [banks[b] for b in fhlb.BANKS]
    rbc_min, regcap = sum(Decimal(str(m["t91_min_mm"])) for m in members), sum(Decimal(str(m["t92_actual_mm"])) for m in members)
    rbc_act = sum(Decimal(str(m["t91_actual_mm"])) for m in members)
    with localcontext() as c:
        c.prec = 60
        assets_reg = sum(Decimal(str(m["t92_actual_mm"])) / (Decimal(str(m["t92_actual_ratio_pct"])) / 100) for m in members)
        ratio_actual = regcap / assets_reg  # Combined regulatory capital ratio (a fraction)
        expected_ratio = rbc_min / (rbc_act / ratio_actual)  # Combined "Actual Risk Based Capital Ratio (derived)" as a fraction
    r = res(bm.build_payload(), 5, 2023)
    assert r["name"] == "FHLB Actual Risk Based Capital (GNMA)" and r["status"] == "ok"
    assert r["formula"] == "gnma_total_exposure * credit_risk_density_pct * fhlb_combined_actual_rbc_ratio"
    i = inp(r, "fhlb_combined_actual_rbc_ratio")
    assert i["kind"] == "derived" and "derived as the sum of the 11 FHLBanks" in i["note"]
    assert abs(Decimal(i["usd"]) - expected_ratio) < Decimal("1e-14")
    assert abs(Decimal(r["result_usd"]) - Decimal("2613623651000") * Decimal("0.17") * expected_ratio) < Decimal("0.01")


def test_benchmark_5_uses_a_published_combined_row_as_is(loaded):
    seed_fhlb("2022Q3", combined={"t91_min_mm": 1000.0, "t91_actual_mm": 5000.0, "t92_min_mm": 4000.0, "t92_actual_mm": 5000.0, "t92_actual_ratio_pct": 5.0})
    r = res(bm.build_payload(), 5, 2022)
    # assets = 5000 / 5% = 100,000; ratio = 1000 / 100,000 = 1%
    i = inp(r, "fhlb_combined_actual_rbc_ratio")
    assert r["status"] == "ok" and i["usd"] == "0.01" and i["note"] == "Combined row as published"
    assert r["result_usd"] == "4151996861.5"  # $2,442,351,095,000 x 17% x 1%


def test_fhlb_benchmarks_flag_years_without_fhlb_data_and_never_substitute(loaded):
    seed_fhlb("2023Q3")
    p = bm.build_payload()
    for n in (3, 5):
        r = res(p, n, 2022)
        assert r["status"] == "missing_input" and r["result_usd"] is None and "not substituted" in r["message"]
    assert check(p, "Missing inputs are flagged")["status"] == "warn"


def test_benchmark_3_needs_all_eleven_banks_to_agree_on_the_minimum_ratio(loaded):
    from mcr import fhlb
    banks = seed_fhlb("2023Q3")
    obs = [fhlb.Observation("2023Q3", "", b, f, f, str(v), v + (0.5 if (b, f) == ("Boston", "t92_min_ratio_pct") else 0), "percent" if f.endswith("pct") else "USD millions",
                            "fhlb.pdf", "", "Table 9.x", "p.1") for b, vals in banks.items() for f, v in vals.items()]
    store.save_fhlb("2023Q3", fhlb.FhlbResult("2023Q3", "", obs))
    assert res(bm.build_payload(), 3, 2023)["status"] == "missing_input"


# ------------------------------------------------------------------ Benchmarks 6-10 are never invented
def test_unconfirmed_benchmarks_require_confirmation_and_have_no_numbers(loaded):
    p = bm.build_payload()
    assert [d["number"] for d in p["definitions"]] == list(range(1, 11))
    for n in range(6, 11):
        d = p["definitions"][n - 1]
        assert d["status"] == "unconfirmed" and not d["confirmed"] and d["formula"] is None and d["assumptions"] == []
        for fy in (2021, 2022, 2023):
            r = res(p, n, fy)
            assert r["status"] == "unconfirmed" and r["result_usd"] is None and r["result_billions"] is None
            assert r["result_billions_text"] == "—"
    pending = check(p, "All benchmarks have a confirmed definition")
    assert pending["status"] == "warn" and "6, 7, 8, 9, 10" in pending["detail"]
    assert all(s["latest"] is None for s in p["summary"][5:])



# ------------------------------------------------------------------ validation
def test_validation_checks_pass_on_real_data(loaded):
    p = bm.build_payload()
    by = {c["name"]: c["status"] for c in p["validation"]}
    assert by["GNMA Total Maximum Exposure to Loss = Outstanding MBS + Outstanding MBS Commitments"] == "pass"
    assert by["Benchmark 1 uses the business-specified 1% adjustment"] == "pass"
    assert by["FY2023 Benchmark 1 = $26,136,236.51 (USD thousands as published) = $26,136,236,510"] == "pass"
    assert by["Reporting dates align across all inputs of a fiscal year (Sept 30)"] == "pass"
    assert not [c for c in p["validation"] if c["status"] == "fail"]


# ------------------------------------------------------------------ assumptions: validated, persisted, recalculated
def test_changing_the_assumption_recalculates_every_year_and_is_flagged(loaded):
    bm.set_assumption(1, "adjustment_pct", "0.02")
    p = bm.build_payload()
    assert res(p, 1, 2023)["result_usd"] == "52272473020" and res(p, 1, 2022)["result_usd"] == "48847021900"
    assert res(p, 1, 2023)["assumptions"] == {"adjustment_pct": "0.02"} and res(p, 1, 2023)["result_billions_text"] == "$52.27B"
    flag = check(p, "Benchmark 1 uses the business-specified 1% adjustment")
    assert flag["status"] == "warn" and "0.02" in flag["detail"]
    assert not [c for c in p["validation"] if c["name"].startswith("FY2023 Benchmark 1 =")]  # reference only applies to the specified 1%
    assert check(p, "Every result reproduces")["status"] == "pass"  # still reproducible with the new assumption


def test_assumption_edit_is_persisted_and_changes_the_version(loaded):
    v0 = bm.build_payload()["assumptions_version"]
    bm.set_assumption(1, "adjustment_pct", "0.015")
    assert bm.load_definitions()[0]["assumptions"]["adjustment_pct"] == "0.015"
    v1 = bm.build_payload()["assumptions_version"]
    assert v1 != v0
    bm.reset_assumption(1, "adjustment_pct")
    p = bm.build_payload()
    assert p["assumptions_version"] == v0 and res(p, 1, 2023)["result_usd"] == "26136236510"


@pytest.mark.parametrize("bad", ["0", "-0.01", "1.5", "abc", "", "nan", "inf", "1e999999"])
def test_invalid_assumptions_are_rejected_and_change_nothing(loaded, bad):
    with pytest.raises(ValueError):
        bm.set_assumption(1, "adjustment_pct", bad)
    assert bm.load_definitions()[0]["assumptions"]["adjustment_pct"] == "0.01"


def test_cannot_edit_unconfirmed_or_unknown_assumptions(loaded):
    with pytest.raises(ValueError, match="not confirmed"):
        bm.set_assumption(6, "adjustment_pct", "0.5")
    with pytest.raises(ValueError):
        bm.set_assumption(1, "nonsense", "0.5")
    with pytest.raises(KeyError):
        bm.set_assumption(99, "adjustment_pct", "0.5")


def test_hand_edited_bad_assumption_is_reported_not_calculated(loaded):
    defs = bm.load_definitions()
    defs[0]["assumptions"]["adjustment_pct"] = "5"
    bm.save_definitions(defs)
    p = bm.build_payload()
    r = res(p, 1, 2023)
    assert r["status"] == "invalid_assumption" and r["result_usd"] is None and "at most 1" in r["message"]
    assert check(p, "Benchmark definitions are valid")["status"] == "fail"


# ------------------------------------------------------------------ dependency-driven calculation
def confirmed(number, formula, assumptions=None):
    return {"number": number, "key": f"b{number}", "name": f"Test {number}", "status": "confirmed", "description": "", "formula": formula,
            "assumptions": assumptions or {}, "assumption_meta": {}, "reference": "test"}


def with_defs(*overrides):
    defs = copy.deepcopy(bm.load_definitions())
    for o in overrides:
        defs[o["number"] - 1] = o
    bm.save_definitions(defs)


def test_benchmarks_can_depend_on_other_benchmarks_and_recalculate_together(loaded):
    with_defs(confirmed(2, "benchmark_1 * 2"))
    p = bm.build_payload()
    assert res(p, 2, 2023)["result_usd"] == "52272473020" and res(p, 2, 2023)["depends_on"] == ["benchmark_1"]
    bm.set_assumption(1, "adjustment_pct", "0.03")  # dependent result follows its input
    assert res(bm.build_payload(), 2, 2023)["result_usd"] == "156817419060"


def test_changing_one_benchmark_does_not_touch_an_unrelated_one(loaded):
    with_defs(confirmed(2, "gnma_total_exposure * 0.5"))
    before = res(bm.build_payload(), 2, 2023)["result_usd"]
    bm.set_assumption(1, "adjustment_pct", "0.07")
    assert res(bm.build_payload(), 2, 2023)["result_usd"] == before == "1306811825500"


def test_circular_dependencies_are_detected_and_isolated(loaded):
    with_defs(confirmed(2, "benchmark_3 + 1"), confirmed(3, "benchmark_2 + 1"))
    p = bm.build_payload()
    for n in (2, 3):
        r = res(p, n, 2023)
        assert r["status"] == "error" and "circular dependency" in r["message"] and r["result_usd"] is None
    assert res(p, 1, 2023)["status"] == "ok"  # unrelated benchmark unaffected
    assert check(p, "Benchmark definitions are valid")["status"] == "fail"


def test_missing_inputs_are_flagged_not_substituted_from_other_years(loaded):
    seed_q3_2023()
    with_defs(confirmed(2, "cet1_fannie_mae / gnma_total_exposure"))
    p = bm.build_payload()
    ok = res(p, 2, 2023)
    assert ok["status"] == "ok" and [i["name"] for i in ok["inputs"]] == ["cet1_fannie_mae", "gnma_total_exposure"]
    with localcontext() as c:
        c.prec = bm.PREC
        expected = Decimal(61_000_000_000) / Decimal(2_613_623_651_000)  # $61bn CET1 (printed in billions) vs $2.6tn exposure
    assert Decimal(ok["result_usd"]) == expected
    miss = res(p, 2, 2022)
    assert miss["status"] == "missing_input" and "cet1_fannie_mae" in miss["message"] and miss["result_usd"] is None
    assert check(p, "Missing inputs are flagged")["status"] == "warn"


def test_cet1_and_assets_are_converted_to_usd_once_and_only_q3_is_used(loaded):
    seed_q3_2023()
    p = bm.build_payload()
    rows = {(i["fiscal_year"], i["name"]): i for i in p["inputs"]}
    cet1, ata = rows[(2023, "cet1_fannie_mae")], rows[(2023, "ata_fannie_mae")]
    assert cet1["usd"] == "61000000000" and cet1["source_units"] == "USD billions" and cet1["source_raw"] == "61" and cet1["billions"] == "61"
    assert ata["usd"] == "4552448000000" and ata["source_units"] == "USD millions" and ata["billions_text"] == "$4,552.45B"
    assert (rows[(2023, "cet1_freddie_mac")]["usd"], rows[(2023, "ata_freddie_mac")]["usd"]) == ("49000000000", "3833729000000")
    assert all(i["reporting_date"] == f"{i['fiscal_year']}-09-30" for i in p["inputs"])  # Q4 2023 row (1 billion) was not used
    assert rows[(2023, "gnma_total_exposure")]["kind"] == "derived" and rows[(2023, "gnma_outstanding_mbs")]["kind"] == "official"
    assert rows[(2023, "gnma_total_exposure")]["location"].startswith("PDF p.") and "A-20" in rows[(2023, "gnma_total_exposure")]["location"]


def test_formula_errors_are_explicit(loaded):
    with_defs(confirmed(2, "gnma_total_exposure / 0"), confirmed(3, "mystery_input * 2"), confirmed(4, "__import__('os')"))
    p = bm.build_payload()
    assert res(p, 2, 2023)["status"] == "error" and "division by zero" in res(p, 2, 2023)["message"]
    assert res(p, 3, 2023)["status"] == "invalid_assumption" and "unknown input" in res(p, 3, 2023)["message"]
    assert res(p, 4, 2023)["status"] == "invalid_assumption" and "unsupported syntax" in res(p, 4, 2023)["message"]


# ------------------------------------------------------------------ formula language, precision, formatting
def test_decimal_precision_no_float_error():
    assert bm.evaluate("a + b", {"a": Decimal("0.1"), "b": Decimal("0.2")}) == Decimal("0.3")
    assert bm.evaluate("a * 0.01", {"a": Decimal("2613623651000")}) == Decimal("26136236510")
    assert bm.evaluate("(a - b) / b * 100", {"a": Decimal(3), "b": Decimal(2)}) == Decimal(50)


@pytest.mark.parametrize("src", ["f(1)", "a.b", "a ** 2", "a if b else c", "[1]", "'x'", "a; b", "lambda: 1"])
def test_formula_language_rejects_everything_but_arithmetic(src):
    with pytest.raises(bm.FormulaError):
        bm.parse_formula(src)


def test_billions_conversion_happens_once_and_rounds_only_the_text():
    assert bm.usd_to_billions(Decimal("26136236510")) == Decimal("26.13623651")
    assert bm.fmt_billions(Decimal("26136236510")) == "$26.14B" and bm.fmt_billions(Decimal("26136236510"), 8) == "$26.13623651B"
    assert bm.fmt_billions(Decimal("125000000")) == "$0.13B"  # half-up, not banker's rounding
    assert bm.fmt_billions(Decimal("-500000000")) == "−$0.50B" and bm.fmt_billions(None) == "—"
    assert bm.fmt_billions(Decimal("3010690643000")) == "$3,010.69B"


# ------------------------------------------------------------------ API
@pytest.fixture()
def client(loaded):
    return TestClient(api.create_app(dist=loaded / "nodist"))


def test_api_payload_units_and_edit_flow(client):
    p = client.get("/api/benchmarks").json()
    assert p["units"]["display"] == "USD (billions)" and p["units"]["divisor"] == 1_000_000_000
    assert res(p, 1, 2023)["result_billions_text"] == "$26.14B"
    d1 = p["definitions"][0]["assumptions"][0]
    assert (d1["name"], d1["value"], d1["default"], d1["editable"]) == ("adjustment_pct", "0.01", "0.01", True)
    r = client.put("/api/benchmarks/1/assumptions/adjustment_pct", json={"value": "0.02"})
    assert r.status_code == 200 and res(r.json(), 1, 2023)["result_usd"] == "52272473020"
    assert client.put("/api/benchmarks/1/assumptions/adjustment_pct", json={"value": 0.025}).status_code == 200  # JSON numbers accepted
    bad = client.put("/api/benchmarks/1/assumptions/adjustment_pct", json={"value": "7"})
    assert bad.status_code == 422 and "at most 1" in bad.json()["detail"]
    assert client.put("/api/benchmarks/2/assumptions/adjustment_pct", json={"value": "0.5"}).status_code == 422
    assert client.put("/api/benchmarks/42/assumptions/adjustment_pct", json={"value": "0.5"}).status_code == 404
    back = client.delete("/api/benchmarks/1/assumptions/adjustment_pct")
    assert back.status_code == 200 and res(back.json(), 1, 2023)["result_usd"] == "26136236510"


def test_api_requires_the_token_for_benchmarks(client, monkeypatch):
    monkeypatch.setenv("MCR_TOKEN", "s3cret")
    assert client.get("/api/benchmarks").status_code == 401
    assert client.put("/api/benchmarks/1/assumptions/adjustment_pct", json={"value": "0.02"}).status_code == 401
    assert client.get("/api/benchmarks", headers={"X-MCR-Token": "s3cret"}).status_code == 200
