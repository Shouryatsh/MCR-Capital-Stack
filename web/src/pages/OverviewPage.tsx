import { Download } from "lucide-react";
import { Link } from "react-router-dom";
import { ActionButton } from "../components/Buttons";
import { DataTable, type Column } from "../components/DataTable";
import { Badge, GlassCard } from "../components/GlassCard";
import { KpiCard, type Delta } from "../components/KpiCard";
import { EmptyState, ErrorState, LoadingState } from "../components/States";
import { SourceCitation } from "../components/SourceCitation";
import { useApi, usePeriod } from "../lib/hooks";
import { direction, downloadCsv, fmtMm, fmtPct, fmtPp, fmtSignedPct, fmtSignedUsd, fmtDate, fmtUsd } from "../lib/format";
import type { EntitySeries, GnmaResponse, Meta, PeerRow, PeersResponse } from "../lib/types";
import { splitPublished } from "./GnmaPage";

export function narrative(p: PeersResponse, dec: number): string | null {
  const s = p.stats;
  if (!s) return null;
  let text = `${p.period}. ${s.have} of ${s.slots} benchmarks have data. ${s.top} has the highest CET1-based leverage ratio (${fmtPct(s.top_ratio, dec)}) and ${s.bottom} the lowest (${fmtPct(s.bottom_ratio, dec)}); the average is ${fmtPct(s.average, dec)}. `;
  if (s.primary) text += `${s.primary} ranks ${s.primary_rank} of ${s.primary_of} (percentile ${Math.round(s.primary_percentile ?? 0)}). `;
  if (s.have < s.slots) text += `${s.slots - s.have} benchmark slot(s) are not configured or have no data for this period, so rank and percentile cover ${s.have} entities only. `;
  return text + "All amounts are in $ millions.";
}

export function OverviewPage() {
  const { period } = usePeriod();
  const meta = useApi<Meta>("/meta");
  const peers = useApi<PeersResponse>(period ? `/peers?period=${encodeURIComponent(period)}` : meta.loading ? null : "/peers");
  const dec = meta.data?.ratio_decimals ?? 2;
  const primaryRow = peers.data?.rows.find((r) => r.name === peers.data?.stats?.primary);
  const primarySeries = useApi<EntitySeries>(primaryRow ? `/entities/${encodeURIComponent(primaryRow.provider)}/series` : null);
  const gnma = useApi<GnmaResponse>("/gnma");

  if ((peers.loading && !peers.data) || (meta.loading && !meta.data)) return <LoadingState label="Loading overview" />;
  if (peers.error) return <ErrorState error={peers.error} onRetry={peers.reload} />;
  const p = peers.data;
  if (!p || !p.period) return <EmptyState title="No data yet">Ingest a disclosure from Uploads or fetch the GSE disclosures, then refresh.</EmptyState>;

  const s = p.stats;
  const pts = primarySeries.data?.series ?? [];
  const idx = pts.findIndex((x) => x.period === p.period);
  const cur = idx >= 0 ? pts[idx] : undefined;
  const ratioDelta: Delta | null = cur && cur.previous_period && cur.ratio_change != null
    ? { abs: fmtPp(cur.ratio_change, dec), direction: direction(cur.ratio_change), label: `vs ${cur.previous_period}`, tone: "auto" } : null;
  const g = gnma.data?.series[gnma.data.series.length - 1];
  const gy = g?.yoy;

  const text = narrative(p, dec);
  const columns: Column<PeerRow>[] = [
    { key: "slot", header: "Slot", numeric: true },
    { key: "name", header: "Benchmark", sticky: true, render: (r) => r.name || <span className="text-subtle">(not configured)</span> },
    { key: "period", header: "Period", value: (r) => r.period || p.period },
    { key: "status", header: "Status", render: (r) => <Badge tone={r.status === "ok" ? "positive" : "neutral"}>{r.status}</Badge> },
    { key: "cet1_mm", header: "CET1 amount ($ millions)", numeric: true, render: (r) => fmtMm(r.cet1_mm) },
    { key: "ata_mm", header: "Adj. total assets ($ millions)", numeric: true, render: (r) => fmtMm(r.ata_mm) },
    { key: "ratio", header: "Ratio (%)", numeric: true, render: (r) => fmtPct(r.ratio, dec) },
    { key: "ratio_dec", header: "Ratio (decimal)", numeric: true, value: (r) => r.ratio, render: (r) => (r.ratio == null ? "—" : r.ratio.toFixed(dec + 4)) },
    { key: "rank", header: "Rank", numeric: true, render: (r) => r.rank ?? "—" },
    { key: "percentile", header: "Percentile", numeric: true, render: (r) => (r.percentile == null ? "—" : Math.round(r.percentile)) },
    { key: "cet1_src", header: "CET1 provenance", value: (r) => r.cet1_src?.source_file, className: "min-w-64 whitespace-normal", render: (r) => <SourceCitation o={r.cet1_src} /> },
    { key: "ata_src", header: "ATA provenance", value: (r) => r.ata_src?.source_file, className: "min-w-64 whitespace-normal", render: (r) => <SourceCitation o={r.ata_src} /> },
    { key: "failed", header: "Failed checks", value: (r) => r.failed_checks.join(", "), render: (r) => (r.failed_checks.length ? <Badge tone="negative">{r.failed_checks.join(", ")}</Badge> : "—") },
  ];

  return (
    <div className="space-y-5">
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <KpiCard accent="teal" title={`${s?.primary ?? "Primary entity"} · CET1 ratio`} value={fmtPct(cur?.ratio ?? primaryRow?.ratio, dec)}
          caption={`CET1 ÷ adjusted total assets · ${p.period}`} delta={ratioDelta} spark={pts.map((x) => x.ratio * 100)} sparkLabel={`${s?.primary} ratio history`} />
        <KpiCard accent="violet" title="Peer average ratio" value={fmtPct(s?.average, dec)}
          caption={s ? `High ${s.top} ${fmtPct(s.top_ratio, dec)} · Low ${s.bottom} ${fmtPct(s.bottom_ratio, dec)}` : undefined} />
        <KpiCard accent="blue" title="Primary entity rank" value={s?.primary_rank ? `${s.primary_rank} of ${s.primary_of}` : "—"}
          caption={s ? `${s.have} of ${s.slots} slots have data · percentile ${Math.round(s.primary_percentile ?? 0)}` : undefined} />
        {g && (
          <KpiCard accent="emerald" title="GNMA max. exposure to loss" value={splitPublished(g.total_published)[0]}
            caption={<>FY{g.fiscal_year} · {fmtDate(g.reporting_date)} · {splitPublished(g.total_published)[1]}<br />= {fmtUsd(g.total_usd)}</>}
            delta={gy ? { abs: fmtSignedUsd(gy.total_abs_usd), pct: fmtSignedPct(gy.total_pct), direction: direction(gy.total_abs_usd), tone: "neutral", label: `vs FY${gy.prior_fiscal_year}` } : null}
            spark={gnma.data!.series.map((f) => f.total_usd / 1e9)} sparkLabel="GNMA total exposure history"
            footer={<Link to="/source-values?entity=gnma" className="text-aurora-cyan hover:underline">Open GNMA source values →</Link>} />
        )}
      </div>

      {text && (
        <GlassCard as="section" className="border-l-2 border-l-aurora-teal p-4 text-sm leading-relaxed text-muted" aria-label="Narrative summary">
          <p>{text.split(/^(\S+\.)/).filter(Boolean).map((part, i) => (i === 0 ? <strong key={i} className="text-fg">{part} </strong> : part))}</p>
        </GlassCard>
      )}

      <section aria-label="Summary table" className="space-y-2">
        <h2 className="text-base font-semibold">Benchmark summary · {p.period}</h2>
        <DataTable<PeerRow> caption={`Benchmark summary for ${p.period}`} rows={p.rows} rowKey={(r) => String(r.slot)} columns={columns} filterable
          filterPlaceholder="Filter benchmarks…" initialSort={{ key: "slot", dir: "asc" }} maxHeight="32rem"
          toolbar={<ActionButton onClick={() => downloadCsv(`mcr_summary_${p.period}.csv`, p.rows.map((r) => ({
            Slot: r.slot, Benchmark: r.name || "(not configured)", Period: r.period || p.period, Status: r.status,
            "CET1 amount ($ millions)": r.cet1_mm, "Adjusted total assets ($ millions)": r.ata_mm,
            "Ratio (%)": r.ratio == null ? "" : (r.ratio * 100).toFixed(dec), "Ratio (decimal)": r.ratio == null ? "" : r.ratio.toFixed(dec + 4), Units: "millions",
            Rank: r.rank, Percentile: r.percentile == null ? "" : Math.round(r.percentile),
            "CET1 provenance": r.cet1_src ? `${r.cet1_src.source_file}, ${r.cet1_src.location} · ${r.cet1_src.table_name} · ${r.cet1_src.field_label}` : "",
            "ATA provenance": r.ata_src ? `${r.ata_src.source_file}, ${r.ata_src.location} · ${r.ata_src.table_name} · ${r.ata_src.field_label}` : "",
            "Failed checks": r.failed_checks.join(", ") })))}>
            <Download className="size-4" aria-hidden="true" /> Download summary CSV
          </ActionButton>} />
      </section>
    </div>
  );
}
