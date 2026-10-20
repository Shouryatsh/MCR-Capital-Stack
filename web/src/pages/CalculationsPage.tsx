import { RotateCcw } from "lucide-react";
import { useEffect, useId, useMemo, useState } from "react";
import { Badge, GlassCard } from "../components/GlassCard";
import { ActionButton } from "../components/Buttons";
import { StatusBadge } from "../components/BenchmarkResults";
import { DataTable, type Column } from "../components/DataTable";
import { EmptyState, ErrorState, LoadingState } from "../components/States";
import { ChecksCard } from "../components/ChecksCard";
import { api, ApiError } from "../lib/api";
import { useApi } from "../lib/hooks";
import { fmtDate, fmtUsd } from "../lib/format";
import type { BenchAssumption, BenchDefinition, BenchInput, BenchResult, BenchmarksResponse } from "../lib/types";

const KIND = {
  official: { tone: "neutral", label: "Official source" },
  derived: { tone: "accent", label: "Derived" },
} as const;
const usd = (s: string | null) => (s == null ? "—" : fmtUsd(Number(s)));
const SELECT = "rounded-lg border border-white/10 bg-ink-900/80 px-2.5 py-1.5 text-sm text-fg";

export function CalculationsPage() {
  const query = useApi<BenchmarksResponse>("/benchmarks");
  const [override, setOverride] = useState<BenchmarksResponse | null>(null);
  const [bench, setBench] = useState("all");
  const [fy, setFy] = useState("all");
  const [pending, setPending] = useState(false);
  const [notice, setNotice] = useState("");
  useEffect(() => setOverride(null), [query.data]);
  const data = override ?? query.data;

  const results = useMemo(
    () => (data?.results ?? []).filter((r) => (bench === "all" || r.number === Number(bench)) && (fy === "all" || r.fiscal_year === Number(fy)) && (pending || r.status !== "unconfirmed")),
    [data, bench, fy, pending],
  );

  if (query.loading && !data) return <LoadingState label="Loading benchmark calculations" />;
  if (query.error) return <ErrorState error={query.error} onRetry={query.reload} />;
  if (!data) return null;
  if (!data.periods.length) return <EmptyState title="No GNMA inputs yet">Benchmarks are calculated from the GNMA annual-report data. Fetch it from Source values (GNMA) or Data sources first.</EmptyState>;

  const inputs = data.inputs.filter((i) => fy === "all" || i.fiscal_year === Number(fy));
  const defs = data.definitions.filter((d) => bench === "all" || d.number === Number(bench));
  const latestKeys = new Set(data.summary.filter((s) => s.latest).map((s) => `${s.number}-${s.latest!.fiscal_year}`));
  const isLatest = (r: BenchResult) => latestKeys.has(`${r.number}-${r.fiscal_year}`);

  const inputCols: Column<BenchInput>[] = [
    { key: "fiscal_year", header: "FY", className: "whitespace-nowrap", render: (i) => `FY${i.fiscal_year}` },
    { key: "reporting_date", header: "Reporting date", className: "whitespace-nowrap", render: (i) => fmtDate(i.reporting_date) },
    { key: "label", header: "Input", className: "min-w-52 whitespace-normal font-medium" },
    { key: "kind", header: "Type", render: (i) => <Badge tone={KIND[i.kind].tone}>{KIND[i.kind].label}</Badge> },
    { key: "billions", header: "Value (USD billions; ratios in %)", numeric: true, value: (i) => (i.unit === "ratio" ? Number(i.usd) * 100 : Number(i.billions)), render: (i) => <strong>{i.billions_text}</strong> },
    { key: "usd", header: "Exact value (USD; ratios as a fraction)", numeric: true, value: (i) => Number(i.usd), render: (i) => (i.unit === "ratio" ? i.usd : usd(i.usd)) },
    { key: "source_units", header: "Source units", render: (i) => i.source_units },
    { key: "source_raw", header: "As printed", numeric: true },
    { key: "source_report", header: "Source", className: "min-w-64 whitespace-normal", render: (i) => (
      <span className="text-xs text-muted">{i.source_url ? <a className="text-aurora-cyan hover:underline" href={i.source_url} target="_blank" rel="noreferrer">{i.source_report}<span className="sr-only"> (opens the source PDF)</span></a> : i.source_report}<br />{i.location}{i.note && <><br /><em>{i.note}</em></>}</span>) },
  ];

  const defCols: Column<BenchDefinition>[] = [
    { key: "number", header: "#", numeric: true },
    { key: "name", header: "Benchmark", sticky: true, className: "min-w-48 whitespace-normal font-medium" },
    { key: "description", header: "Description", className: "min-w-64 whitespace-normal text-xs text-muted" },
    { key: "inputs", header: "Input metrics", value: (d) => d.inputs.join(", "), className: "min-w-44 whitespace-normal", render: (d) => (d.inputs.length ? <code className="text-xs">{d.inputs.join(", ")}</code> : "—") },
    { key: "assumption", header: "Assumption", sortable: false, className: "min-w-64", render: (d) => (d.assumptions.length ? d.assumptions.map((a) => <AssumptionEditor key={a.name} number={d.number} a={a} onSaved={(p, msg) => { setOverride(p); setNotice(msg); }} />) : <span className="text-subtle">—</span>) },
    { key: "formula", header: "Formula", className: "min-w-52 whitespace-normal", render: (d) => (d.formula ? <code className="text-xs text-aurora-cyan">{d.formula}</code> : <span className="text-xs text-subtle">not defined</span>) },
    { key: "period", header: "Reporting period", value: () => data.periods[0].fiscal_year, className: "whitespace-nowrap text-xs", render: () => `FY${data.periods[0].fiscal_year}–FY${data.periods[data.periods.length - 1].fiscal_year} (Sept 30)` },
    { key: "result", header: "Latest result (USD billions)", numeric: true, value: (d) => { const l = data.summary.find((s) => s.number === d.number)?.latest; return l ? Number(l.result_billions) : null; },
      render: (d) => { const l = data.summary.find((s) => s.number === d.number)?.latest; return l ? <span><strong>{l.result_billions_text}</strong> <span className="text-xs text-subtle">FY{l.fiscal_year}</span></span> : "—"; } },
    { key: "reference", header: "Source / assumption reference", className: "min-w-56 whitespace-normal text-xs text-muted" },
    { key: "validation", header: "Validation", value: (d) => (d.confirmed ? 0 : 1), render: (d) => <span title={d.problem ?? undefined}><StatusBadge status={d.problem ? "invalid_assumption" : d.confirmed ? "ok" : "unconfirmed"} /></span> },
  ];

  const resCols: Column<BenchResult>[] = [
    { key: "number", header: "Benchmark", sticky: true, className: "min-w-52 whitespace-normal", value: (r) => r.number, render: (r) => <span className="font-medium">{r.number}. {r.name}</span> },
    { key: "fiscal_year", header: "FY", className: "whitespace-nowrap", render: (r) => <span className="inline-flex items-center gap-1.5">FY{r.fiscal_year}{isLatest(r) && <Badge tone="accent">Latest</Badge>}</span> },
    { key: "reporting_date", header: "Reporting date", className: "whitespace-nowrap", render: (r) => fmtDate(r.reporting_date) },
    { key: "status", header: "Status", render: (r) => <StatusBadge status={r.status} /> },
    { key: "formula", header: "Formula", className: "min-w-48 whitespace-normal", render: (r) => (r.formula ? <code className="text-xs text-aurora-cyan">{r.formula}</code> : "—") },
    { key: "inputs", header: "Inputs (USD billions; ratios in %)", sortable: false, className: "min-w-56 whitespace-normal text-xs", render: (r) => (r.inputs.length ? r.inputs.map((i) => <div key={i.name}>{i.label}: <span className="tnum">{i.billions_text}</span></div>) : "—") },
    { key: "assumptions", header: "Assumptions", sortable: false, className: "whitespace-nowrap text-xs", render: (r) => (Object.keys(r.assumptions).length ? Object.entries(r.assumptions).map(([k, v]) => <div key={k}>{k} = <span className="tnum">{v}</span></div>) : "—") },
    { key: "result", header: "Result (USD billions)", numeric: true, value: (r) => (r.result_billions == null ? null : Number(r.result_billions)), render: (r) => <strong>{r.result_billions_text}</strong> },
  ];

  return (
    <div className="space-y-6">
      <GlassCard variant="data" className="space-y-1 p-4 text-sm text-muted" role="note" aria-label="Units">
        <p><strong className="text-fg">Units.</strong> {data.units.pipeline} Results are shown in <strong className="text-fg">{data.units.display}</strong> ({data.units.display_decimals} decimals); full precision is in each calculation’s details.</p>
        <p className="text-xs text-subtle">Assumptions version <code>{data.assumptions_version}</code> · identifies the exact set of formulas and assumptions behind the numbers on this page.</p>
      </GlassCard>

      <div className="flex flex-wrap items-center gap-4" role="search" aria-label="Filter calculations">
        <label className="flex items-center gap-2 text-sm text-muted">Benchmark
          <select className={SELECT} value={bench} onChange={(e) => setBench(e.target.value)} aria-label="Benchmark">
            <option value="all">All benchmarks</option>
            {data.definitions.map((d) => <option key={d.number} value={d.number}>{d.number}. {d.name}</option>)}
          </select>
        </label>
        <label className="flex items-center gap-2 text-sm text-muted">Fiscal year
          <select className={SELECT} value={fy} onChange={(e) => setFy(e.target.value)} aria-label="Fiscal year">
            <option value="all">All years</option>
            {data.periods.map((p) => <option key={p.fiscal_year} value={p.fiscal_year}>FY{p.fiscal_year}</option>)}
          </select>
        </label>
        <label className="flex items-center gap-2 text-sm text-muted">
          <input type="checkbox" checked={pending} onChange={(e) => setPending(e.target.checked)} className="size-4 accent-teal-400" />
          Include benchmarks awaiting confirmation in results
        </label>
      </div>
      <p role="status" aria-live="polite" className="min-h-5 text-xs text-pos">{notice}</p>

      <ChecksCard checks={data.validation} label="Benchmark validation" subtitle={`${data.validation.length} checks on inputs, units, formulas and reproducibility`} />

      <section aria-labelledby="sec-a" className="space-y-2">
        <h2 id="sec-a" className="text-base font-semibold">A. Source data</h2>
        <p className="text-xs text-subtle">Raw values stay exactly as published and are converted once to USD. <Badge tone="neutral">Official source</Badge> values come straight from a document; <Badge tone="accent">Derived</Badge> values are computed from them. CET1 and assets are only used for the quarter that ends on the GNMA fiscal-year end (Sept 30); no other period is substituted. FHLB ratios are shown as percents and used as fractions.</p>
        <DataTable<BenchInput> caption="Benchmark source data" rows={inputs} rowKey={(i) => `${i.fiscal_year}-${i.name}`} columns={inputCols} filterable filterPlaceholder="Filter inputs…" initialSort={{ key: "fiscal_year", dir: "asc" }} maxHeight="26rem"
          empty="No inputs for this selection." />
      </section>

      <section aria-labelledby="sec-b" className="space-y-2">
        <h2 id="sec-b" className="text-base font-semibold">B. Benchmark assumptions</h2>
        <p className="text-xs text-subtle"><Badge tone="warning">Editable</Badge> assumptions are validated on the server and recalculate every dependent result immediately. Benchmarks without a confirmed definition cannot be edited and produce no number.</p>
        <DataTable<BenchDefinition> caption="Benchmark assumptions and formulas" rows={defs} rowKey={(d) => String(d.number)} columns={defCols} filterable filterPlaceholder="Filter benchmarks…" initialSort={{ key: "number", dir: "asc" }} maxHeight="34rem" />
      </section>

      <section aria-labelledby="sec-c" className="space-y-2">
        <h2 id="sec-c" className="text-base font-semibold">C. Calculated benchmark results</h2>
        <p className="text-xs text-subtle">Expand a row to see the formula, every input with its source, the assumptions applied and the exact result. <Badge tone="accent">Calculated</Badge> values are never typed in or rounded in storage.</p>
        <DataTable<BenchResult> caption="Calculated benchmark results by fiscal year" rows={results} rowKey={(r) => `${r.number}-${r.fiscal_year}`} columns={resCols} filterable filterPlaceholder="Filter results…"
          initialSort={{ key: "fiscal_year", dir: "asc" }} maxHeight="36rem" renderDetail={(r) => <CalculationDetail r={r} version={data.assumptions_version} />}
          detailLabel={(r) => `Benchmark ${r.number} FY${r.fiscal_year}`} empty="No results for this selection."
          rowClassName={(r) => (isLatest(r) ? "bg-aurora-cyan/10" : undefined)} />
      </section>
    </div>
  );
}

function AssumptionEditor({ number, a, onSaved }: { number: number; a: BenchAssumption; onSaved: (p: BenchmarksResponse, msg: string) => void }) {
  const id = useId();
  const [text, setText] = useState(a.value);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => setText(a.value), [a.value]);

  const call = async (method: "PUT" | "DELETE") => {
    setBusy(true);
    setError("");
    try {
      const p = await api<BenchmarksResponse>(`/benchmarks/${number}/assumptions/${a.name}`, method === "PUT"
        ? { method, headers: { "Content-Type": "application/json" }, body: JSON.stringify({ value: text }) } : { method });
      onSaved(p, `Benchmark ${number} ${a.label} ${method === "PUT" ? "saved" : "reset"}; results recalculated.`);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="rounded-lg border border-warn/30 bg-warn/5 p-2" data-testid="assumption-editor">
      <label htmlFor={id} className="mb-1 flex items-center gap-2 text-xs text-muted">{a.label} <Badge tone="warning">Editable</Badge></label>
      <div className="flex items-center gap-2">
        <input id={id} value={text} onChange={(e) => setText(e.target.value)} inputMode="decimal" aria-invalid={!!error} aria-describedby={`${id}-h`}
          className="tnum w-24 rounded-md border border-white/15 bg-ink-900/80 px-2 py-1 text-sm text-fg" />
        <ActionButton onClick={() => call("PUT")} disabled={busy || text === a.value} aria-label={`Save ${a.label}`}>Save</ActionButton>
        {a.default != null && a.value !== a.default && <ActionButton onClick={() => call("DELETE")} disabled={busy} aria-label={`Reset ${a.label} to ${a.default}`}><RotateCcw className="size-3.5" aria-hidden="true" />Reset</ActionButton>}
      </div>
      <p id={`${id}-h`} className="mt-1 text-[11px] text-subtle">{a.unit}{a.default != null && ` · default ${a.default}`}</p>
      {error && <p role="alert" className="mt-1 text-xs text-neg">{error}</p>}
    </div>
  );
}

function CalculationDetail({ r, version }: { r: BenchResult; version: string }) {
  return (
    <div className="space-y-4 text-sm" data-testid="calculation-detail">
      {r.status !== "ok" && (
        <p role="alert" className="rounded-lg border border-warn/30 bg-warn/10 p-3 text-warn">{r.status === "unconfirmed" ? "Requires business confirmation. " : ""}{r.message || "No result."}</p>
      )}
      {r.formula && (
        <div>
          <h4 className="text-xs font-semibold tracking-wide text-muted uppercase">Formula</h4>
          <p><code className="text-aurora-cyan">{r.formula}</code></p>
          {r.calculation && <p className="mt-1 tnum" data-testid="calculation-line"><span className="text-subtle">With values (USD): </span>{r.calculation}</p>}
        </div>
      )}
      {r.inputs.length > 0 && (
        <div>
          <h4 className="mb-1 text-xs font-semibold tracking-wide text-muted uppercase">Inputs</h4>
          <ul className="space-y-2">
            {r.inputs.map((i) => (
              <li key={i.name} className="rounded-lg border border-white/5 bg-ink-900/60 p-2.5">
                <p className="flex flex-wrap items-center gap-2"><strong>{i.label}</strong><Badge tone={KIND[i.kind].tone}>{KIND[i.kind].label}</Badge><span className="text-xs text-subtle">as of {fmtDate(i.reporting_date)}</span></p>
                <p className="tnum text-xs text-muted">{i.unit === "ratio" ? `${i.usd} (ratio) = ${i.billions_text}` : `${usd(i.usd)} = ${i.billions} USD billions`} · printed {i.source_raw} ({i.source_units}){i.note && ` · ${i.note}`}</p>
                <p className="text-xs text-subtle">{i.source_report} · {i.location}</p>
              </li>
            ))}
          </ul>
        </div>
      )}
      {Object.keys(r.assumptions).length > 0 && (
        <div>
          <h4 className="mb-1 text-xs font-semibold tracking-wide text-muted uppercase">Assumptions applied</h4>
          <ul className="text-xs text-muted">{Object.entries(r.assumptions).map(([k, v]) => <li key={k}><code>{k}</code> = <span className="tnum">{v}</span> <Badge tone="warning">Editable</Badge></li>)}</ul>
        </div>
      )}
      {r.depends_on.length > 0 && <p className="text-xs text-muted">Depends on: {r.depends_on.join(", ")}</p>}
      {r.result_usd != null && (
        <div>
          <h4 className="mb-1 text-xs font-semibold tracking-wide text-muted uppercase">Result <Badge tone="accent">Calculated</Badge></h4>
          <dl className="grid grid-cols-[max-content_1fr] gap-x-4 gap-y-1 text-xs">
            <dt className="text-subtle">Exact result</dt><dd className="tnum">{usd(r.result_usd)} USD</dd>
            <dt className="text-subtle">In USD billions (full precision)</dt><dd className="tnum">{r.result_billions} USD billions</dd>
            <dt className="text-subtle">Displayed</dt><dd className="tnum font-semibold">{r.result_billions_text}</dd>
            <dt className="text-subtle">Same amount in USD thousands</dt><dd className="tnum">{r.result_thousands_text} (the unit GNMA prints)</dd>
          </dl>
        </div>
      )}
      <p className="text-[11px] text-subtle">Assumptions version {version}</p>
    </div>
  );
}
