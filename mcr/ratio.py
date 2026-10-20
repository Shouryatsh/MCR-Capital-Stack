"""CET1-based leverage ratio and benchmarking. All inputs are $ millions."""
from __future__ import annotations

from . import config, store


def cet1_leverage_ratio(cet1_mm: float, ata_mm: float) -> float:
    """CET1 amount / Adjusted total assets, as a decimal (0.0134 = 1.34%). Both must be in the same unit."""
    if ata_mm is None or ata_mm <= 0:
        raise ValueError("adjusted total assets must be positive")
    return cet1_mm / ata_mm


def fmt_ratio(r: float | None, decimals: int = 2) -> str:
    """'1.34% (0.0134)' with configurable precision; the decimal form carries two more places."""
    return "—" if r is None else f"{r * 100:.{decimals}f}% ({r:.{decimals + 2}f})"


def fmt_mm(v: float | None) -> str:
    return "—" if v is None else f"{v:,.0f}"


def rank_and_percentile(ratios: dict[str, float]) -> dict[str, dict]:
    """{name: ratio} -> {name: {rank, of, percentile}}. Rank 1 = highest ratio.
    Percentile = share of the benchmark set with a ratio at or below this one (100 = highest)."""
    items = {k: v for k, v in ratios.items() if v is not None}
    order = sorted(items, key=lambda k: items[k], reverse=True)
    n = len(items)
    out = {}
    for i, k in enumerate(order, 1):
        out[k] = {"rank": i, "of": n, "percentile": 100.0 * sum(1 for v in items.values() if v <= items[k]) / n}
    return out


def latest_by_provider(period: str | None = None, db=None) -> dict[str, dict]:
    """provider -> series row for `period` (or each provider's latest period)."""
    out = {}
    for peer in config.load_peers():
        prov = peer.get("provider")
        if not prov:
            continue
        s = [r for r in store.series(prov, db) if r["ratio"] is not None]
        if period:
            s = [r for r in s if r["period"] == period]
        if s:
            out[prov] = s[-1]
    return out


def benchmark_table(period: str | None = None, db=None) -> list[dict]:
    """One row per configured benchmark slot (10), including unconfigured and no-data slots."""
    data = latest_by_provider(period, db)
    ranks = rank_and_percentile({p: d["ratio"] for p, d in data.items()})
    rows = []
    for peer in config.load_peers():
        prov = peer.get("provider")
        d = data.get(prov) if prov else None
        status = "not configured" if not prov else ("no data for this period" if not d else "ok")
        rk = ranks.get(prov, {})
        rows.append({"slot": peer["slot"], "name": peer.get("name") or "", "provider": prov or "", "status": status,
                     "period": d["period"] if d else "", "cet1_mm": d["cet1"]["value_mm"] if d else None,
                     "ata_mm": d["ata"]["value_mm"] if d else None, "ratio": d["ratio"] if d else None,
                     "rank": rk.get("rank"), "of": rk.get("of"), "percentile": rk.get("percentile"),
                     "cet1_src": d["cet1"] if d else None, "ata_src": d["ata"] if d else None,
                     "failed_checks": [k["name"] for k in d["failed"]] if d else []})
    return rows
