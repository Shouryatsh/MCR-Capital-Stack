import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Badge } from "../components/GlassCard";
import { DataTable, type Column } from "../components/DataTable";
import { axisProps, CHART, FinancialChart, GlassTooltip } from "../components/FinancialChart";
import { EmptyState, ErrorState, LoadingState } from "../components/States";
import { useApi, usePeriod } from "../lib/hooks";
import { fmtMm, fmtPct } from "../lib/format";
import type { Meta, PeerRow, PeersResponse } from "../lib/types";
import { streamlitUrl } from "../components/nav";

export function SummaryPage() {
  const { period } = usePeriod();
  const meta = useApi<Meta>("/meta");
  const peers = useApi<PeersResponse>(period ? `/peers?period=${encodeURIComponent(period)}` : meta.loading ? null : "/peers");
  const dec = meta.data?.ratio_decimals ?? 2;

  if (peers.loading && !peers.data) return <LoadingState label="Loading summary" cards={0} />;
  if (peers.error) return <ErrorState error={peers.error} onRetry={peers.reload} />;
  const p = peers.data;
  if (!p || !p.period) return <EmptyState title="No data yet" />;

  const have = p.rows.filter((r) => r.ratio != null).sort((a, b) => (b.ratio as number) - (a.ratio as number));
  const bars = have.map((r) => ({ name: r.name, pct: (r.ratio as number) * 100, r }));
  const primary = p.stats?.primary;

  const columns: Column<PeerRow>[] = [
    { key: "slot", header: "Slot", numeric: true },
    { key: "name", header: "Benchmark", sticky: true, render: (r) => r.name || <span className="text-subtle">—</span> },
    { key: "status", header: "Status", render: (r) => <Badge tone={r.status === "ok" ? "positive" : "neutral"}>{r.status}</Badge> },
    { key: "rank", header: "Rank", numeric: true, value: (r) => r.rank, render: (r) => (r.rank ? `${r.rank} of ${r.of}` : "—") },
    { key: "percentile", header: "Percentile", numeric: true, render: (r) => (r.percentile == null ? "—" : Math.round(r.percentile)) },
    { key: "ratio", header: "Ratio", numeric: true, render: (r) => (r.ratio == null ? "—" : `${fmtPct(r.ratio, dec)} (${r.ratio.toFixed(dec + 2)})`) },
    { key: "cet1_mm", header: "CET1 ($ millions)", numeric: true, render: (r) => fmtMm(r.cet1_mm) },
    { key: "ata_mm", header: "Adj. total assets ($ millions)", numeric: true, render: (r) => fmtMm(r.ata_mm) },
  ];

  return (
    <div className="space-y-5">
      <p className="text-sm text-muted">
        {have.length} of {p.rows.length} benchmark slots have data for {p.period}. Unconfigured slots are set in{" "}
        <a className="text-aurora-cyan hover:underline" href={streamlitUrl()} target="_blank" rel="noreferrer">Settings → Benchmarks<span className="sr-only"> (opens the Streamlit app)</span></a>.
      </p>
      {bars.length > 0 && (
        <FinancialChart title="CET1-based leverage ratio by benchmark" description={`Ranked highest to lowest · ${p.period}`} height={320}
          summary={`Ratios for ${p.period}: ${bars.map((b) => `${b.name} ${fmtPct(b.r.ratio, dec)}`).join(", ")}.`}>
          <ResponsiveContainer width="100%" height="100%" minWidth={0}>
            <BarChart data={bars} margin={{ top: 8, right: 16, bottom: 0, left: 0 }}>
              <CartesianGrid stroke={CHART.grid} vertical={false} />
              <XAxis dataKey="name" {...axisProps} />
              <YAxis {...axisProps} tickFormatter={(v: number) => `${v}%`} width={48} />
              <Tooltip cursor={{ fill: "rgba(148,163,205,0.08)" }} content={<GlassTooltip format={(v) => `${v.toFixed(dec)}%`}
                footer={(row) => { const r = (row as { r: PeerRow }).r; return <>CET1 {fmtMm(r.cet1_mm)} · Adj. assets {fmtMm(r.ata_mm)} ($ millions)<br />CET1 src: {r.cet1_src?.source_file}, {r.cet1_src?.location}</>; }} />} />
              <Bar dataKey="pct" name="Ratio" radius={[6, 6, 0, 0]} maxBarSize={72}>
                {bars.map((b) => <Cell key={b.name} fill={b.name === primary ? CHART.teal : CHART.blue} />)}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </FinancialChart>
      )}
      <DataTable<PeerRow> caption={`Benchmark slots for ${p.period}`} rows={p.rows} rowKey={(r) => String(r.slot)} columns={columns} initialSort={{ key: "slot", dir: "asc" }} />
      <p className="text-xs text-subtle">Rank 1 = highest ratio. Percentile = share of benchmarks with data whose ratio is at or below this one.</p>
    </div>
  );
}
