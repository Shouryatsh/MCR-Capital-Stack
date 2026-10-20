"""Scheduled fetch job (cron / Task Scheduler): pulls the newest Freddie Mac and Fannie Mae disclosures.

  python scripts/fetch.py            # newest Freddie Mac PDF + any new Fannie Mae periods
  python scripts/fetch.py --all      # every period listed on both sites (backfill)
  python scripts/fetch.py --ginnie   # GNMA Maximum Exposure to Loss: download + extract every English annual report

Exit code is 1 if any file failed to download or parse, so the scheduler can alert.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mcr import capital, config, fannie, fdic, fhlb, freddie, gfee, gnma  # noqa: E402


def run_fhlb() -> int:
    """Re-read the local FHLB Combined Financial Report PDFs (raw/fhlb/*.pdf), downloading any missing periods first."""
    results = fhlb.ingest_all(fetch=True)
    for r in results:
        n_banks = len({o.fhlbank for o in r.observations})
        print(f"{r.period:7} {r.report_date or '—':24} {n_banks:2} bank(s)/entities  {'; '.join(r.gaps) if r.gaps else 'OK'}")
    rows = fhlb.load_rows()
    checks = fhlb.validate(rows)
    for c in checks:
        print(f"{c['status'].upper():5} {c['name']}: {c['detail']}")
    return 1 if any(c["status"] == "fail" for c in checks) else 0


def run_ginnie() -> int:
    results = gnma.ingest_all()
    for r in results:
        for f in r.figures:
            print(f"FY{f.fiscal_year} {f.role:11} {f.source_report:20} {f.as_published_total():38} pdf p.{f.pdf_page} {'; '.join(x for x in f.flags if x.startswith(('FAIL', 'WARN')))}")
        for g in r.gaps:
            print(f"FY{r.fiscal_year} {'gap':11} {r.source_report:20} {g}")
    figs = gnma.load_figures()
    checks = gnma.validate(figs)
    for c in checks:
        print(f"{c['status'].upper():5} {c['name']}: {c['detail']}")
    return 1 if any(c["status"] == "fail" for c in checks) else 0


def run_gfee() -> int:
    """Re-read the local FHFA Single-Family Guarantee Fees report PDFs (raw/gfee/*.pdf), downloading any missing ones first."""
    results = gfee.ingest_all(fetch=True)
    for r in results:
        print(f"{r.report_key:12} {r.title:70} {len(r.points)} data point(s)")
    rows = gfee.load_rows()
    gaps = gfee.load_gaps()
    for g in gaps:
        print(f"GAP   {g['report_key']}: {g['reason']}")
    checks = gfee.validate(rows)
    for c in checks:
        print(f"{c['status'].upper():5} {c['name']}: {c['detail']}")
    return 1 if any(c["status"] == "fail" for c in checks) else 0


def run_fdic() -> int:
    """Re-read the local FDIC Annual Report Financial Section PDFs (raw/fdic/*.pdf), downloading any missing ones first."""
    results = fdic.ingest_all(fetch=True)
    for r in results:
        n = sum(1 for v in (r.point and [r.point.fund_balance_ending, r.point.min_reserve_ratio_pct, r.point.insured_deposits_trillions] or []) if v is not None)
        print(f"{r.report_key:7} {r.title:55} {n}/3 metric(s)")
    rows = fdic.load_rows()
    gaps = fdic.load_gaps()
    for g in gaps:
        print(f"GAP   {g['report_key']}: {g['reason']}")
    checks = fdic.validate(rows)
    for c in checks:
        print(f"{c['status'].upper():5} {c['name']}: {c['detail']}")
    return 1 if any(c["status"] == "fail" for c in checks) else 0


def run_capital() -> int:
    """Re-read the local Fannie Mae / Freddie Mac PDFs for minimum capital ratio, total RWA and credit RWA (no downloads)."""
    results = capital.backfill(config.RAW_DIR)
    for r in results:
        m = r.metrics
        print(f"{r.provider:12} {r.period:7} min ratio {m['min_capital_ratio'].value if 'min_capital_ratio' in m else '—':>5}%  "
              f"total RWA {m['total_rwa'].value if 'total_rwa' in m else '—':>9}  credit RWA {m['credit_rwa'].value if 'credit_rwa' in m else '—':>9}  "
              f"{'OK' if r.ok else 'CHECKS FAILED: ' + '; '.join(c.name for c in r.checks if c.status == 'fail')}")
    print(f"{len(results)} disclosure(s) processed ($ millions)")
    return 0 if all(r.ok for r in results) else 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--ginnie", action="store_true", help="fetch + extract GNMA annual reports instead of the GSE disclosures")
    ap.add_argument("--capital", action="store_true", help="re-read local GSE PDFs for minimum capital ratio, total RWA and credit RWA")
    ap.add_argument("--fhlb", action="store_true", help="fetch + extract the FHLBanks Office of Finance Combined Financial Reports (Table 9.1/9.2)")
    ap.add_argument("--gfee", action="store_true", help="fetch + extract the FHFA Single-Family Guarantee Fees reports (Total Average Guarantee Fee, annual)")
    ap.add_argument("--fdic", action="store_true", help="fetch + extract the FDIC Annual Report Financial Section PDFs (Fund Balance, Minimum Reserve Ratio, Estimated Insured Deposits)")
    a = ap.parse_args()
    config.setup_logging()
    if a.ginnie:
        sys.exit(run_ginnie())
    if a.capital:
        sys.exit(run_capital())
    if a.fhlb:
        sys.exit(run_fhlb())
    if a.gfee:
        sys.exit(run_gfee())
    if a.fdic:
        sys.exit(run_fdic())
    outs = freddie.fetch_latest(all_periods=a.all) + fannie.fetch(all_periods=a.all)
    for o in outs:
        print(f"{o.status:14} {o.provider:12} {o.period:7} {o.file} {o.message}")
    print(f"{len(outs)} file(s) processed" if outs else "nothing new")
    sys.exit(1 if any(o.status != "ok" for o in outs) else 0)
