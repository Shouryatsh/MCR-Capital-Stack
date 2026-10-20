"""Builds the sample spreadsheet / CSV / zip fixtures. Run `python tests/samples.py` to write them to sample_data/."""
from __future__ import annotations

import zipfile
from pathlib import Path

import openpyxl

ROOT = Path(__file__).resolve().parent.parent

# BankA mapping used in the tests / README demo (different sheets and field names than the GSEs)
BANKA_MAPPING = {
    "kind": "tabular",
    "fields": {
        "CET1_amount": {"sheet": "CapitalTable", "field": "Common Equity Tier 1 capital"},
        "Adjusted_total_assets": {"sheet": "AssetsTable", "field": "Adjusted total assets"},
    },
}


def make_banka_xlsx(path: Path, cet1=4250, ata=61800, units="millions", decoy=False) -> Path:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "CapitalTable"
    ws.append(["BankA regulatory capital"])
    ws.append([f"(Dollars in {units})"])
    ws.append(["Item", "Amount", "Ratio"])
    ws.append(["Common Equity Tier 1 capital", cet1, None])
    ws.append(["Tier 1 capital", cet1 + 500, None])
    wa = wb.create_sheet("AssetsTable")
    wa.append(["Leverage exposure"])
    wa.append([f"(in {units})"])
    wa.append(["Item", "Amount"])
    wa.append(["Adjusted total assets", ata])
    if decoy:  # same label twice with different values -> ambiguous
        wa.append(["Adjusted total assets", ata + 1])
    wb.save(path)
    return path


def make_banka_csv(path: Path, cet1=4250, ata=61800) -> Path:
    path.write_text("Item,Amount\n(Dollars in millions),\n"
                    f"Common Equity Tier 1 capital,\"{cet1:,}\"\nAdjusted total assets,\"{ata:,}\"\n", encoding="utf8")
    return path


def make_no_units_xlsx(path: Path) -> Path:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "CapitalTable"
    ws.append(["Common Equity Tier 1 capital", 4250])
    wa = wb.create_sheet("AssetsTable")
    wa.append(["Adjusted total assets", 61800])
    wb.save(path)
    return path


def make_zip(path: Path, members: list[Path]) -> Path:
    with zipfile.ZipFile(path, "w") as z:
        for m in members:
            z.write(m, m.name)
    return path


if __name__ == "__main__":
    out = ROOT / "sample_data"
    out.mkdir(exist_ok=True)
    make_banka_xlsx(out / "BankA_20260930_disclosure.xlsx")
    make_banka_xlsx(out / "BankA_20260630_disclosure.xlsx", cet1=4100, ata=60900)
    make_banka_xlsx(out / "BankB_20260930_disclosure.xlsx", cet1=4.9, ata=71.2, units="billions")
    print("wrote", sorted(p.name for p in out.iterdir()))
