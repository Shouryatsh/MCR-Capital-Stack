"""Read-only JSON API for the React frontend (web/). It only exposes what the Streamlit app already computes:
store / ratio / gnma are called unchanged, so every number, check and provenance record is identical in both UIs.

Run: python scripts/serve_web.py   (serves /api and, when web/dist exists, the built frontend)
"""
from __future__ import annotations

import hmac
import logging
import os
import threading
from decimal import Decimal
from pathlib import Path

from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import benchmarks, config, fdic, fhlb, gnma, gfee, source_values, store
from .ratio import benchmark_table

log = logging.getLogger("mcr.api")
DIST = config.ROOT / "web" / "dist"
UNITS = "$ millions"
PROV_KEYS = ("source_file", "table_name", "row_identifier", "field_label", "raw_value", "parsed_value", "units_detected",
             "units_source", "value_mm", "location", "column_name", "source_url", "ingested_at")


def require_token(x_mcr_token: str | None = Header(default=None)) -> None:
    """Same placeholder gate as the Streamlit app: set MCR_TOKEN to require it; unset = open (local use)."""
    token = os.environ.get("MCR_TOKEN")
    if token and not (x_mcr_token and hmac.compare_digest(x_mcr_token, token)):
        raise HTTPException(401, "access token required")


router = APIRouter(prefix="/api", dependencies=[Depends(require_token)])


def prov(o: dict | None) -> dict | None:
    return {k: o.get(k) for k in PROV_KEYS} if o else None


def last_updated() -> str | None:
    stamps = [r["t"] for r in store.rows("SELECT MAX(ingested_at) AS t FROM observations")
              + store.rows("SELECT MAX(ingested_at) AS t FROM gnma_exposure") if r["t"]]
    return max(stamps) if stamps else None


# ------------------------------------------------------------------ meta
@router.get("/meta")
def meta():
    s = config.load_settings()
    return {"app_name": config.APP_NAME, "units": UNITS, "ratio_decimals": int(s["ratio_decimals"]),
            "primary_provider": s["primary_provider"], "last_updated": last_updated(),
            "has_cet1": bool(store.rows("SELECT 1 FROM observations LIMIT 1")),
            "has_gnma": bool(store.rows("SELECT 1 FROM gnma_exposure LIMIT 1")),
            "periods": sorted({r["period"] for r in store.rows("SELECT DISTINCT period FROM observations")}, reverse=True)}


# ------------------------------------------------------------------ peers (Overview + Summary pages)
@router.get("/peers")
def peers(period: str | None = None):
    periods = sorted({r["period"] for r in store.rows("SELECT DISTINCT period FROM observations")}, reverse=True)
    if not periods:
        return {"periods": [], "period": None, "rows": [], "stats": None}
    if period is None:
        period = periods[0]
    elif period not in periods:
        raise HTTPException(404, f"no data for period {period}")
    settings = config.load_settings()
    rows = []
    for r in benchmark_table(period):
        rows.append({k: r[k] for k in ("slot", "name", "provider", "status", "period", "cet1_mm", "ata_mm", "ratio", "rank", "of",
                                       "percentile", "failed_checks")}
                    | {"cet1_src": prov(r["cet1_src"]), "ata_src": prov(r["ata_src"])})
    have = [r for r in rows if r["ratio"] is not None]
    stats = None
    if have:
        top, bot = max(have, key=lambda r: r["ratio"]), min(have, key=lambda r: r["ratio"])
        primary = next((r for r in have if r["provider"] == settings["primary_provider"]), None)
        stats = {"have": len(have), "slots": len(rows), "top": top["name"], "top_ratio": top["ratio"], "bottom": bot["name"],
                 "bottom_ratio": bot["ratio"], "average": sum(r["ratio"] for r in have) / len(have),
                 "primary": primary["name"] if primary else None, "primary_rank": primary["rank"] if primary else None,
                 "primary_of": primary["of"] if primary else None,
                 "primary_percentile": primary["percentile"] if primary else None}
    return {"periods": periods, "period": period, "rows": rows, "stats": stats}


# ------------------------------------------------------------------ entities (Benchmark page)
@router.get("/entities")
def entities():
    provs = [r["provider"] for r in store.rows("SELECT DISTINCT provider FROM observations ORDER BY provider")]
    primary = config.load_settings()["primary_provider"]
    return {"providers": provs, "primary": primary if primary in provs else (provs[0] if provs else None)}


@router.get("/entities/{provider}/series")
def entity_series(provider: str):
    ser = [r for r in store.series(provider) if r["ratio"] is not None]
    if not ser:
        raise HTTPException(404, f"{provider} has no complete period (both CET1 and adjusted total assets)")
    out = []
    for r in ser:
        prev = out[-1] if out else None
        out.append({"period": r["period"], "ratio": r["ratio"], "cet1_mm": r["cet1"]["value_mm"], "ata_mm": r["ata"]["value_mm"],
                    "cet1": prov(r["cet1"]), "ata": prov(r["ata"]),
                    "checks": [{"name": k["name"], "status": k["status"], "detail": k["detail"]} for k in r["checks"]],
                    "failed": [k["name"] for k in r["failed"]],
                    "ratio_change": None if prev is None else r["ratio"] - prev["ratio"],
                    "previous_period": None if prev is None else prev["period"]})
    return {"provider": provider, "series": out}


# ------------------------------------------------------------------ GNMA
def _pct(diff: int, base: int) -> float | None:
    return float((Decimal(diff) / Decimal(base) * 100).quantize(Decimal("0.0001"))) if base else None


def _fig(f: gnma.Figure) -> dict:
    d = gnma.figure_dict(f)
    d.update(ok=f.ok, mbs_usd_text=gnma.fmt_usd(f.mbs_usd), commitments_usd_text=gnma.fmt_usd(f.commitments_usd),
             total_usd_text=gnma.fmt_usd(f.total_usd), total_published=f.as_published_total(),
             mbs_published=f.published(f.mbs_usd), commitments_published=f.published(f.commitments_usd))
    return d


@router.get("/gnma")
def gnma_data():
    figs = gnma.load_figures()
    series = gnma.headline_series(figs)
    by_year = {f.fiscal_year: f for f in series}
    rows = []
    for f in series:
        d = _fig(f)
        prev = by_year.get(f.fiscal_year - 1)
        d["yoy"] = None if prev is None else {
            "prior_fiscal_year": prev.fiscal_year,
            "total_abs_usd": f.total_usd - prev.total_usd, "total_pct": _pct(f.total_usd - prev.total_usd, prev.total_usd),
            "mbs_abs_usd": f.mbs_usd - prev.mbs_usd, "mbs_pct": _pct(f.mbs_usd - prev.mbs_usd, prev.mbs_usd),
            "commitments_abs_usd": f.commitments_usd - prev.commitments_usd,
            "commitments_pct": _pct(f.commitments_usd - prev.commitments_usd, prev.commitments_usd),
            "rounded": max(f.precision_usd, prev.precision_usd) > 1_000}
        d["latest"] = f is series[-1]
        rows.append(d)
    return {
        "source": {"index_url": gnma.INDEX_URL, "provider": gnma.PROVIDER},
        "series": rows,
        "observations": [_fig(f) for f in figs],
        "validation": gnma.validate(figs) if figs else [],
        "reconciliation": gnma.reconcile(figs),
        "gaps": gnma.load_gaps(),
        "reference": {str(fy): {k: v * 1000 for k, v in ref.items()} for fy, ref in gnma.REFERENCE_TOTALS.items()},
    }


_refresh = {"running": False, "started": None, "finished": None, "reports": 0, "with_figures": 0, "error": None}
_refresh_lock = threading.Lock()


def _run_refresh() -> None:
    try:
        results = gnma.ingest_all()
        _refresh.update(reports=len(results), with_figures=sum(1 for r in results if r.figures), error=None)
    except Exception as e:  # surfaced to the UI instead of failing silently
        log.exception("GNMA refresh failed")
        _refresh["error"] = str(e)
    finally:
        _refresh.update(running=False, finished=store.now())


@router.post("/gnma/refresh", status_code=202)
def gnma_refresh():
    with _refresh_lock:
        if _refresh["running"]:
            return JSONResponse(_refresh, status_code=409)
        _refresh.update(running=True, started=store.now(), finished=None, error=None)
    threading.Thread(target=_run_refresh, daemon=True).start()
    return _refresh


@router.get("/gnma/refresh")
def gnma_refresh_status():
    return _refresh


def _fhlb_cell(o: dict) -> dict:
    text = f"{o['parsed_value']:,.2f}%" if o["unit"] == "percent" else f"{o['parsed_value']:,.0f}"
    return {"value": o["parsed_value"], "text": text, "unit": o["unit"], "raw_value": o["raw_value"],
            "source_file": o["source_file"], "source_url": o["source_url"] or "", "table_name": o["table_name"],
            "location": o["location"]}


def _derived_cell(field: str, unit: str, value: float, **extra) -> dict:
    text = f"{value:,.2f}%" if unit == "percent" else f"{value:,.0f}"
    return {"value": value, "text": text, "unit": unit, "derived": True, **extra}


@router.get("/fhlb")
def fhlb_data():
    rows = fhlb.load_rows()
    periods: dict[str, dict] = {}
    for o in rows:
        p = periods.setdefault(o["period"], {"period": o["period"], "report_date": o["report_date"], "banks": {}, "derived_banks": []})
        p["banks"].setdefault(o["fhlbank"], {})[o["field"]] = _fhlb_cell(o)
    ordered = [periods[p] for p in sorted(periods, key=fhlb.period_sort_key)]
    units = {f: u for f, _, u, _ in fhlb.FIELDS} | {f: u for f, _, u, _ in fhlb.DERIVED_FIELDS}
    for p in ordered:
        label, end = source_values.period_info(p["period"])
        p["label"], p["period_end"] = label, end
        if "Combined" not in p["banks"]:  # not published for this period: sum the 11 FHLBanks and mark the row as derived
            values = {b: {f: c["value"] for f, c in cells.items()} for b, cells in p["banks"].items()}
            combined = fhlb.derive_combined(values)
            if combined:
                p["banks"]["Combined"] = {f: _derived_cell(f, units[f], v, source_note="Sum of the 11 FHLBanks") for f, v in combined.items()}
                p["derived_banks"].append("Combined")
        for bank, cells in p["banks"].items():
            for field, value in fhlb.derive({f: c["value"] for f, c in cells.items()}).items():
                cells[field] = _derived_cell(field, units[field], value)
    return {
        "source": {"index_url": fhlb.INDEX_URL, "provider": fhlb.PROVIDER},
        "banks": fhlb.BANKS + ["Combined"],
        "fields": [{"field": f, "label": lbl, "unit": u, "table": t} for f, lbl, u, t in fhlb.FIELDS]
                  + [{"field": f, "label": lbl, "unit": u, "table": "Derived", "derived": True, "formula": fm}
                     for f, lbl, u, fm in fhlb.DERIVED_FIELDS],
        "periods": ordered,
        "gaps": fhlb.load_gaps(),
        "validation": fhlb.validate(rows) if rows else [],
    }


def _gfee_point(o: dict) -> dict:
    return {"report_key": o["report_key"], "report_title": o["report_title"], "source_url": o["source_url"],
            "total_bps": o["total_bps"], "ongoing_bps": o["ongoing_bps"], "upfront_bps": o["upfront_bps"],
            "gap_bps": o["gap_bps"], "quote": o["quote"], "restated_from": o["restated_from"],
            "restated_note": o["restated_note"]}


@router.get("/gfee")
def gfee_data():
    rows = gfee.load_rows()
    series = [{"data_year": s["data_year"], "population": s["population"],
               "primary": _gfee_point(s["primary"]), "restatements": [_gfee_point(o) for o in s["restatements"]]}
              for s in gfee.headline_series(rows)]
    return {
        "source": {"index_url": gfee.INDEX_URL, "provider": gfee.PROVIDER},
        "years": series,
        "gaps": gfee.load_gaps(),
        "validation": gfee.validate(rows) if rows else [],
        "summary": gfee.summary(rows),
    }


def _fdic_point(o: dict) -> dict:
    return {"report_key": o["report_key"], "report_title": o["report_title"], "source_url": o["source_url"],
            "fund_balance_ending": o["fund_balance_ending"], "fund_balance_prior": o["fund_balance_prior"],
            "fund_balance_quote": o["fund_balance_quote"], "min_reserve_ratio_pct": o["min_reserve_ratio_pct"],
            "min_reserve_ratio_quote": o["min_reserve_ratio_quote"],
            "insured_deposits_trillions": o["insured_deposits_trillions"],
            "insured_deposits_as_of": o["insured_deposits_as_of"],
            "insured_deposits_quote": o["insured_deposits_quote"]}


@router.get("/fdic")
def fdic_data():
    rows = fdic.load_rows()
    return {
        "source": {"index_url": fdic.INDEX_URL, "provider": fdic.PROVIDER},
        "years": [_fdic_point(r) for r in rows],
        "gaps": fdic.load_gaps(),
        "validation": fdic.validate(rows) if rows else [],
        "summary": fdic.summary(rows),
    }


# ------------------------------------------------------------------ source values (per-entity as-published figures)
@router.get("/source-values")
def source_values_index():
    return {"entities": source_values.build_index()}


@router.get("/source-values/{key}")
def source_values_entity(key: str):
    payload = source_values.build_entity(key)
    if payload is None:
        raise HTTPException(404, f"unknown entity {key!r}")
    return payload


# ------------------------------------------------------------------ benchmark calculations
class AssumptionEdit(BaseModel):
    value: str | int | float


@router.get("/benchmarks")
def benchmarks_data():
    return benchmarks.build_payload()


@router.put("/benchmarks/{number}/assumptions/{name}")
def benchmarks_set_assumption(number: int, name: str, body: AssumptionEdit):
    """Validate, save and immediately recalculate. Rejected values change nothing."""
    try:
        benchmarks.set_assumption(number, name, body.value)
    except KeyError as e:
        raise HTTPException(404, str(e).strip("'\"")) from None
    except ValueError as e:
        raise HTTPException(422, str(e)) from None
    return benchmarks.build_payload()


@router.delete("/benchmarks/{number}/assumptions/{name}")
def benchmarks_reset_assumption(number: int, name: str):
    try:
        benchmarks.reset_assumption(number, name)
    except (KeyError, ValueError) as e:
        raise HTTPException(422, str(e).strip("'\"")) from None
    return benchmarks.build_payload()


# ------------------------------------------------------------------ data sources
@router.get("/sources")
def sources():
    obs = [{k: o[k] for k in ("provider", "period", "field", "source_file", "table_name", "field_label", "column_name", "location",
                              "raw_value", "units_detected", "units_source", "value_mm", "source_url", "ingested_at")}
           for o in store.get_observations()]
    return {"observations": obs,
            "fetch_log": store.rows("SELECT ts,url,status,detail FROM fetch_log ORDER BY id DESC LIMIT 100"),
            "ingest_log": store.rows("SELECT ts,file,provider,period,status,detail FROM ingest_log ORDER BY id DESC LIMIT 100")}


# ------------------------------------------------------------------ app
def create_app(dist: Path | None = None) -> FastAPI:
    app = FastAPI(title=f"{config.APP_NAME} API", docs_url="/api/docs", openapi_url="/api/openapi.json")
    app.include_router(router)

    @app.get("/api/health")
    def health():
        return {"status": "ok", "auth_required": bool(os.environ.get("MCR_TOKEN"))}

    dist = DIST if dist is None else dist
    if (dist / "index.html").exists():
        if (dist / "assets").exists():
            app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str):
            if path.startswith("api/"):
                raise HTTPException(404)
            f = (dist / path).resolve()
            target = f if f.is_file() and dist.resolve() in f.parents else dist / "index.html"
            # index.html names the hashed bundles, so it must always be revalidated or a rebuild would not reach users
            return FileResponse(target, headers={"Cache-Control": "no-cache"} if target.name == "index.html" else None)
    return app


app = create_app()
