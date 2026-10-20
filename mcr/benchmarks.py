"""GNMA-adjusted benchmark calculation engine (all business calculation lives here; the UI only displays results).

Unit pipeline (one conversion point per stage, so nothing can be converted twice):
  1. SOURCE   values are kept as published (GNMA: USD thousands / billions; CET1, assets: $ millions / billions) together
              with their unit metadata.
  2. INPUT    each source value is converted ONCE to exact whole US dollars (Decimal): `gnma.to_usd`.
  3. CALC     every formula runs on USD Decimals at full precision (no intermediate rounding).
  4. DISPLAY  the final USD result is divided by 1,000,000,000 ONCE (`usd_to_billions`) and rounded only for the text shown.

Benchmarks are defined in config/benchmarks.json (created from DEFAULT_BENCHMARKS): a formula over named inputs,
assumptions and other benchmarks (`benchmark_<n>`). Only Benchmarks 1-5 have business-confirmed definitions. Benchmarks 6-10 are
shipped as "unconfirmed": they produce no number until a formula is supplied, so nothing is invented.
"""
from __future__ import annotations

import ast
import hashlib
import json
import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, localcontext
from graphlib import CycleError, TopologicalSorter

from . import config, fhlb, gnma, store
from .models import ATA, CET1

BILLION = Decimal(10) ** 9
THOUSAND = Decimal(1000)
PREC = 60
DISPLAY_DECIMALS = 2
Q3_END = "09-30"  # GNMA fiscal years end on Sept 30, which is the calendar-Q3 quarter end of the GSE disclosures

GNMA_INPUTS = {
    "gnma_total_exposure": "GNMA Total Maximum Exposure to Loss",
    "gnma_outstanding_mbs": "GNMA Outstanding MBS",
    "gnma_outstanding_mbs_commitments": "GNMA Outstanding MBS Commitments",
}
_KNOWN_INPUT = re.compile(r"^(?:gnma_total_exposure|gnma_outstanding_mbs|gnma_outstanding_mbs_commitments|(?:cet1|ata|fhlb)_[a-z0-9_]+)$")
_BENCH_REF = re.compile(r"^benchmark_(\d+)$")

PENDING = "Formula and assumptions have not been established. Supply them in config/benchmarks.json (status \"confirmed\") after business sign-off."
DEFAULT_BENCHMARKS: list[dict] = [
    {"number": 1, "key": "leverage_cet1_gses", "name": "Leverage based CET1 (GSEs)", "status": "confirmed",
     "description": "GNMA Total Maximum Exposure to Loss multiplied by the 1% leverage-based CET1 adjustment.",
     "formula": "gnma_total_exposure * adjustment_pct",
     "assumptions": {"adjustment_pct": "0.01"},
     "assumption_meta": {"adjustment_pct": {"label": "Adjustment percentage", "unit": "fraction (0.01 = 1%)", "min": "0", "max": "1", "min_exclusive": True}},
     "reference": "Business specification: Leverage based CET1 (GSEs) = GNMA Total Maximum Exposure to Loss × 1%."},
    {"number": 2, "key": "risk_based_cet1_gses", "name": "GSE Risk Based Capital", "status": "confirmed",
     "description": "GNMA Total Maximum Exposure to Loss multiplied by the 17% risk weight and the 4.5% minimum CET1 capital ratio required of Fannie Mae and Freddie Mac.",
     "formula": "gnma_total_exposure * risk_weight_pct * minimum_cet1_ratio_pct",
     "assumptions": {"risk_weight_pct": "0.17", "minimum_cet1_ratio_pct": "0.045"},
     "assumption_meta": {
         "risk_weight_pct": {"label": "Risk weight", "unit": "fraction (0.17 = 17%)", "min": "0", "max": "1", "min_exclusive": True},
         "minimum_cet1_ratio_pct": {"label": "Minimum CET1 capital ratio", "unit": "fraction (0.045 = 4.5%)", "min": "0", "max": "1", "min_exclusive": True},
     },
     "reference": "Business specification: GSE Risk Based Capital = GNMA Total Maximum Exposure to Loss × 17% risk weight × 4.5% minimum CET1 capital ratio (Fannie Mae/Freddie Mac)."},
    {"number": 3, "key": "fhlb_min_capital_gnma", "name": "FHLB Minimum Regulatory Capital (GNMA)", "status": "confirmed",
     "description": "GNMA Total Maximum Exposure to Loss multiplied by the 17% credit risk density and the FHLBs' regulatory capital ratio, minimum requirement.",
     "formula": "gnma_total_exposure * credit_risk_density_pct * fhlb_regulatory_capital_min_ratio",
     "assumptions": {"credit_risk_density_pct": "0.17"},
     "assumption_meta": {"credit_risk_density_pct": {"label": "Credit risk density", "unit": "fraction (0.17 = 17%)", "min": "0", "max": "1", "min_exclusive": True}},
     "reference": "Business specification: Benchmark 3 = GNMA Total Maximum Exposure to Loss × 17% credit risk density × FHLBs regulatory capital ratio, minimum requirement."},
    {"number": 4, "key": "fha_min_capital_gnma", "name": "FHA Minimum Capital Requirement", "status": "confirmed",
     "description": "GNMA Total Maximum Exposure to Loss multiplied by the 25% GNMA position in line (4th in the loss hierarchy) if losses occur and the 2% FHA minimum capital requirement.",
     "formula": "gnma_total_exposure * position_in_line_pct * fha_min_capital_pct",
     "assumptions": {"position_in_line_pct": "0.25", "fha_min_capital_pct": "0.02"},
     "assumption_meta": {
         "position_in_line_pct": {"label": "GNMA position in line (4th in loss hierarchy) if losses occur", "unit": "fraction (0.25 = 25%)", "min": "0", "max": "1", "min_exclusive": True},
         "fha_min_capital_pct": {"label": "FHA minimum capital requirement", "unit": "fraction (0.02 = 2%)", "min": "0", "max": "1", "min_exclusive": True},
     },
     "reference": "Business specification: Benchmark 4 = GNMA Total Maximum Exposure to Loss × 25% GNMA position in line (4th in the loss hierarchy) if losses occur × 2% FHA minimum capital requirement."},
] + [
    {"number": 5, "key": "fhlb_actual_rbc_gnma", "name": "FHLB Actual Risk Based Capital (GNMA)", "status": "confirmed",
     "description": "GNMA Total Maximum Exposure to Loss multiplied by the 17% credit risk density and the FHLBs' Actual Risk Based Capital Ratio (derived) of the Combined row.",
     "formula": "gnma_total_exposure * credit_risk_density_pct * fhlb_combined_actual_rbc_ratio",
     "assumptions": {"credit_risk_density_pct": "0.17"},
     "assumption_meta": {"credit_risk_density_pct": {"label": "Credit risk density", "unit": "fraction (0.17 = 17%)", "min": "0", "max": "1", "min_exclusive": True}},
     "reference": "Business specification: Benchmark 5 = GNMA Total Maximum Exposure to Loss × 17% credit risk density × FHLBs Actual Risk Based Capital Ratio (derived), Combined row."},
] + [
    {"number": n, "key": f"benchmark_{n}", "name": f"Benchmark {n} (definition required)", "status": "unconfirmed", "description": PENDING,
     "formula": None, "assumptions": {}, "assumption_meta": {}, "reference": "No definition supplied; requires business confirmation."}
    for n in range(6, 11)
]


class FormulaError(ValueError):
    pass


# ------------------------------------------------------------------ formatting (display stage only)
def plain(d: Decimal) -> str:
    """Exact decimal text without exponent or trailing zeros."""
    s = format(d, "f")
    return s.rstrip("0").rstrip(".") if "." in s else s


def commas(d: Decimal) -> str:
    s = format(d, ",f")
    return s.rstrip("0").rstrip(".") if "." in s else s


def usd_to_billions(usd: Decimal) -> Decimal:
    """THE single USD -> billions conversion. Exact (Decimal division by 1e9); callers must not convert again."""
    with localcontext() as c:
        c.prec = PREC
        return usd / BILLION


def fmt_billions(usd: Decimal | None, decimals: int = DISPLAY_DECIMALS) -> str:
    """'$26.14B' for 26,136,236,510 USD. Rounds only the text; never the stored value."""
    if usd is None:
        return "—"
    with localcontext() as c:
        c.prec = PREC
        q = usd_to_billions(usd).quantize(Decimal(1).scaleb(-decimals), ROUND_HALF_UP)
    return f"{'−' if q < 0 else ''}${format(abs(q), f',.{decimals}f')}B"


def fmt_thousands(usd: Decimal) -> str:
    """The same amount in USD thousands as GNMA prints it (reconciliation with the annual report)."""
    with localcontext() as c:
        c.prec = PREC
        return f"${format(usd / THOUSAND, ',.2f')}"


# ------------------------------------------------------------------ formula language (+ - * / parentheses, names, numbers)
def parse_formula(src: str) -> ast.Expression:
    src = src.strip()
    try:
        tree = ast.parse(src, mode="eval")
    except SyntaxError as e:
        raise FormulaError(f"invalid formula {src!r}: {e.msg}") from None
    ok = (ast.Expression, ast.Name, ast.Load, ast.BinOp, ast.UnaryOp, ast.Add, ast.Sub, ast.Mult, ast.Div, ast.USub, ast.UAdd)
    for node in ast.walk(tree):
        if isinstance(node, ok):
            continue
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
            continue
        raise FormulaError(f"formula {src!r} uses unsupported syntax ({type(node).__name__}); only + - * / ( ), numbers and names are allowed")
    return tree


def formula_names(src: str) -> list[str]:
    return sorted({n.id for n in ast.walk(parse_formula(src)) if isinstance(n, ast.Name)})


def _eval(node, src: str, env: dict[str, Decimal]) -> Decimal:
    if isinstance(node, ast.Expression):
        return _eval(node.body, src, env)
    if isinstance(node, ast.Constant):
        return Decimal(ast.get_source_segment(src, node))
    if isinstance(node, ast.Name):
        try:
            return env[node.id]
        except KeyError:
            raise FormulaError(f"no value for {node.id}") from None
    if isinstance(node, ast.UnaryOp):
        v = _eval(node.operand, src, env)
        return -v if isinstance(node.op, ast.USub) else v
    a, b = _eval(node.left, src, env), _eval(node.right, src, env)
    if isinstance(node.op, ast.Add):
        return a + b
    if isinstance(node.op, ast.Sub):
        return a - b
    if isinstance(node.op, ast.Mult):
        return a * b
    if b == 0:
        raise FormulaError("division by zero")
    return a / b


def evaluate(src: str, env: dict[str, Decimal]) -> Decimal:
    src = src.strip()
    with localcontext() as c:
        c.prec = PREC
        return _eval(parse_formula(src), src, env)


_SYM = {ast.Add: "+", ast.Sub: "−", ast.Mult: "×", ast.Div: "÷"}


def render(src: str, env: dict[str, Decimal]) -> str:
    """The formula with every name replaced by its value, e.g. '2,613,623,651,000 × 0.01'."""
    src = src.strip()

    def go(node, top=False):
        if isinstance(node, ast.Expression):
            return go(node.body, True)
        if isinstance(node, ast.Constant):
            return commas(Decimal(ast.get_source_segment(src, node)))
        if isinstance(node, ast.Name):
            return commas(env[node.id]) if node.id in env else node.id
        if isinstance(node, ast.UnaryOp):
            return ("−" if isinstance(node.op, ast.USub) else "") + go(node.operand)
        s = f"{go(node.left)} {_SYM[type(node.op)]} {go(node.right)}"
        return s if top else f"({s})"

    return go(parse_formula(src), True)


# ------------------------------------------------------------------ definitions (configurable) and assumption validation
def _path():
    return config.CONFIG_DIR / "benchmarks.json"


def load_definitions() -> list[dict]:
    stored = config._load(_path(), DEFAULT_BENCHMARKS)
    by = {d["number"]: d for d in stored}
    return [by.get(d["number"], d) for d in DEFAULT_BENCHMARKS] + [d for n, d in sorted(by.items()) if n > 10]


def save_definitions(defs: list[dict]) -> None:
    _path().parent.mkdir(parents=True, exist_ok=True)
    _path().write_text(json.dumps(defs, indent=2, ensure_ascii=False), encoding="utf8")


def assumptions_version(defs: list[dict]) -> str:
    canon = json.dumps([[d["number"], d.get("formula"), d.get("status"), d.get("assumptions")] for d in defs], sort_keys=True)
    return hashlib.sha256(canon.encode()).hexdigest()[:12]


def parse_assumption(name: str, value, meta: dict | None) -> Decimal:
    """Decimal for a stored/edited assumption, or ValueError with a user-facing reason."""
    try:
        d = Decimal(str(value).strip())
    except InvalidOperation:
        raise ValueError(f"{name}: {value!r} is not a number") from None
    if not d.is_finite():
        raise ValueError(f"{name}: must be a finite number")
    meta = meta or {}
    lo, hi = meta.get("min"), meta.get("max")
    if lo is not None and (d <= Decimal(lo) if meta.get("min_exclusive") else d < Decimal(lo)):
        raise ValueError(f"{name}: must be {'greater than' if meta.get('min_exclusive') else 'at least'} {lo}")
    if hi is not None and d > Decimal(hi):
        raise ValueError(f"{name}: must be at most {hi}")
    return d


def set_assumption(number: int, name: str, value) -> list[dict]:
    defs = load_definitions()
    d = next((x for x in defs if x["number"] == number), None)
    if d is None:
        raise KeyError(f"no benchmark {number}")
    if d.get("status") != "confirmed" or name not in d.get("assumptions", {}):
        raise ValueError(f"Benchmark {number} has no editable assumption {name!r}" + (" (definition not confirmed)" if d.get("status") != "confirmed" else ""))
    d["assumptions"][name] = plain(parse_assumption(name, value, d.get("assumption_meta", {}).get(name)))
    save_definitions(defs)
    return defs


def reset_assumption(number: int, name: str) -> list[dict]:
    default = next((x for x in DEFAULT_BENCHMARKS if x["number"] == number), None)
    if default is None or name not in default["assumptions"]:
        raise ValueError(f"Benchmark {number} has no default for {name!r}")
    return set_assumption(number, name, default["assumptions"][name])


def definition_problems(defs: list[dict]) -> dict[int, str]:
    """Static problems per benchmark (bad assumption, bad formula, unknown input) - found before any calculation."""
    bad: dict[int, str] = {}
    for d in defs:
        if d.get("status") != "confirmed":
            continue
        n = d["number"]
        try:
            if not d.get("formula"):
                raise ValueError("confirmed benchmark has no formula")
            for k, v in d.get("assumptions", {}).items():
                parse_assumption(k, v, d.get("assumption_meta", {}).get(k))
            for name in formula_names(d["formula"]):
                if name in d.get("assumptions", {}) or _BENCH_REF.match(name):
                    continue
                if not _KNOWN_INPUT.match(name):
                    raise ValueError(f"unknown input {name!r}")
        except (ValueError, FormulaError) as e:
            bad[n] = str(e)
    return bad


def calculation_order(defs: list[dict], bad: dict[int, str]) -> tuple[list[int], dict[int, str]]:
    """Topological order of the confirmed benchmarks; benchmarks in a dependency cycle are reported and excluded."""
    graph: dict[int, set[int]] = {}
    for d in defs:
        if d.get("status") == "confirmed" and d["number"] not in bad:
            graph[d["number"]] = {int(m.group(1)) for nm in formula_names(d["formula"]) if (m := _BENCH_REF.match(nm))}
    problems = dict(bad)
    while True:
        try:
            return list(TopologicalSorter(graph).static_order()), problems
        except CycleError as e:
            cyc = e.args[1]
            text = " → ".join(f"benchmark_{n}" for n in cyc)
            for n in set(cyc):
                problems[n] = f"circular dependency: {text}"
                graph.pop(n, None)


# ------------------------------------------------------------------ inputs (the only place source units are converted)
@dataclass
class InputValue:
    name: str
    label: str
    usd: Decimal
    kind: str  # official (as printed in a source document) | derived (computed from official values)
    fiscal_year: int
    reporting_date: str
    source_report: str
    source_url: str
    location: str  # "PDF p.96 (printed A-20) · Note 2: ..." / "p.9 · Exhibit 2.2 ..."
    source_units: str  # as published: "USD thousands" ...
    source_raw: str  # as printed
    note: str = ""
    unit: str = "usd"  # usd | ratio (a dimensionless fraction, e.g. 0.04 for 4%; `usd` then holds that fraction)


def _units_label(units: str) -> str:
    return f"USD {units}"


def provider_slug(provider: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", provider.lower()).strip("_")


RATIO_DECIMALS = 15  # a derived ratio is rounded once, here, to 1e-15 (under one cent on a $3tn exposure)


def _fhlb_inputs(fiscal_years, db=None) -> dict[int, dict[str, InputValue]]:
    """FHLB ratios for the quarter that ends on each GNMA fiscal year end (Sept 30), as fractions. Exact Decimal arithmetic."""
    by_period: dict[str, dict[str, dict[str, dict]]] = {}
    for o in fhlb.load_rows(db):
        by_period.setdefault(o["period"], {}).setdefault(o["fhlbank"], {})[o["field"]] = o
    out: dict[int, dict[str, InputValue]] = {}
    for fy in fiscal_years:
        banks = by_period.get(f"{fy}Q3")
        if not banks:
            continue
        date, found = f"{fy}-09-30", {}

        def make(name, label, fraction, kind, first, units, raw, location, note=""):
            return InputValue(name, label, fraction, kind, fy, date, first["source_file"], first.get("source_url") or "", location, units, raw, note, "ratio")

        # Benchmark 3: the 4.00% minimum is published per bank (not for Combined); use it only when all 11 banks agree
        mins = [banks.get(b, {}).get("t92_min_ratio_pct") for b in fhlb.BANKS]
        if all(mins) and len({Decimal(str(m["parsed_value"])) for m in mins}) == 1:
            first = mins[0]
            found["fhlb_regulatory_capital_min_ratio"] = make(
                "fhlb_regulatory_capital_min_ratio", "FHLBs regulatory capital ratio, minimum requirement",
                Decimal(str(first["parsed_value"])) / 100, "official", first, "percent", first["raw_value"],
                f"{first['location']} · {first['table_name']}", "identical for all 11 FHLBanks")
        # Benchmark 5: Actual Risk Based Capital Ratio (derived) of the Combined row, itself derived when not published
        values = {b: {f: Decimal(str(o["parsed_value"])) for f, o in fields.items()} for b, fields in banks.items()}
        with localcontext() as c:
            c.prec = PREC
            combined = values.get("Combined")
            derived_row = combined is None
            if derived_row:
                combined = fhlb.derive_combined(values)
            ratio = fhlb.derive(combined).get("derived_actual_rbc_ratio_pct") if combined else None
            if ratio is not None:
                fraction = (ratio / 100).quantize(Decimal(1).scaleb(-RATIO_DECIMALS), ROUND_HALF_UP)
        if ratio is not None:
            first = banks["Combined"]["t91_min_mm"] if not derived_row else banks[fhlb.BANKS[0]]["t91_min_mm"]
            found["fhlb_combined_actual_rbc_ratio"] = make(
                "fhlb_combined_actual_rbc_ratio", "FHLBs Actual Risk Based Capital Ratio (derived), Combined", fraction, "derived", first, "percent (derived)",
                "computed: Risk-based capital, minimum requirement ÷ (Risk-based capital, actual ÷ Regulatory capital ratio, actual)",
                f"{first['table_name']} and Table 9.2",
                "Combined row not published in this report; derived as the sum of the 11 FHLBanks" if derived_row else "Combined row as published")
        if found:
            out[fy] = found
    return out


def build_inputs(db=None) -> dict[int, dict[str, InputValue]]:
    """fiscal year -> input name -> value, for every GNMA fiscal year. No value is ever carried over from another year."""
    figs = gnma.headline_series(gnma.load_figures(db))
    out: dict[int, dict[str, InputValue]] = {}
    for f in figs:
        loc = f"PDF p.{f.pdf_page}" + (f" (printed {f.printed_page})" if f.printed_page else "") + (f" · {f.note}" if f.note else "")
        note = "comparative figure from a later report" if f.role == "comparative" else ""
        base = dict(fiscal_year=f.fiscal_year, reporting_date=f.reporting_date, source_report=f.source_report, source_url=f.source_url,
                    location=loc, source_units=_units_label(f.units), note=note)
        out[f.fiscal_year] = {
            "gnma_outstanding_mbs": InputValue("gnma_outstanding_mbs", GNMA_INPUTS["gnma_outstanding_mbs"], Decimal(f.mbs_usd), "official", source_raw=f.mbs_raw, **base),
            "gnma_outstanding_mbs_commitments": InputValue("gnma_outstanding_mbs_commitments", GNMA_INPUTS["gnma_outstanding_mbs_commitments"], Decimal(f.commitments_usd), "official", source_raw=f.commitments_raw, **base),
            "gnma_total_exposure": InputValue("gnma_total_exposure", GNMA_INPUTS["gnma_total_exposure"], Decimal(f.total_usd), "derived",
                                              source_raw=f.total_raw or "(computed: MBS + commitments)", **base),
        }
    quarter_end = {"Q1": "03-31", "Q2": "06-30", "Q3": "09-30", "Q4": "12-31"}
    for o in store.get_observations(path=db):
        m = re.fullmatch(r"(\d{4})(Q[1-4])", o["period"])
        if not m or o["field"] not in (CET1, ATA):
            continue
        fy, date = int(m.group(1)), f"{m.group(1)}-{quarter_end[m.group(2)]}"
        if fy not in out or not date.endswith(Q3_END):
            continue  # only the quarter that ends on the GNMA fiscal year end (Sept 30) lines up; nothing else is substituted
        prefix = "cet1" if o["field"] == CET1 else "ata"
        name = f"{prefix}_{provider_slug(o['provider'])}"
        label = f"{'CET1 amount' if prefix == 'cet1' else 'Adjusted total assets'} ({o['provider']})"
        out[fy][name] = InputValue(name, label, gnma.to_usd(o["raw_value"], o["units_detected"]), "official", fy, date, o["source_file"], o.get("source_url") or "",
                                   f"{o['location']} · {o['table_name']}", _units_label(o["units_detected"]), o["raw_value"])
    for fy, vals in _fhlb_inputs(list(out), db).items():
        out[fy].update(vals)
    return out


# ------------------------------------------------------------------ calculation
@dataclass
class Result:
    number: int
    name: str
    fiscal_year: int
    reporting_date: str
    status: str  # ok | missing_input | unconfirmed | invalid_assumption | error
    message: str = ""
    formula: str | None = None
    result_usd: Decimal | None = None
    inputs: list = field(default_factory=list)
    assumptions: dict = field(default_factory=dict)
    calculation: str = ""
    depends_on: list = field(default_factory=list)

    def to_dict(self) -> dict:
        usd = self.result_usd
        return {
            "number": self.number, "name": self.name, "fiscal_year": self.fiscal_year, "reporting_date": self.reporting_date,
            "status": self.status, "message": self.message, "formula": self.formula, "calculation": self.calculation,
            "assumptions": self.assumptions, "inputs": self.inputs, "depends_on": self.depends_on,
            "result_usd": None if usd is None else plain(usd),
            "result_billions": None if usd is None else plain(usd_to_billions(usd)),
            "result_billions_text": fmt_billions(usd),
            "result_thousands_text": None if usd is None else fmt_thousands(usd),
        }


def _input_row(v: InputValue) -> dict:
    if v.unit == "ratio":  # dimensionless: `usd` is the exact fraction; the text is shown as a percent, never as dollars
        pct = (v.usd * 100).quantize(Decimal("0.01"), ROUND_HALF_UP)
        billions, text = "", f"{pct}%"
    else:
        billions, text = plain(usd_to_billions(v.usd)), fmt_billions(v.usd)
    return {"name": v.name, "label": v.label, "kind": v.kind, "unit": v.unit, "fiscal_year": v.fiscal_year, "reporting_date": v.reporting_date,
            "usd": plain(v.usd), "billions": billions, "billions_text": text,
            "source_units": v.source_units, "source_raw": v.source_raw, "source_report": v.source_report, "source_url": v.source_url,
            "location": v.location, "note": v.note}


def calculate(defs: list[dict] | None = None, inputs: dict[int, dict[str, InputValue]] | None = None) -> tuple[list[Result], dict[int, str]]:
    defs = load_definitions() if defs is None else defs
    inputs = build_inputs() if inputs is None else inputs
    bad = definition_problems(defs)
    order, problems = calculation_order(defs, bad)
    by_num = {d["number"]: d for d in defs}
    results: list[Result] = []
    for fy in sorted(inputs):
        avail = inputs[fy]
        date = next(iter(avail.values())).reporting_date if avail else f"{fy}-09-30"
        done: dict[int, Result] = {}
        for n in sorted(by_num):
            d = by_num[n]
            r = Result(n, d["name"], fy, date, "unconfirmed", d.get("description", "") if d.get("status") != "confirmed" else "", d.get("formula"))
            if d.get("status") == "confirmed" and n in problems:
                r.status, r.message = ("invalid_assumption" if "circular" not in problems[n] else "error"), problems[n]
            done[n] = r
        for n in order:
            d, r = by_num[n], done[n]
            names = formula_names(d["formula"])
            env: dict[str, Decimal] = {k: parse_assumption(k, v, d.get("assumption_meta", {}).get(k)) for k, v in d.get("assumptions", {}).items()}
            r.assumptions = {k: plain(v) for k, v in env.items()}
            missing = []
            for nm in names:
                if nm in env:
                    continue
                if (m := _BENCH_REF.match(nm)):
                    dep = done.get(int(m.group(1)))
                    if dep is None or dep.status != "ok":
                        missing.append(nm)
                    else:
                        env[nm] = dep.result_usd
                        r.depends_on.append(nm)
                elif nm in avail:
                    env[nm] = avail[nm].usd
                    r.inputs.append(_input_row(avail[nm]))
                else:
                    missing.append(nm)
            if missing:
                r.status, r.message = "missing_input", f"missing input(s) for FY{fy}: {', '.join(missing)} (not substituted from any other period)"
                continue
            try:
                r.result_usd = evaluate(d["formula"], env)
            except FormulaError as e:
                r.status, r.message = "error", str(e)
                continue
            r.status = "ok"
            r.calculation = f"{render(d['formula'], env)} = {commas(r.result_usd)}"
        results.extend(done[n] for n in sorted(done))
    return results, problems


# ------------------------------------------------------------------ summaries + validation
def _yoy(cur: dict, prior: dict | None) -> dict | None:
    if not prior or prior["fiscal_year"] != cur["fiscal_year"] - 1:
        return None
    a, b = Decimal(cur["result_usd"]), Decimal(prior["result_usd"])
    with localcontext() as c:
        c.prec = PREC
        pct = None if b == 0 else float((((a - b) / b) * 100).quantize(Decimal("0.0001")))
    diff = a - b
    sign = "+" if diff > 0 else "−" if diff < 0 else ""
    return {"prior_fiscal_year": prior["fiscal_year"], "abs_usd": plain(diff), "abs_billions_text": f"{sign}{fmt_billions(abs(diff))}", "pct": pct}


def summarize(defs: list[dict], results: list[dict]) -> list[dict]:
    out = []
    for d in defs:
        rs = [r for r in results if r["number"] == d["number"]]
        ok = [r for r in rs if r["status"] == "ok"]
        latest = ok[-1] if ok else None
        prior = next((r for r in ok if latest and r["fiscal_year"] == latest["fiscal_year"] - 1), None)
        out.append({"number": d["number"], "name": d["name"], "status": d.get("status"), "formula": d.get("formula"),
                    "latest": latest, "prior": prior, "yoy": _yoy(latest, prior) if latest else None,
                    "periods_calculated": len(ok), "periods_total": len(rs),
                    "problem": None if ok else (rs[-1]["message"] if rs else "no periods")})
    return out


def validate(defs: list[dict], inputs: dict[int, dict[str, InputValue]], results: list[Result], problems: dict[int, str]) -> list[dict]:
    checks: list[dict] = []

    def add(name, status, detail):
        checks.append({"name": name, "status": status, "detail": detail})

    # 1. GNMA total = MBS + commitments
    bad = [fy for fy, v in inputs.items() if v["gnma_total_exposure"].usd != v["gnma_outstanding_mbs"].usd + v["gnma_outstanding_mbs_commitments"].usd]
    add("GNMA Total Maximum Exposure to Loss = Outstanding MBS + Outstanding MBS Commitments", "fail" if bad else "pass",
        f"{len(inputs)} fiscal year(s) checked" + (f"; violated in FY{bad}" if bad else ""))
    # 2. unit sanity: guards against a x1,000 / x1,000,000 mis-scale of the GNMA inputs
    off = [fy for fy, v in inputs.items() if not Decimal(10) ** 11 < v["gnma_total_exposure"].usd < Decimal(10) ** 14]
    add("Units: GNMA exposure is a plausible USD amount ($100bn to $100tn), not scaled by 1e3 or 1e6", "fail" if off else "pass",
        f"out of range in FY{off}" if off else "all fiscal years in range")
    # 3. date alignment
    mis = [(fy, v.name) for fy, vs in inputs.items() for v in vs.values() if v.reporting_date != f"{fy}-09-30"]
    add("Reporting dates align across all inputs of a fiscal year (Sept 30)", "fail" if mis else "pass", f"misaligned: {mis}" if mis else "all inputs dated the fiscal year end")
    # 4. reproducibility from stored values (round-trip through the serialised text, a different data path from calculate())
    drift = []
    by_def = {d["number"]: d for d in defs}
    for r in results:
        if r.status != "ok":
            continue
        d = by_def[r.number]
        env = {k: Decimal(v) for k, v in r.assumptions.items()} | {i["name"]: Decimal(i["usd"]) for i in r.inputs}
        env |= {dep: next(x.result_usd for x in results if x.number == int(dep.split("_")[1]) and x.fiscal_year == r.fiscal_year) for dep in r.depends_on}
        if evaluate(d["formula"], env) != r.result_usd or Decimal(r.to_dict()["result_usd"]) != r.result_usd:
            drift.append((r.number, r.fiscal_year))
    n_ok = sum(1 for r in results if r.status == "ok")
    add("Every result reproduces exactly from its stored inputs and assumptions; no silent rounding", "fail" if drift else "pass",
        f"{n_ok} result(s) recomputed" + (f"; differ: {drift}" if drift else ""))
    # 5. Benchmark 1 uses the 1% correctly
    b1 = by_def.get(1)
    b1r = [r for r in results if r.number == 1 and r.status == "ok"]
    if b1 and b1.get("status") == "confirmed" and b1.get("formula") == DEFAULT_BENCHMARKS[0]["formula"] and 1 not in problems:
        pct = Decimal(b1["assumptions"]["adjustment_pct"])
        wrong = [r.fiscal_year for r in b1r if r.result_usd != inputs[r.fiscal_year]["gnma_total_exposure"].usd * pct]
        add("Benchmark 1 = GNMA Total Maximum Exposure to Loss × adjustment percentage", "fail" if wrong else "pass", f"{len(b1r)} period(s)" + (f"; wrong in FY{wrong}" if wrong else ""))
        default = Decimal(DEFAULT_BENCHMARKS[0]["assumptions"]["adjustment_pct"])
        if pct == default:
            add("Benchmark 1 uses the business-specified 1% adjustment", "pass", "adjustment_pct = 0.01")
        else:
            add("Benchmark 1 uses the business-specified 1% adjustment", "warn", f"adjustment_pct has been changed to {plain(pct)}; results differ from the specified 1% definition")
    else:
        add("Benchmark 1 uses the business-specified definition", "fail",
            problems.get(1) or "Benchmark 1 formula or status differs from the specified definition")
    # 6. spec reference value (only meaningful with the specified 1%)
    ref = next((r for r in b1r if r.fiscal_year == 2023), None)
    if ref is not None and b1["assumptions"].get("adjustment_pct") == "0.01":
        ok = ref.result_usd / THOUSAND == Decimal("26136236.51") and ref.result_usd == Decimal("26136236510")
        add("FY2023 Benchmark 1 = $26,136,236.51 (USD thousands as published) = $26,136,236,510", "pass" if ok else "fail",
            f"calculated {fmt_thousands(ref.result_usd)} thousand = {commas(ref.result_usd)} USD = {fmt_billions(ref.result_usd, 8)}")
    elif ref is None:
        add("FY2023 Benchmark 1 reference value", "fail", "FY2023 Benchmark 1 could not be calculated")
    # 6b. Benchmark 2 uses the 17% risk weight and 4.5% minimum CET1 ratio correctly
    b2 = by_def.get(2)
    b2r = [r for r in results if r.number == 2 and r.status == "ok"]
    if b2 and b2.get("status") == "confirmed" and b2.get("formula") == DEFAULT_BENCHMARKS[1]["formula"] and 2 not in problems:
        rw = Decimal(b2["assumptions"]["risk_weight_pct"])
        mcr = Decimal(b2["assumptions"]["minimum_cet1_ratio_pct"])
        wrong2 = [r.fiscal_year for r in b2r if r.result_usd != inputs[r.fiscal_year]["gnma_total_exposure"].usd * rw * mcr]
        add("Benchmark 2 = GNMA Total Maximum Exposure to Loss × risk weight × minimum CET1 capital ratio", "fail" if wrong2 else "pass",
            f"{len(b2r)} period(s)" + (f"; wrong in FY{wrong2}" if wrong2 else ""))
        default_rw = Decimal(DEFAULT_BENCHMARKS[1]["assumptions"]["risk_weight_pct"])
        default_mcr = Decimal(DEFAULT_BENCHMARKS[1]["assumptions"]["minimum_cet1_ratio_pct"])
        if rw == default_rw and mcr == default_mcr:
            add("Benchmark 2 uses the business-specified 17% risk weight and 4.5% minimum CET1 ratio", "pass", "risk_weight_pct = 0.17, minimum_cet1_ratio_pct = 0.045")
        else:
            add("Benchmark 2 uses the business-specified 17% risk weight and 4.5% minimum CET1 ratio", "warn",
                f"risk_weight_pct={plain(rw)}, minimum_cet1_ratio_pct={plain(mcr)} differ from the specified 17%/4.5% definition")
    else:
        add("Benchmark 2 uses the business-specified definition", "fail",
            problems.get(2) or "Benchmark 2 formula or status differs from the specified definition")
    # 7. definitions
    errs = {n: m for n, m in problems.items()}
    add("Benchmark definitions are valid (formulas, assumptions, no circular dependencies)", "fail" if errs else "pass",
        "; ".join(f"Benchmark {n}: {m}" for n, m in sorted(errs.items())) if errs else "no problems")
    pending = [d["number"] for d in defs if d.get("status") != "confirmed"]
    add("All benchmarks have a confirmed definition", "warn" if pending else "pass",
        f"Benchmark(s) {', '.join(map(str, pending))} require business confirmation; no result is shown for them" if pending else "all confirmed")
    # 8. missing inputs flagged
    miss = sorted({(r.number, r.fiscal_year) for r in results if r.status == "missing_input"})
    add("Missing inputs are flagged, never substituted", "warn" if miss else "pass",
        f"{len(miss)} result(s) lack an input" if miss else "none")
    return checks


def _safe_names(formula: str | None) -> list[str]:
    try:
        return formula_names(formula) if formula else []
    except FormulaError:
        return []


def build_payload(db=None) -> dict:
    defs = load_definitions()
    inputs = build_inputs(db)
    results, problems = calculate(defs, inputs)
    rd = [r.to_dict() for r in results]
    default_by = {d["number"]: d for d in DEFAULT_BENCHMARKS}
    definitions = []
    for d in defs:
        meta = d.get("assumption_meta", {})
        dflt = default_by.get(d["number"], {}).get("assumptions", {})
        definitions.append({
            "number": d["number"], "key": d.get("key"), "name": d["name"], "description": d.get("description", ""), "formula": d.get("formula"),
            "status": d.get("status"), "confirmed": d.get("status") == "confirmed" and d["number"] not in problems,
            "reference": d.get("reference", ""), "problem": problems.get(d["number"]),
            "inputs": _safe_names(d.get("formula")),
            "assumptions": [{"name": k, "label": meta.get(k, {}).get("label", k), "unit": meta.get(k, {}).get("unit", ""), "value": v,
                             "default": dflt.get(k), "min": meta.get(k, {}).get("min"), "max": meta.get(k, {}).get("max"),
                             "min_exclusive": bool(meta.get(k, {}).get("min_exclusive")), "editable": d.get("status") == "confirmed"}
                            for k, v in d.get("assumptions", {}).items()],
        })
    flat_inputs = [_input_row(v) for fy in sorted(inputs) for v in inputs[fy].values()]
    return {
        "units": {"engine": "USD", "display": "USD (billions)", "divisor": int(BILLION), "display_decimals": DISPLAY_DECIMALS,
                  "pipeline": "Source values are converted once to exact USD; formulas run in USD at full precision; results are divided by 1,000,000,000 once for display."},
        "assumptions_version": assumptions_version(defs),
        "definitions": definitions,
        "periods": [{"fiscal_year": fy, "reporting_date": next(iter(v.values())).reporting_date} for fy, v in sorted(inputs.items())],
        "inputs": flat_inputs,
        "results": rd,
        "summary": summarize(defs, rd),
        "validation": validate(defs, inputs, results, problems),
    }
