import { Info } from "lucide-react";
import { Link } from "react-router-dom";
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { useApi } from "../lib/hooks";
import { direction, fmtDate, fmtSignedPct } from "../lib/format";
import type { BenchResult, BenchSummary, BenchmarksResponse } from "../lib/types";
import { DataTable, type Column } from "./DataTable";
import { axisProps, CHART, FinancialChart, GlassTooltip } from "./FinancialChart";
import { Badge, GlassCard } from "./GlassCard";
import { KpiCard } from "./KpiCard";
import { ErrorState, LoadingState } from "./States";

export const STATUS: Record<string, { tone: "positive" | "neutral" | "warning" | "negative"; label: string }> = {
  ok: { tone: "positive", label: "Calculated" },
  unconfirmed: { tone: "warning", label: "Requires confirmation" },
  missing_input: { tone: "warning", label: "Missing input" },
  invalid_assumption: { tone: "negative", label: "Invalid definition" },
  error: { tone: "negative", label: "Error" },
};

export const StatusBadge = ({ status }: { status: string }) => <Badge tone={STATUS[status]?.tone ?? "neutral"}>{STATUS[status]?.label ?? status}</Badge>;

/** Executive view of the GNMA-adjusted benchmarks. Every figure is the server's USD-billions text; nothing is recalculated here. */
export function BenchmarkResults() {
  const { data, error, loading, reload } = useApi<BenchmarksResponse>("/benchmarks");
  if (loading && !data) return <LoadingState label="Loading benchmark results" cards={2} />;
  if (error) return <ErrorState error={error} onRetry={reload} />;
  if (!data) return null;

  const live = data.summary.filter((s) => s.latest);
  const pending = data.summary.filter((s) => s.status !== "confirmed").length;
  const history = (n: number) => data.results.filter((r) => r.number === n && r.status === "ok");
  const years = [...new Set(live.flatMap((s) => history(s.number).map((r) => r.fiscal_year)))].sort();
  const rows = years.map((fy) => {
    const row: Record<string, unknown> = { fy: `FY${fy}` };
    for (const s of live) {
      const r = history(s.number).find((x) => x.fiscal_year === fy);
      row[`b${s.number}`] = r ? Number(r.result_billions) : null;
      row[`b${s.number}__text`] = r?.result_billions_text;
      row[`b${s.number}__date`] = r?.reporting_date;
    }
    return row;
  });

  const columns: Column<BenchSummary>[] = [
    { key: "number", header: "#", numeric: true },
    { key: "name", header: "Benchmark", sticky: true, className: "min-w-52 whitespace-normal font-medium" },
    { key: "status", header: "Status", value: (s) => s.status, render: (s) => <StatusBadge status={s.latest ? "ok" : s.status === "confirmed" ? "missing_input" : "unconfirmed"} /> },
    { key: "period", header: "Latest period", value: (s) => s.latest?.fiscal_year, render: (s) => (s.latest ? `FY${s.latest.fiscal_year} · ${fmtDate(s.latest.reporting_date)}` : "—") },
    { key: "latest", header: "Latest result (USD billions)", numeric: true, value: (s) => (s.latest ? Number(s.latest.result_billions) : null),
      render: (s) => (s.latest ? <strong>{s.latest.result_billions_text}</strong> : <span className="text-subtle">—</span>) },
    { key: "prior", header: "Prior year (USD billions)", numeric: true, value: (s) => (s.prior ? Number(s.prior.result_billions) : null), render: (s) => s.prior?.result_billions_text ?? "—" },
    { key: "yoy", header: "YoY change (USD billions)", numeric: true, value: (s) => (s.yoy ? Number(s.yoy.abs_usd) : null), render: (s) => s.yoy?.abs_billions_text ?? "—" },
    { key: "yoypct", header: "YoY %", numeric: true, value: (s) => s.yoy?.pct, render: (s) => (s.yoy ? fmtSignedPct(s.yoy.pct) : "—") },
    { key: "formula", header: "Formula", className: "min-w-56 whitespace-normal", render: (s) => (s.formula ? <code className="text-xs text-aurora-cyan">{s.formula}</code> : <span className="text-xs text-subtle">not defined</span>) },
  ];

  return (
    <section aria-label="GNMA-adjusted benchmarks" className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-2">
        <div>
          <h2 className="text-lg font-semibold">GNMA-adjusted benchmarks <span className="font-normal text-muted">· USD (billions)</span></h2>
          <p className="text-xs text-subtle">Calculated from GNMA Total Maximum Exposure to Loss at full precision, then converted to billions once for display.</p>
        </div>
        <Link to="/calculations" className="text-sm text-aurora-cyan hover:underline">Inspect every calculation →</Link>
      </div>

      {pending > 0 && (
        <GlassCard role="note" className="flex gap-2 border-warn/30 p-3 text-sm text-muted">
          <Info className="mt-0.5 size-4 shrink-0 text-warn" aria-hidden="true" />
          <span>{live.length} of {data.summary.length} benchmarks have a confirmed definition. Benchmarks {data.summary.filter((s) => s.status !== "confirmed").map((s) => s.number).join(", ")} require business confirmation and show no result rather than an invented one.</span>
        </GlassCard>
      )}

      {live.length > 0 && (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {live.map((s) => {
            const l = s.latest as BenchResult;
            return (
              <KpiCard key={s.number} featured={live.length === 1} accent="teal" title={`Benchmark ${s.number} · ${s.name}`} value={l.result_billions_text}
                caption={<>FY{l.fiscal_year} · as of {fmtDate(l.reporting_date)} · USD (billions)<br />Full precision {l.result_billions} USD billions</>}
                delta={s.yoy ? { abs: s.yoy.abs_billions_text, pct: fmtSignedPct(s.yoy.pct), direction: direction(Number(s.yoy.abs_usd)), tone: "neutral", label: `vs FY${s.yoy.prior_fiscal_year}` } : null}
                spark={history(s.number).map((r) => Number(r.result_billions))} sparkLabel={`${s.name} history`}
                footer={<code className="text-aurora-cyan">{s.formula}</code>} />
            );
          })}
        </div>
      )}

      {rows.length > 0 && (
        <FinancialChart title="Benchmark history" description="USD (billions). Hover for the reporting date and the value as calculated." height={300}
          summary={`${live.map((s) => `Benchmark ${s.number} ${s.name} rose from ${history(s.number)[0].result_billions_text} in FY${history(s.number)[0].fiscal_year} to ${s.latest!.result_billions_text} in FY${s.latest!.fiscal_year}`).join("; ")}. The comparison table lists every value.`}>
          <ResponsiveContainer width="100%" height="100%" minWidth={0}>
            <AreaChart data={rows} margin={{ top: 12, right: 16, bottom: 0, left: 0 }}>
              <defs>
                <linearGradient id="gBench" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor={CHART.teal} stopOpacity={0.5} /><stop offset="100%" stopColor={CHART.teal} stopOpacity={0.04} /></linearGradient>
              </defs>
              <CartesianGrid stroke={CHART.grid} vertical={false} />
              <XAxis dataKey="fy" {...axisProps} />
              <YAxis {...axisProps} width={64} tickFormatter={(v: number) => `$${v.toLocaleString("en-US")}B`} label={{ value: "USD (billions)", angle: -90, position: "insideLeft", fill: CHART.axis, fontSize: 11, dx: 6 }} />
              <Tooltip content={<GlassTooltip format={(v, p) => String((p.payload as Record<string, unknown>)?.[`${p.dataKey}__text`] ?? v)} title={(l, row) => `${l} · as of ${fmtDate(String(row?.["b1__date"] ?? ""))}`} />} />
              {live.map((s, i) => <Area key={s.number} type="monotone" dataKey={`b${s.number}`} name={`B${s.number} ${s.name}`} stroke={CHART.series[i % CHART.series.length]} strokeWidth={2.5} fill={i === 0 ? "url(#gBench)" : "none"} connectNulls />)}
            </AreaChart>
          </ResponsiveContainer>
        </FinancialChart>
      )}

      <section aria-label="Benchmark comparison" className="space-y-2">
        <h3 className="text-base font-semibold">All 10 benchmarks <span className="font-normal text-muted">· USD (billions)</span></h3>
        <DataTable<BenchSummary> caption="Comparison of the ten GNMA-adjusted benchmarks in USD billions" rows={data.summary} rowKey={(s) => String(s.number)} columns={columns} filterable
          filterPlaceholder="Filter benchmarks…" initialSort={{ key: "number", dir: "asc" }} maxHeight="26rem" />
      </section>
    </section>
  );
}
