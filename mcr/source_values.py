"""Source values: the raw, as-published figures per entity (Fannie Mae, GNMA, Freddie Mac, FHLBs, FDIC, ...).

The entity list lives in config/source_entities.json (created from DEFAULT_ENTITIES) so new entities can be added without code
changes. An entity without loaded data is shown as empty, never filled with estimates.
"""
from __future__ import annotations

import re
from decimal import Decimal

from . import capital, config, store
from .models import ATA, CET1

DEFAULT_ENTITIES = [
    {"key": "fannie-mae", "name": "Fannie Mae", "kind": "gse", "provider": "Fannie Mae"},
    {"key": "gnma", "name": "GNMA", "kind": "gnma"},
    {"key": "freddie-mac", "name": "Freddie Mac", "kind": "gse", "provider": "Freddie Mac"},
    {"key": "fhlbs", "name": "FHLBs", "kind": "fhlb", "note": "Federal Home Loan Banks"},
    {"key": "gse-gfee", "name": "GSE GFEE", "kind": "gfee", "note": "FHFA Single-Family Guarantee Fees (annual)"},
    {"key": "fdic", "name": "FDIC", "kind": "fdic", "note": "Federal Deposit Insurance Corporation - Deposit Insurance Fund"},
]

# Values supplied by the business for verification (not used to produce any number).
REFERENCE_VALUES = {
    "Fannie Mae": {"period": "2023Q4", "source": "Provided for verification (December 2023 results)",
                   "values": {capital.MIN_RATIO: "4.5", capital.TOTAL_RWA: "1357097", capital.CREDIT_RWA: "1240896"}},
}

# (field, label, unit) shown for the GSEs, in display order.
GSE_METRICS = [
    (CET1, "CET1 minimum capital requirement", "USD millions"),
    (ATA, "Adjusted total assets", "USD millions"),
    (capital.MIN_RATIO, "Minimum capital ratio (CET1)", "percent"),
    (capital.TOTAL_RWA, "Total risk-weighted assets", "USD millions"),
    (capital.CREDIT_RWA, "Credit risk-weighted assets", "USD millions"),
]
_MONTH = {"Q1": ("March", "03-31"), "Q2": ("June", "06-30"), "Q3": ("September", "09-30"), "Q4": ("December", "12-31")}


def load_entities() -> list[dict]:
    return config._load(config.CONFIG_DIR / "source_entities.json", DEFAULT_ENTITIES)


def period_info(period: str) -> tuple[str, str]:
    """'2023Q4' -> ('December 2023', '2023-12-31')."""
    m = re.fullmatch(r"(\d{4})(Q[1-4])", period)
    if not m:
        return period, ""
    month, end = _MONTH[m.group(2)]
    return f"{month} {m.group(1)}", f"{m.group(1)}-{end}"


def fmt_value(value: str, unit: str) -> str:
    d = Decimal(value)
    if unit == "percent":
        return f"{capital._plain(d)}%"
    s = format(d, ",f")
    return s.rstrip("0").rstrip(".") if "." in s else s


def _obs_value(o: dict) -> str:
    """Exact $ millions from the printed value and its unit statement (never from the stored float)."""
    mult = capital.TO_MILLIONS[o["units_detected"]]
    return capital._plain(Decimal(re.sub(r"[^\d.]", "", o["raw_value"])) * mult)


def _cell(row: dict, unit: str) -> dict:
    return {"value": row["value"], "text": fmt_value(row["value"], unit), "unit": unit, "raw_value": row["raw_value"], "source_file": row["source_file"],
            "source_url": row.get("source_url") or "", "table_name": row["table_name"], "line_item": row["line_item"],
            "column_name": row.get("column_name") or "", "location": row["location"]}


def gse_payload(entity: dict, db=None) -> dict:
    provider = entity["provider"]
    periods: dict[str, dict] = {}
    for o in store.get_observations(provider, db):
        if o["field"] not in (CET1, ATA):
            continue
        unit = "USD millions"
        row = {"value": _obs_value(o), "raw_value": o["raw_value"], "source_file": o["source_file"], "source_url": o["source_url"],
               "table_name": o["table_name"], "line_item": o["field_label"], "column_name": o["column_name"], "location": o["location"]}
        periods.setdefault(o["period"], {"values": {}, "checks": []})["values"][o["field"]] = _cell(row, unit)
    for p in capital.load(provider, db):
        d = periods.setdefault(p["period"], {"values": {}, "checks": []})
        for f, r in p["metrics"].items():
            d["values"][f] = _cell(r, r["unit"])
        d["checks"] = [{"name": k["name"], "status": k["status"], "detail": k["detail"]} for k in p["checks"]]
    rows = []
    for period in sorted(periods):
        label, end = period_info(period)
        rows.append({"period": period, "label": label, "period_end": end, **periods[period]})

    validation = []
    capital_rows = [r for r in rows if any(f in r["values"] for f in (capital.MIN_RATIO, capital.TOTAL_RWA, capital.CREDIT_RWA))]
    incomplete = [r["period"] for r in capital_rows if not all(f in r["values"] for f in (capital.MIN_RATIO, capital.TOTAL_RWA, capital.CREDIT_RWA))]
    validation.append({"name": "Minimum capital ratio, total RWA and credit RWA found for every stored period",
                       "status": "fail" if incomplete else ("pass" if capital_rows else "warn"),
                       "detail": f"missing values in {incomplete}" if incomplete else (f"{len(capital_rows)} period(s)" if capital_rows else "no capital metrics stored yet")})
    failed = [(r["period"], c["name"]) for r in rows for c in r["checks"] if c["status"] == "fail"]
    warned = [(r["period"], c["name"]) for r in rows for c in r["checks"] if c["status"] == "warn"]
    total_checks = sum(len(r["checks"]) for r in rows)
    validation.append({"name": "Per-period checks: credit RWA within total, components sum to total, minimum ratio × RWA matches the published CET1 minimum",
                       "status": "fail" if failed else ("warn" if warned else ("pass" if total_checks else "warn")),
                       "detail": (f"failed: {failed}" if failed else f"{total_checks} check(s) across {len(rows)} period(s)") + (f"; warnings: {warned}" if warned else "")})
    ref = REFERENCE_VALUES.get(provider)
    reference = None
    if ref:
        row = next((r for r in rows if r["period"] == ref["period"]), None)
        got = {f: (row["values"].get(f, {}).get("value") if row else None) for f in ref["values"]}
        ok = all(got[f] is not None and Decimal(got[f]) == Decimal(v) for f, v in ref["values"].items())
        label = period_info(ref["period"])[0]
        reference = {"period": ref["period"], "label": label, "source": ref["source"], "expected": ref["values"], "found": got, "matches": ok}
        validation.append({"name": f"{label} matches the verification values (min ratio {ref['values'][capital.MIN_RATIO]}%, total RWA {int(ref['values'][capital.TOTAL_RWA]):,}, credit RWA {int(ref['values'][capital.CREDIT_RWA]):,} $ millions)",
                           "status": "pass" if ok else "fail", "detail": f"found {got}"})
    else:
        validation.append({"name": "Independent verification values", "status": "warn",
                           "detail": "No reference values supplied for this entity; covered by the internal consistency checks above"})
    return {"key": entity["key"], "name": entity["name"], "kind": "gse", "provider": provider,
            "metrics": [{"field": f, "label": lbl, "unit": u} for f, lbl, u in GSE_METRICS],
            "periods": rows, "reference": reference, "validation": validation}


def build_index(db=None) -> list[dict]:
    from . import gnma, fhlb, gfee, fdic
    out = []
    for e in load_entities():
        item = {"key": e["key"], "name": e["name"], "kind": e["kind"], "note": e.get("note", "")}
        if e["kind"] == "gse":
            n = len({r["period"] for r in store.rows("SELECT period FROM observations WHERE provider=?", (e["provider"],), db)})
            item.update(status="data" if n else "empty", summary=f"{n} quarterly disclosure(s)" if n else "No disclosures ingested")
        elif e["kind"] == "gnma":
            n = len(gnma.headline_series(gnma.load_figures(db)))
            item.update(status="data" if n else "empty", summary=f"{n} fiscal year(s)" if n else "No annual reports ingested")
        elif e["kind"] == "fhlb":
            s = fhlb.summary(fhlb.load_rows(db))
            item.update(status="data" if s["periods"] else "empty",
                       summary=f"{s['periods']} quarterly report(s), {s['banks']} FHLBanks ({s['first_period']}\u2013{s['last_period']})" if s["periods"] else "No Combined Financial Reports ingested")
        elif e["kind"] == "gfee":
            s = gfee.summary(gfee.load_rows(db))
            item.update(status="data" if s["years"] else "empty",
                       summary=f"{s['years']} calendar year(s), {s['reports']} report(s) ({s['first_year']}\u2013{s['last_year']})" if s["years"] else "No FHFA guarantee-fee reports ingested")
        elif e["kind"] == "fdic":
            s = fdic.summary(fdic.load_rows(db))
            item.update(status="data" if s["years"] else "empty",
                       summary=f"{s['years']} calendar year(s) ({s['first_year']}\u2013{s['last_year']})" if s["years"] else "No FDIC annual reports ingested")
        else:
            item.update(status="empty", summary="No source values loaded yet")
        out.append(item)
    return out


def build_entity(key: str, db=None) -> dict | None:
    e = next((x for x in load_entities() if x["key"] == key), None)
    if e is None:
        return None
    if e["kind"] == "gse":
        return gse_payload(e, db)
    return {"key": e["key"], "name": e["name"], "kind": e["kind"], "note": e.get("note", ""), "periods": [], "metrics": [], "validation": [], "reference": None}
