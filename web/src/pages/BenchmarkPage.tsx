import { AlertTriangle } from "lucide-react";
import { useContext, useEffect, useMemo, useState } from "react";
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "../lib/api";
import { BenchmarkResults } from "../components/BenchmarkResults";
import { DataTable, type Column } from "../components/DataTable";
import { axisProps, CHART, FinancialChart, GlassTooltip } from "../components/FinancialChart";
import { Badge, cx, GlassCard } from "../components/GlassCard";
import { KpiCard } from "../components/KpiCard";
import { EmptyState, ErrorState, LoadingState } from "../components/States";
import { SourceCitation } from "../components/SourceCitation";
import { RefreshContext, useApi } from "../lib/hooks";
import { direction, fmtMm, fmtPct, fmtPp } from "../lib/format";
import type { EntitiesResponse, EntitySeries, Meta, Provenance, SeriesPoint } from "../lib/types";

function ProvenanceBlock({ o, title }: { o: Provenance; title: string }) {
  const rows: [string, string][] = [
    ["source_file", o.source_file], ["sheet_or_table_name", o.table_name], ["row_identifier", o.row_identifier], ["field_label", o.field_label],
    ["raw_value", o.raw_value], ["parsed_value", o.parsed_value.toLocaleString("en-US")], ["units_detected", `${o.units_detected} (${o.units_source})`],
    ["value ($ millions)", fmtMm(o.value_mm)], ["location", o.location],
  ];
  return (
    <details className="glass-data group rounded-xl px-4 py-3 text-sm">
      <summary className="cursor-pointer font-medium marker:text-aurora-teal">Provenance: {title}</summary>
      <dl className="mt-3 grid grid-cols-[max-content_1fr] gap-x-4 gap-y-1 text-xs">
        {rows.map(([k, v]) => (<div key={k} className="contents"><dt className="text-subtle">{k}</dt><dd className="tnum break-all">{v}</dd></div>))}
      </dl>
      {o.source_url && <p className="mt-2 text-xs">Source URL: <a className="break-all text-aurora-cyan hover:underline" href={o.source_url} target="_blank" rel="noreferrer">{o.source_url}</a></p>}
    </details>
  );
}

/** Loads the ratio history of several entities in parallel (the compare overlay). */
function useSeriesMap(providers: string[]) {
  const { key } = useContext(RefreshContext);
  const [map, setMap] = useState<Record<string, SeriesPoint[]>>({});
  const joined = providers.join("\u0000");
  useEffect(() => {
    let live = true;
    Promise.all(providers.map((p) => api<EntitySeries>(`/entities/${encodeURIComponent(p)}/series`).then((r) => [p, r.series] as const).catch(() => [p, []] as const)))
      .then((pairs) => live && setMap(Object.fromEntries(pairs)));
    return () => { live = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [joined, key]);
  return map;
}

/** Benchmark tab: the GNMA-adjusted benchmark results (USD billions), then the entity view (the former Overview content). */
export function BenchmarkPage() {
  return (
    <div className="space-y-8">
      <BenchmarkResults />
      <section aria-label="Entity benchmark" className="space-y-5 border-t border-white/10 pt-6">
        <h2 className="text-lg font-semibold">Entity benchmark <span className="font-normal text-muted">· CET1 ÷ adjusted total assets ($ millions)</span></h2>
        <EntityBenchmark />
      </section>
    </div>
  );
}

function EntityBenchmark() {
  const meta = useApi<Meta>("/meta");
  const ents = useApi<EntitiesResponse>("/entities");
  const [chosen, setChosen] = useState<string | null>(null);
  const [compare, setCompare] = useState<string[] | null>(null);

  const providers = ents.data?.providers ?? [];
  const entity = chosen && providers.includes(chosen) ? chosen : ents.data?.primary ?? null;
  const others = providers.filter((p) => p !== entity);
  const compared = (compare ?? others.slice(0, 1)).filter((p) => others.includes(p));
  const series = useApi<EntitySeries>(entity ? `/entities/${encodeURIComponent(entity)}/series` : null);
  const map = useSeriesMap(entity ? [entity, ...compared] : []);
  const dec = meta.data?.ratio_decimals ?? 2;

  const chartRows = useMemo(() => {
    const names = entity ? [entity, ...compared] : [];
    const periods = [...new Set(names.flatMap((n) => (map[n] ?? []).map((x) => x.period)))].sort();
    return periods.map((period) => {
      const row: Record<string, unknown> = { period };
      for (const n of names) {
        const pt = map[n]?.find((x) => x.period === period);
        row[n] = pt ? pt.ratio * 100 : null;
        row[`${n}__pt`] = pt;
      }
      return row;
    });
  }, [map, entity, compared]);

  if ((ents.loading && !ents.data) || (meta.loading && !meta.data)) return <LoadingState label="Loading benchmark" />;
  if (ents.error) return <ErrorState error={ents.error} onRetry={ents.reload} />;
  if (!entity) return <EmptyState title="No data yet">Ingest a disclosure from Uploads or fetch the GSE disclosures, then refresh.</EmptyState>;
  if (series.error) return <ErrorState error={series.error} onRetry={series.reload} />;
  if (!series.data) return <LoadingState label={`Loading ${entity}`} />;

  const pts = series.data.series;
  const last = pts[pts.length - 1];
  const bad = pts.filter((p) => p.failed.length);

  const columns: Column<SeriesPoint>[] = [
    { key: "period", header: "Period", sticky: true },
    { key: "cet1_mm", header: "CET1 amount ($ millions)", numeric: true, render: (p) => fmtMm(p.cet1_mm) },
    { key: "ata_mm", header: "Adj. total assets ($ millions)", numeric: true, render: (p) => fmtMm(p.ata_mm) },
    { key: "ratio", header: "Ratio (%)", numeric: true, render: (p) => fmtPct(p.ratio, dec) },
    { key: "change", header: "Change vs prior", numeric: true, value: (p) => p.ratio_change, render: (p) => fmtPp(p.ratio_change, dec) },
    { key: "checks", header: "Checks", value: (p) => p.failed.length, render: (p) => (p.failed.length ? <Badge tone="negative">✗ {p.failed.join(", ")}</Badge> : <Badge tone="positive">✓ pass</Badge>) },
    { key: "source", header: "Source file", value: (p) => p.cet1.source_file },
  ];

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center gap-4">
        <label className="flex items-center gap-2 text-sm text-muted">
          Entity
          <select value={entity} onChange={(e) => { setChosen(e.target.value); setCompare(null); }} aria-label="Entity"
            className="rounded-lg border border-white/10 bg-ink-900/80 px-3 py-1.5 text-fg">
            {providers.map((p) => <option key={p}>{p}</option>)}
          </select>
        </label>
        {others.length > 0 && (
          <fieldset className="flex flex-wrap items-center gap-2">
            <legend className="sr-only">Compare with</legend>
            <span className="text-sm text-muted" aria-hidden="true">Compare with</span>
            {others.map((p) => {
              const on = compared.includes(p);
              return (
                <button key={p} type="button" aria-pressed={on} onClick={() => setCompare(on ? compared.filter((x) => x !== p) : [...compared, p])}
                  className={cx("rounded-full border px-3 py-1 text-xs font-medium transition", on ? "border-aurora-violet/50 bg-aurora-violet/15 text-fg" : "border-white/10 text-muted hover:text-fg")}>
                  {p}
                </button>
              );
            })}
          </fieldset>
        )}
      </div>

      {bad.length > 0 && (
        <GlassCard role="alert" className="flex gap-2 border-neg/30 p-4 text-sm text-neg">
          <AlertTriangle className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
          <span>Validation failed for: {bad.map((p) => `${p.period} (${p.failed.join(", ")})`).join("; ")}</span>
        </GlassCard>
      )}

      <h2 className="text-lg font-semibold">{entity} · {last.period}</h2>
      <div className="grid gap-4 sm:grid-cols-3">
        <KpiCard accent="teal" title="CET1 amount ($ millions)" value={fmtMm(last.cet1_mm)} spark={pts.map((p) => p.cet1_mm)} sparkLabel="CET1 amount history" footer={<SourceCitation o={last.cet1} />} />
        <KpiCard accent="blue" title="Adjusted total assets ($ millions)" value={fmtMm(last.ata_mm)} spark={pts.map((p) => p.ata_mm)} sparkLabel="Adjusted total assets history" footer={<SourceCitation o={last.ata} />} />
        <KpiCard accent="violet" title="CET1-based leverage ratio" value={fmtPct(last.ratio, dec)} caption="CET1 amount ÷ adjusted total assets"
          delta={last.previous_period && last.ratio_change != null ? { abs: fmtPp(last.ratio_change, dec), direction: direction(last.ratio_change), label: `vs ${last.previous_period}`, tone: "auto" } : null}
          spark={pts.map((p) => p.ratio * 100)} sparkLabel="Ratio history" />
      </div>
      <div className="grid gap-3 lg:grid-cols-2">
        <ProvenanceBlock o={last.cet1} title="CET1 amount" />
        <ProvenanceBlock o={last.ata} title="Adjusted total assets" />
      </div>

      <FinancialChart title="Ratio history" description="CET1 amount ÷ adjusted total assets (%). Hover for CET1, assets and sources." height={360}
        summary={`Ratio history for ${[entity, ...compared].join(", ")} across ${chartRows.length} periods. Latest ${entity}: ${fmtPct(last.ratio, dec)} in ${last.period}.`}>
        <ResponsiveContainer width="100%" height="100%" minWidth={0}>
          <LineChart data={chartRows} margin={{ top: 8, right: 16, bottom: 0, left: 0 }}>
            <CartesianGrid stroke={CHART.grid} vertical={false} />
            <XAxis dataKey="period" {...axisProps} />
            <YAxis {...axisProps} tickFormatter={(v: number) => `${v}%`} width={52} domain={["auto", "auto"]} />
            <Legend verticalAlign="top" height={28} iconType="circle" wrapperStyle={{ fontSize: 12, color: CHART.axis }} />
            <Tooltip content={<GlassTooltip format={(v) => `${v.toFixed(dec)}%`}
              footer={(row) => { const pt = row ? (row[`${entity}__pt`] as SeriesPoint | undefined) : undefined;
                return pt ? <>CET1 {fmtMm(pt.cet1_mm)} · Adj. assets {fmtMm(pt.ata_mm)} ($ millions)<br />CET1 src: {pt.cet1.source_file}, {pt.cet1.location}</> : null; }} />} />
            {[entity, ...compared].map((n, i) => (
              <Line key={n} type="monotone" dataKey={n} name={n} stroke={CHART.series[i % CHART.series.length]} strokeWidth={2.5} dot={{ r: 3 }} activeDot={{ r: 5 }} connectNulls />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </FinancialChart>

      <section aria-label="History table" className="space-y-2">
        <h2 className="text-base font-semibold">History</h2>
        <DataTable<SeriesPoint> caption={`${entity} ratio history`} rows={pts} rowKey={(p) => p.period} columns={columns} initialSort={{ key: "period", dir: "desc" }} filterable maxHeight="24rem" />
      </section>
    </div>
  );
}
