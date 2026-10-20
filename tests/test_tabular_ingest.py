import zipfile

import pytest

from mcr import config, store
from mcr.ingest import (ingest_file, ingest_upload, newest_per_provider, parse_filename, unpack_zip, validate_file)
from mcr.mappings import load_mappings, save_mappings
from mcr.models import ATA, CET1, UploadRejected
from mcr.ratio import benchmark_table
from samples import make_banka_csv, make_banka_xlsx, make_no_units_xlsx, make_zip


def test_xlsx_extraction_with_provenance(with_banka, tmp_path):
    o = ingest_file(make_banka_xlsx(tmp_path / "BankA_20260930_disclosure.xlsx"))
    assert o.status == "ok", o.message
    assert (o.provider, o.period) == ("BankA", "2026Q3")
    c, a = o.result.observations[CET1], o.result.observations[ATA]
    assert (c.value_mm, a.value_mm) == (4250, 61800)
    assert (c.table_name, c.field_label, c.location) == ("CapitalTable", "Common Equity Tier 1 capital", "CapitalTable!R4C2")
    assert (a.table_name, a.field_label) == ("AssetsTable", "Adjusted total assets")
    assert c.source_file == "BankA_20260930_disclosure.xlsx" and c.raw_value == "4250"


def test_units_detected_and_converted(with_banka, tmp_path):
    o = ingest_file(make_banka_xlsx(tmp_path / "BankA_20260930_disclosure.xlsx", cet1=4.25, ata=61.8, units="billions"))
    assert o.status == "ok"
    assert o.result.observations[CET1].value_mm == pytest.approx(4250)
    assert o.result.observations[ATA].units_detected == "billions"


def test_file_units_override_mapping_hint(with_banka, tmp_path):
    m = load_mappings()
    for spec in m["BankA"]["fields"].values():
        spec["units"] = "millions"  # wrong hint; the file says billions
    save_mappings(m)
    o = ingest_file(make_banka_xlsx(tmp_path / "BankA_20260930_disclosure.xlsx", cet1=4.25, ata=61.8, units="billions"))
    c = o.result.observations[CET1]
    assert c.value_mm == pytest.approx(4250) and c.units_source == "detected"


def test_no_unit_statement_and_no_hint_is_an_error(with_banka, tmp_path):
    o = ingest_file(make_no_units_xlsx(tmp_path / "BankA_20260930_disclosure.xlsx"))
    assert o.status == "error" and "no unit statement" in o.message


def test_mapping_unit_hint_used_only_when_file_states_none(with_banka, tmp_path):
    m = load_mappings()
    for spec in m["BankA"]["fields"].values():
        spec["units"] = "millions"
    save_mappings(m)
    o = ingest_file(make_no_units_xlsx(tmp_path / "BankA_20260930_disclosure.xlsx"))
    assert o.status == "ok" and o.result.observations[CET1].units_source == "mapping"


def test_ambiguous_field_is_reported(with_banka, tmp_path):
    o = ingest_file(make_banka_xlsx(tmp_path / "BankA_20260930_disclosure.xlsx", decoy=True))
    assert o.status == "error" and "several different values" in o.message and "AssetsTable" in o.message


def test_missing_field_names_field_and_file(with_banka, tmp_path):
    m = load_mappings()
    m["BankA"]["fields"]["CET1_amount"]["field"] = "Nonexistent line item"
    save_mappings(m)
    o = ingest_file(make_banka_xlsx(tmp_path / "BankA_20260930_disclosure.xlsx"))
    assert o.status == "error" and "CET1_amount" in o.message and "BankA_20260930_disclosure.xlsx" in o.message


def test_csv_supported(with_banka, tmp_path):
    m = load_mappings()
    m["BankA"]["fields"]["CET1_amount"].pop("sheet")
    m["BankA"]["fields"]["Adjusted_total_assets"].pop("sheet")
    save_mappings(m)
    o = ingest_file(make_banka_csv(tmp_path / "BankA_20260930_disclosure.csv"))
    assert o.status == "ok", o.message
    assert o.result.observations[CET1].value_mm == 4250


def test_filename_pattern():
    assert parse_filename("BankA_20260930_disclosure.xlsx") == ("BankA", "2026Q3")
    assert parse_filename("Bank_B_20260331_disclosure.csv") == ("Bank B", "2026Q1")
    assert parse_filename("random.xlsx") is None


def test_unknown_provider_gives_clear_message(env, tmp_path):
    o = ingest_file(make_banka_xlsx(tmp_path / "Zeta_20260930_disclosure.xlsx"))
    assert o.status == "error" and "no mapping for provider" in o.message


def test_upload_validation(env, tmp_path):
    exe = tmp_path / "x.exe"
    exe.write_bytes(b"MZ")
    with pytest.raises(UploadRejected):
        validate_file(exe)
    fake = tmp_path / "fake.pdf"
    fake.write_bytes(b"not a pdf")
    with pytest.raises(UploadRejected):
        validate_file(fake)
    assert ingest_file(fake).status == "error"


def test_zip_package_and_zip_slip(with_banka, tmp_path):
    a = make_banka_xlsx(tmp_path / "BankA_20260630_disclosure.xlsx", cet1=4100, ata=60900)
    b = make_banka_xlsx(tmp_path / "BankA_20260930_disclosure.xlsx")
    z = make_zip(tmp_path / "pkg.zip", [a, b])
    outs = ingest_upload(z)
    assert sorted(o.period for o in outs) == ["2026Q2", "2026Q3"] and all(o.status == "ok" for o in outs)
    assert [o.period for o in ingest_upload(z, only_newest=True)] == ["2026Q3"]
    evil = tmp_path / "evil.zip"
    with zipfile.ZipFile(evil, "w") as zf:
        zf.writestr("../../escape.csv", "a,b\n")
    dest = tmp_path / "out"
    unpack_zip(evil, dest)  # the member name is flattened into dest, never written outside it
    assert not (tmp_path / "escape.csv").exists() and (dest / "escape.csv").exists()


def test_newest_per_provider(tmp_path):
    ps = [tmp_path / n for n in ("BankA_20260630_disclosure.xlsx", "BankA_20260930_disclosure.xlsx", "BankB_20260331_disclosure.xlsx")]
    for p in ps:
        p.write_bytes(b"PK")
    assert sorted(p.name for p in newest_per_provider(ps)) == ["BankA_20260930_disclosure.xlsx", "BankB_20260331_disclosure.xlsx"]


def test_store_series_and_benchmarks(with_banka, tmp_path, fannie_pdf, freddie_pdf):
    ingest_file(fannie_pdf, "Fannie Mae", "2023Q4")
    ingest_file(freddie_pdf, "Freddie Mac", "2025Q1")
    assert store.series("Fannie Mae")[0]["ratio"] == pytest.approx(61_000 / 4_552_448)
    peers = config.load_peers()
    peers[2].update(name="Bank A", provider="BankA")
    config.save_peers(peers)
    ingest_file(make_banka_xlsx(tmp_path / "BankA_20250331_disclosure.xlsx"))
    bt = benchmark_table("2025Q1")
    assert len(bt) == 10
    assert [r["status"] for r in bt[:3]] == ["no data for this period", "ok", "ok"]  # no Fannie 2025Q1 loaded here
    assert all(r["status"] == "not configured" for r in bt[3:])
    top = max((r for r in bt if r["ratio"]), key=lambda r: r["ratio"])
    assert top["name"] == "Bank A" and top["rank"] == 1 and top["of"] == 2
    assert "Table 11.1" in next(r for r in bt if r["name"] == "Freddie Mac")["ata_src"]["table_name"]
