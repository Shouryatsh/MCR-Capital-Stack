"""SQLite persistence: observations (with full provenance), checks, and fetch / ingest logs."""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

from .config import DB_PATH, DATA_DIR
from .models import ATA, CET1, Check, Observation, ParseResult

SCHEMA = """
CREATE TABLE IF NOT EXISTS observations(
  provider TEXT, period TEXT, field TEXT, source_file TEXT, source_url TEXT, table_name TEXT,
  row_identifier TEXT, field_label TEXT, column_name TEXT, location TEXT, raw_value TEXT, parsed_value REAL,
  units_detected TEXT, units_source TEXT, value_mm REAL, notes TEXT, ingested_at TEXT,
  PRIMARY KEY(provider, period, field));
CREATE TABLE IF NOT EXISTS checks(provider TEXT, period TEXT, name TEXT, status TEXT, detail TEXT,
  PRIMARY KEY(provider, period, name));
CREATE TABLE IF NOT EXISTS fetch_log(id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, url TEXT, status TEXT, detail TEXT);
CREATE TABLE IF NOT EXISTS ingest_log(id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, file TEXT, provider TEXT,
  period TEXT, status TEXT, detail TEXT);
CREATE TABLE IF NOT EXISTS gnma_exposure(
  fiscal_year INTEGER, reporting_date TEXT, role TEXT, source_report TEXT, source_url TEXT, pdf_page INTEGER,
  printed_page TEXT, note TEXT, table_title TEXT, table_kind TEXT, units TEXT, mbs_raw TEXT, commitments_raw TEXT,
  total_raw TEXT, mbs_usd TEXT, commitments_usd TEXT, total_usd TEXT, reported_total_usd TEXT, precision_usd INTEGER,
  flags TEXT, ingested_at TEXT, PRIMARY KEY(fiscal_year, source_report, role));
CREATE TABLE IF NOT EXISTS gnma_gaps(fiscal_year INTEGER, source_report TEXT, reason TEXT, ingested_at TEXT,
  PRIMARY KEY(fiscal_year, source_report, reason));
CREATE TABLE IF NOT EXISTS capital_metrics(
  provider TEXT, period TEXT, field TEXT, label TEXT, value TEXT, unit TEXT, raw_value TEXT, units_detected TEXT,
  source_file TEXT, source_url TEXT, table_name TEXT, line_item TEXT, column_name TEXT, location TEXT, ingested_at TEXT,
  PRIMARY KEY(provider, period, field));
CREATE TABLE IF NOT EXISTS capital_checks(provider TEXT, period TEXT, name TEXT, status TEXT, detail TEXT,
  PRIMARY KEY(provider, period, name));
CREATE TABLE IF NOT EXISTS fhlb_capital(
  period TEXT, report_date TEXT, fhlbank TEXT, field TEXT, label TEXT, raw_value TEXT, parsed_value REAL, unit TEXT,
  source_file TEXT, source_url TEXT, table_name TEXT, location TEXT, ingested_at TEXT,
  PRIMARY KEY(period, fhlbank, field));
CREATE TABLE IF NOT EXISTS fhlb_gaps(period TEXT, reason TEXT, ingested_at TEXT, PRIMARY KEY(period, reason));
CREATE TABLE IF NOT EXISTS gfee_annual(
  report_key TEXT, report_title TEXT, source_url TEXT, data_year TEXT, population TEXT, total_bps REAL,
  ongoing_bps REAL, upfront_bps REAL, gap_bps REAL, quote TEXT, restated_from REAL, restated_note TEXT,
  ingested_at TEXT, PRIMARY KEY(report_key, data_year, population));
CREATE TABLE IF NOT EXISTS gfee_gaps(report_key TEXT, reason TEXT, ingested_at TEXT, PRIMARY KEY(report_key, reason));
CREATE TABLE IF NOT EXISTS fdic_annual(
  report_key TEXT, report_title TEXT, source_url TEXT, fund_balance_ending INTEGER, fund_balance_prior INTEGER,
  fund_balance_quote TEXT, min_reserve_ratio_pct REAL, min_reserve_ratio_quote TEXT, insured_deposits_trillions REAL,
  insured_deposits_as_of TEXT, insured_deposits_quote TEXT, ingested_at TEXT, PRIMARY KEY(report_key));
CREATE TABLE IF NOT EXISTS fdic_gaps(report_key TEXT, reason TEXT, ingested_at TEXT, PRIMARY KEY(report_key, reason));
"""


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@contextmanager
def conn(path=None):
    DATA_DIR.mkdir(exist_ok=True)
    c = sqlite3.connect(path or DB_PATH)
    c.row_factory = sqlite3.Row
    c.executescript(SCHEMA)
    try:
        yield c
        c.commit()
    finally:
        c.close()


def save_result(res: ParseResult, path=None) -> None:
    with conn(path) as c:
        for o in res.observations.values():
            c.execute("INSERT OR REPLACE INTO observations VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                      (o.provider, o.period, o.field, o.source_file, o.source_url, o.table_name, o.row_identifier,
                       o.field_label, o.column_name, o.location, o.raw_value, o.parsed_value, o.units_detected,
                       o.units_source, o.value_mm, json.dumps(o.notes), now()))
        c.execute("DELETE FROM checks WHERE provider=? AND period=?", (res.provider, res.period))
        for k in res.checks:
            c.execute("INSERT INTO checks VALUES(?,?,?,?,?)", (res.provider, res.period, k.name, k.status, k.detail))


def save_gnma(res, path=None) -> None:
    """Replace everything stored for one GNMA annual report (figures and gaps). Money is kept as exact integer text."""
    with conn(path) as c:
        c.execute("DELETE FROM gnma_exposure WHERE source_report=?", (res.source_report,))
        c.execute("DELETE FROM gnma_gaps WHERE source_report=?", (res.source_report,))
        for f in res.figures:
            c.execute("INSERT OR REPLACE INTO gnma_exposure VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                      (f.fiscal_year, f.reporting_date, f.role, f.source_report, f.source_url, f.pdf_page, f.printed_page, f.note,
                       f.table_title, f.table_kind, f.units, f.mbs_raw, f.commitments_raw, f.total_raw, str(f.mbs_usd),
                       str(f.commitments_usd), str(f.total_usd),
                       None if f.reported_total_usd is None else str(f.reported_total_usd), f.precision_usd,
                       json.dumps(f.flags), now()))
        for reason in res.gaps:
            c.execute("INSERT OR REPLACE INTO gnma_gaps VALUES(?,?,?,?)", (res.fiscal_year, res.source_report, reason, now()))


def save_capital(res, path=None) -> None:
    """Replace the stored capital metrics and checks for one provider/period. Values are exact decimal text."""
    with conn(path) as c:
        c.execute("DELETE FROM capital_metrics WHERE provider=? AND period=?", (res.provider, res.period))
        c.execute("DELETE FROM capital_checks WHERE provider=? AND period=?", (res.provider, res.period))
        for m in res.metrics.values():
            c.execute("INSERT INTO capital_metrics VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                      (res.provider, res.period, m.field, m.label, m.value, m.unit, m.raw_value, m.units_detected, m.source_file,
                       m.source_url, m.table_name, m.line_item, m.column_name, m.location, now()))
        for k in res.checks:
            c.execute("INSERT INTO capital_checks VALUES(?,?,?,?,?)", (res.provider, res.period, k.name, k.status, k.detail))


def save_fhlb(period: str, res, path=None) -> None:
    """Replace everything stored for one FHLB CFR period (per-bank observations and gaps)."""
    with conn(path) as c:
        c.execute("DELETE FROM fhlb_capital WHERE period=?", (period,))
        c.execute("DELETE FROM fhlb_gaps WHERE period=?", (period,))
        for o in res.observations:
            c.execute("INSERT OR REPLACE INTO fhlb_capital VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                      (o.period, o.report_date, o.fhlbank, o.field, o.label, o.raw_value, o.parsed_value, o.unit,
                       o.source_file, o.source_url, o.table_name, o.location, now()))
        for reason in res.gaps:
            c.execute("INSERT OR REPLACE INTO fhlb_gaps VALUES(?,?,?)", (period, reason, now()))


def save_gfee(report_key: str, source_url: str, res, gaps: list[str], path=None) -> None:
    """Replace everything stored for one FHFA guarantee-fee report (its data points and gaps)."""
    with conn(path) as c:
        c.execute("DELETE FROM gfee_annual WHERE report_key=?", (report_key,))
        c.execute("DELETE FROM gfee_gaps WHERE report_key=?", (report_key,))
        for dp in res.points:
            c.execute("INSERT OR REPLACE INTO gfee_annual VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                      (report_key, res.title, source_url, dp.data_year, dp.population, dp.total_bps, dp.ongoing_bps,
                       dp.upfront_bps, dp.gap_bps, dp.quote, dp.restated_from, dp.restated_note, now()))
        for reason in gaps:
            c.execute("INSERT OR REPLACE INTO gfee_gaps VALUES(?,?,?)", (report_key, reason, now()))


def save_fdic(report_key: str, source_url: str, res, gaps: list[str], path=None) -> None:
    """Replace everything stored for one FDIC annual report (its one data point and gaps)."""
    with conn(path) as c:
        c.execute("DELETE FROM fdic_annual WHERE report_key=?", (report_key,))
        c.execute("DELETE FROM fdic_gaps WHERE report_key=?", (report_key,))
        dp = res.point
        if dp is not None:
            c.execute("INSERT OR REPLACE INTO fdic_annual VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                      (report_key, res.title, source_url, dp.fund_balance_ending, dp.fund_balance_prior,
                       dp.fund_balance_quote, dp.min_reserve_ratio_pct, dp.min_reserve_ratio_quote,
                       dp.insured_deposits_trillions, dp.insured_deposits_as_of, dp.insured_deposits_quote, now()))
        for reason in gaps:
            c.execute("INSERT OR REPLACE INTO fdic_gaps VALUES(?,?,?)", (report_key, reason, now()))


def log_ingest(file, provider, period, status, detail="", path=None) -> None:
    with conn(path) as c:
        c.execute("INSERT INTO ingest_log(ts,file,provider,period,status,detail) VALUES(?,?,?,?,?,?)",
                  (now(), file, provider, period, status, detail))


def log_fetch(url, status, detail="", path=None) -> None:
    with conn(path) as c:
        c.execute("INSERT INTO fetch_log(ts,url,status,detail) VALUES(?,?,?,?)", (now(), url, status, detail))


def rows(sql: str, args=(), path=None) -> list[dict]:
    with conn(path) as c:
        return [dict(r) for r in c.execute(sql, args)]


def get_observations(provider=None, path=None) -> list[dict]:
    q, a = "SELECT * FROM observations", ()
    if provider:
        q, a = q + " WHERE provider=?", (provider,)
    return rows(q + " ORDER BY provider, period, field", a, path)


def series(provider: str, path=None) -> list[dict]:
    """One dict per period with both canonical values, the ratio and the check status."""
    obs = get_observations(provider, path)
    by: dict = {}
    for o in obs:
        by.setdefault(o["period"], {})[o["field"]] = o
    chk = {}
    for k in rows("SELECT * FROM checks WHERE provider=?", (provider,), path):
        chk.setdefault(k["period"], []).append(k)
    out = []
    for period in sorted(by):
        d = by[period]
        cet1, ata = d.get(CET1), d.get(ATA)
        ratio = cet1["value_mm"] / ata["value_mm"] if cet1 and ata and ata["value_mm"] else None
        failed = [k for k in chk.get(period, []) if k["status"] != "pass"]
        out.append({"provider": provider, "period": period, "cet1": cet1, "ata": ata, "ratio": ratio,
                    "checks": chk.get(period, []), "failed": failed})
    return out
