import { Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, ReferenceDot, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Download, Info, Loader2, RefreshCw } from "lucide-react";
import { useMemo, useState } from "react";
import { ActionButton } from "../components/Buttons";
import { DataTable, type Column } from "../components/DataTable";
import { axisProps, CHART, FinancialChart, GlassTooltip } from "../components/FinancialChart";
import { Badge, cx, GlassCard } from "../components/GlassCard";
import { KpiCard, type Delta } from "../components/KpiCard";
import { EmptyState, ErrorState, LoadingState } from "../components/States";
import { GnmaCitation } from "../components/SourceCitation";
import { ValidationPanel, ValidationStatus } from "../components/ValidationPanel";
import { useGnmaRefresh } from "../lib/gnmaRefresh";
import { useApi } from "../lib/hooks";
import { direction, downloadCsv, fmtBillions, fmtDate, fmtSignedPct, fmtSignedUsd, fmtUsd } from "../lib/format";
import type { GnmaFigure, GnmaResponse } from "../lib/types";

/** "$2,613,623,651 (USD thousands)" -> ["$2,613,623,651", "USD thousands"] */
export const splitPublished = (s: string): [string, string] => {
  const m = /^(.*?) \((USD [a-z]+)\)$/.exec(s);
  return m ? [m[1], m[2]] : [s, ""];
};

function yoyDelta(f: GnmaFigure, part: "total" | "mbs" | "commitments"): Delta | null {
  const y = f.yoy;
  if (!y) return null;
  const abs = part === "total" ? y.total_abs_usd : part === "mbs" ? y.mbs_abs_usd : y.commitments_abs_usd;
  const pct = part === "total" ? y.total_pct : part === "mbs" ? y.mbs_pct : y.commitments_pct;
  return { abs: fmtSignedUsd(abs), pct: fmtSignedPct(pct), direction: direction(abs), tone: "neutral",
    label: `vs FY${y.prior_fiscal_year}${y.rounded ? " (rounded source figures)" : ""}` };
}

export function GnmaPage() {
  const { data, error, loading, reload } = useApi<GnmaResponse>("/gnma");
  const refresh = useGnmaRefresh();
  const [from, setFrom] = useState<number | null>(null);
  const [view, setView] = useState<"total" | "components">("components");

  const series = data?.series ?? [];
  const shown = useMemo(() => series.filter((f) => from == null || f.fiscal_year >= from), [series, from]);
  const latest = series[series.length - 1];

  if (loading && !data) return <LoadingState label="Loading GNMA exposure" />;
  if (error) return <ErrorState error={error} onRetry={reload} />;
  if (!data || !latest)
    return (
      <EmptyState title="No GNMA data yet">
        Fetch the official English annual reports to build the history.
        <div className="mt-3 flex justify-center"><RefreshButton refresh={refresh} /></div>
      </EmptyState>
    );

  const [headline, unit] = splitPublished(latest.total_published);
  const prior = series.find((f) => f.fiscal_year === latest.fiscal_year - 1);
  const roundedYears = series.filter((f) => f.precision_usd > 1000).map((f) => f.fiscal_year);
  const rows = shown.map((f) => ({
    fy: `FY${f.fiscal_year}`, date: f.reporting_date, mbs: f.mbs_usd / 1e9, commitments: f.commitments_usd / 1e9, total: f.total_usd / 1e9, f,
  }));
  const yoyRows = shown.filter((f) => f.yoy?.total_pct != null).map((f) => ({ fy: `FY${f.fiscal_year}`, pct: f.yoy!.total_pct as number, f }));

  const columns: Column<GnmaFigure>[] = [
    { key: "fiscal_year", header: "Fiscal year", sticky: true, render: (f) => (
      <span className="font-medium">FY{f.fiscal_year} {f.latest && <Badge tone="accent">Latest</Badge>}{f.role === "comparative" && <Badge tone="neutral" title="This year's own report has no extractable table; the figure comes from the next year's report.">comparative</Badge>}</span>) },
    { key: "reporting_date", header: "Reporting date", className: "whitespace-nowrap", render: (f) => fmtDate(f.reporting_date) },
    { key: "mbs_usd", header: "Outstanding MBS (USD)", numeric: true, render: (f) => f.mbs_usd_text },
    { key: "commitments_usd", header: "MBS commitments (USD)", numeric: true, render: (f) => f.commitments_usd_text },
    { key: "total_usd", header: "Total max. exposure (USD)", numeric: true, render: (f) => <strong className="text-fg">{f.total_usd_text}</strong> },
    { key: "published", header: "Total as published", value: (f) => f.total_usd, numeric: true, render: (f) => f.total_published },
    { key: "yoy_abs", header: "YoY change (USD)", numeric: true, value: (f) => f.yoy?.total_abs_usd, render: (f) => (f.yoy ? fmtSignedUsd(f.yoy.total_abs_usd) : "—") },
    { key: "yoy_pct", header: "YoY %", numeric: true, value: (f) => f.yoy?.total_pct, render: (f) => (f.yoy ? fmtSignedPct(f.yoy.total_pct) : "—") },
    { key: "basis", header: "Total basis", value: (f) => (f.reported_total_usd != null ? "printed" : "computed"), render: (f) => (f.reported_total_usd != null ? "Printed in report" : "Computed (MBS + commitments)") },
    { key: "source_report", header: "Source report", render: (f) => <GnmaLink f={f} /> },
    { key: "page", header: "Page · note", value: (f) => f.pdf_page, className: "min-w-64 whitespace-normal", render: (f) => (
      <span className="text-xs text-muted">PDF p.{f.pdf_page}{f.printed_page && ` (printed ${f.printed_page})`}{f.note && <><br />{f.note}</>}</span>) },
    { key: "check", header: "Validation", value: (f) => (f.flags.some((x) => x.startsWith("WARN")) ? 1 : 0), render: (f) => {
      const warn = f.flags.filter((x) => x.startsWith("WARN")).map((x) => x.replace("WARN: ", ""));
      return warn.length ? <Badge tone="warning" title={warn.join("; ")}>Check</Badge> : <Badge tone="positive">Pass</Badge>; } },
  ];

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center gap-3">
        <ValidationStatus checks={data.validation} />
        <label className="flex items-center gap-2 text-xs text-muted">
          From fiscal year
          <select value={from ?? ""} onChange={(e) => setFrom(e.target.value ? Number(e.target.value) : null)} aria-label="From fiscal year"
            className="rounded-lg border border-white/10 bg-ink-900/80 px-2 py-1.5 text-sm text-fg">
            <option value="">All ({series[0].fiscal_year}–{latest.fiscal_year})</option>
            {series.map((f) => <option key={f.fiscal_year} value={f.fiscal_year}>FY{f.fiscal_year}</option>)}
          </select>
        </label>
        <div className="ml-auto flex flex-wrap items-center gap-2">
          <ActionButton onClick={() => downloadCsv("gnma_max_exposure_to_loss.csv", series.map((f) => ({
            fiscal_year: f.fiscal_year, reporting_date: f.reporting_date, outstanding_mbs_usd: f.mbs_usd, outstanding_mbs_commitments_usd: f.commitments_usd,
            total_max_exposure_to_loss_usd: f.total_usd, published_units: f.units, source_report: f.source_report, source_url: f.source_url,
            pdf_page: f.pdf_page, printed_page: f.printed_page, note: f.note })))}>
            <Download className="size-4" aria-hidden="true" /> Download CSV
          </ActionButton>
          <RefreshButton refresh={refresh} />
        </div>
      </div>
      {refresh.error && <ErrorState error={new Error(refresh.error)} />}
      {refresh.status && !refresh.running && !refresh.error && refresh.status.finished && (
        <p role="status" className="text-xs text-pos">GNMA refresh finished: {refresh.status.with_figures} of {refresh.status.reports} annual reports yielded figures.</p>
      )}

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <KpiCard featured accent="teal" title="Total Maximum Exposure to Loss"
          value={headline}
          caption={<>FY{latest.fiscal_year} · as of {fmtDate(latest.reporting_date)} · {unit} as published<br />= {fmtUsd(latest.total_usd)}</>}
          delta={yoyDelta(latest, "total")}
          spark={series.map((f) => f.total_usd / 1e9)} sparkLabel={`Total exposure FY${series[0].fiscal_year} to FY${latest.fiscal_year}`}
          footer={<GnmaCitation f={latest} />} />
        <KpiCard accent="blue" title="Outstanding MBS" value={latest.mbs_published} caption={`${unit} as published · ${fmtUsd(latest.mbs_usd)}`}
          delta={yoyDelta(latest, "mbs")} spark={series.map((f) => f.mbs_usd / 1e9)} sparkLabel="Outstanding MBS history" />
        <KpiCard accent="violet" title="Outstanding MBS commitments" value={latest.commitments_published} caption={`${unit} as published · ${fmtUsd(latest.commitments_usd)}`}
          delta={yoyDelta(latest, "commitments")} spark={series.map((f) => f.commitments_usd / 1e9)} sparkLabel="Outstanding MBS commitments history" />
      </div>
      {!prior && <p className="flex items-center gap-1.5 text-xs text-subtle"><Info className="size-3.5" aria-hidden="true" /> No FY{latest.fiscal_year - 1} figure is available, so no year-over-year change is shown.</p>}

      <ReferenceChecks data={data} />

      <FinancialChart
        title="Historical exposure"
        description="USD billions. Hover for the exact dollar amounts, reporting date and source."
        height={340}
        summary={`Total Maximum Exposure to Loss rose from ${fmtBillions(shown[0].total_usd)} in FY${shown[0].fiscal_year} to ${fmtBillions(latest.total_usd)} in FY${latest.fiscal_year}. The full data is in the table below.`}
        actions={
          <div role="group" aria-label="Chart view" className="inline-flex rounded-lg border border-white/10 p-0.5 text-xs">
            {(["components", "total"] as const).map((v) => (
              <button key={v} type="button" aria-pressed={view === v} onClick={() => setView(v)}
                className={cx("rounded-md px-2.5 py-1", view === v ? "bg-aurora-teal/20 text-fg" : "text-muted hover:text-fg")}>
                {v === "total" ? "Total" : "Components"}
              </button>
            ))}
          </div>
        }
      >
        <ResponsiveContainer width="100%" height="100%" minWidth={0}>
          <AreaChart data={rows} margin={{ top: 16, right: 16, bottom: 0, left: 0 }}>
            <defs>
              {[["gMbs", CHART.blue], ["gCom", CHART.violet], ["gTot", CHART.teal]].map(([id, c]) => (
                <linearGradient key={id} id={id} x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={c} stopOpacity={0.55} /><stop offset="100%" stopColor={c} stopOpacity={0.04} />
                </linearGradient>
              ))}
            </defs>
            <CartesianGrid stroke={CHART.grid} vertical={false} />
            <XAxis dataKey="fy" {...axisProps} />
            <YAxis {...axisProps} tickFormatter={(v: number) => `$${v.toLocaleString("en-US")}B`} width={72} />
            <Tooltip content={<GlassTooltip format={(v) => fmtBillions(v * 1e9)}
              title={(l, row) => `${l} · as of ${fmtDate((row as { date: string }).date)}`}
              footer={(row) => { const f = (row as { f: GnmaFigure }).f; return <>Total {f.total_usd_text}<br />MBS {f.mbs_usd_text}<br />Commitments {f.commitments_usd_text}<br />{f.source_report}, PDF p.{f.pdf_page}</>; }} />} />
            {view === "components" ? (
              <>
                <Area type="monotone" stackId="1" dataKey="mbs" name="Outstanding MBS" stroke={CHART.blue} strokeWidth={2} fill="url(#gMbs)" />
                <Area type="monotone" stackId="1" dataKey="commitments" name="MBS commitments" stroke={CHART.violet} strokeWidth={2} fill="url(#gCom)" />
              </>
            ) : (
              <Area type="monotone" dataKey="total" name="Total exposure" stroke={CHART.teal} strokeWidth={2.5} fill="url(#gTot)" />
            )}
            {rows.length > 0 && <ReferenceDot x={rows[rows.length - 1].fy} y={rows[rows.length - 1].total} r={5} fill={CHART.teal} stroke="#050914" strokeWidth={2} label={{ value: "Latest", position: "top", fill: CHART.axis, fontSize: 11 }} ifOverflow="extendDomain" />}
          </AreaChart>
        </ResponsiveContainer>
      </FinancialChart>
      {roundedYears.length > 0 && (
        <p className="flex items-start gap-1.5 text-xs text-subtle"><Info className="mt-0.5 size-3.5 shrink-0" aria-hidden="true" />
          FY{roundedYears[0]}–FY{roundedYears[roundedYears.length - 1]} figures are published rounded to $0.1 billion or $1 billion; later years are exact to the thousand dollars. Both are shown as published.</p>
      )}

      {yoyRows.length > 0 && (
        <FinancialChart title="Year-over-year change in total exposure" description="Percent change versus the prior fiscal year (consecutive years only)." height={240}
          summary={`Year-over-year change in Total Maximum Exposure to Loss, from ${yoyRows[0].fy} to ${yoyRows[yoyRows.length - 1].fy}. Latest: ${fmtSignedPct(yoyRows[yoyRows.length - 1].pct)}.`}>
          <ResponsiveContainer width="100%" height="100%" minWidth={0}>
            <BarChart data={yoyRows} margin={{ top: 8, right: 16, bottom: 0, left: 0 }}>
              <CartesianGrid stroke={CHART.grid} vertical={false} />
              <XAxis dataKey="fy" {...axisProps} />
              <YAxis {...axisProps} tickFormatter={(v: number) => `${v}%`} width={48} />
              <ReferenceLine y={0} stroke="rgba(148,163,205,0.4)" />
              <Tooltip cursor={{ fill: "rgba(148,163,205,0.08)" }} content={<GlassTooltip format={(v) => fmtSignedPct(v)}
                footer={(row) => { const f = (row as { f: GnmaFigure }).f; return <>{fmtSignedUsd(f.yoy!.total_abs_usd)} vs FY{f.yoy!.prior_fiscal_year}</>; }} />} />
              <Bar dataKey="pct" name="YoY change" radius={[4, 4, 0, 0]} maxBarSize={28}>
                {yoyRows.map((r) => <Cell key={r.fy} fill={r.pct >= 0 ? CHART.cyan : CHART.amber} />)}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </FinancialChart>
      )}

      <section aria-label="Historical data table" className="space-y-2">
        <h2 className="text-base font-semibold">Historical data</h2>
        <DataTable<GnmaFigure> caption="GNMA Maximum Exposure to Loss by fiscal year" rows={shown} rowKey={(f) => String(f.fiscal_year)} columns={columns}
          filterable filterPlaceholder="Filter by year, report or note…" initialSort={{ key: "fiscal_year", dir: "asc" }} maxHeight="30rem"
          rowClassName={(f) => (f.latest ? "bg-aurora-teal/5" : undefined)} />
      </section>

      <ValidationPanel checks={data.validation} reconciliation={data.reconciliation} gaps={data.gaps} />
      <p className="text-xs text-subtle">
        Source: <a className="text-aurora-cyan hover:underline" href={data.source.index_url} target="_blank" rel="noreferrer">Ginnie Mae annual reports (official, English)<span className="sr-only"> (opens ginniemae.gov)</span></a>.
        Total Maximum Exposure to Loss = Outstanding MBS + Outstanding MBS commitments, from the Notes to the Financial Statements. Missing years are flagged, never estimated.
      </p>
    </div>
  );
}

function GnmaLink({ f }: { f: GnmaFigure }) {
  return <a href={f.source_url} target="_blank" rel="noreferrer" className="text-aurora-cyan hover:underline">{f.source_report}<span className="sr-only"> (opens the official PDF)</span></a>;
}

function ReferenceChecks({ data }: { data: GnmaResponse }) {
  const items = Object.entries(data.reference).sort(([a], [b]) => Number(b) - Number(a)).map(([fy, ref]) => {
    const f = data.series.find((s) => s.fiscal_year === Number(fy) && s.role === "current");
    return { fy, ref, f, ok: !!f && f.total_usd === ref.total && f.mbs_usd === ref.mbs && f.commitments_usd === ref.commitments };
  });
  return (
    <GlassCard as="section" variant="data" className="p-4" aria-label="Reference value validation">
      <h2 className="text-sm font-semibold">Validated reference values (2023 Annual Report, Notes p. A-20)</h2>
      <ul className="mt-2 grid gap-2 sm:grid-cols-2">
        {items.map(({ fy, f, ok }) => (
          <li key={fy} className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-white/5 bg-ink-900/60 px-3 py-2 text-sm">
            <span className="text-muted">{f ? fmtDate(f.reporting_date) : `FY${fy}`}</span>
            <span className="tnum font-semibold">{f ? splitPublished(f.total_published)[0] : "—"}</span>
            <Badge tone={ok ? "positive" : "negative"}>{ok ? "Matches reference" : "Does not match"}</Badge>
          </li>
        ))}
      </ul>
    </GlassCard>
  );
}

function RefreshButton({ refresh }: { refresh: ReturnType<typeof useGnmaRefresh> }) {
  return (
    <ActionButton onClick={refresh.start} disabled={refresh.running} title="Download the official annual reports from ginniemae.gov and re-extract (first run is large)">
      {refresh.running ? <Loader2 className="size-4 animate-spin" aria-hidden="true" /> : <RefreshCw className="size-4" aria-hidden="true" />}
      {refresh.running ? "Fetching reports…" : "Fetch GNMA reports"}
    </ActionButton>
  );
}
