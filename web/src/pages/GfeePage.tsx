import { useState } from "react";
import { DataTable, type Column } from "../components/DataTable";
import { Badge, GlassCard } from "../components/GlassCard";
import { EmptyState, ErrorState, LoadingState } from "../components/States";
import { useApi } from "../lib/hooks";
import type { GfeeDataPoint, GfeeResponse, GfeeYear } from "../lib/types";

function fmtBps(v: number | null): string {
  return v === null ? "—" : `${v.toFixed(v % 1 === 0 ? 0 : 1)} bps`;
}

/** Source values: FHFA Single-Family Guarantee Fees reports, one row per calendar year (annual only - FHFA does not
 * publish a consistent quarterly "Total Average Guarantee Fee"). Each year shows the primary (own-report) value plus
 * any later restatements, never collapsed to a single number. */
export function GfeePage() {
  const { data, error, loading, reload } = useApi<GfeeResponse>("/gfee");
  const [selected, setSelected] = useState<GfeeYear | null>(null);

  if (loading && !data) return <LoadingState label="Loading GSE GFEE source values" />;
  if (error) return <ErrorState error={error} onRetry={reload} />;
  if (!data || data.years.length === 0)
    return (
      <EmptyState title="No GSE GFEE source values yet">
        Run <code>python scripts/fetch.py --gfee</code> to download and extract the FHFA Single-Family Guarantee Fees reports.
      </EmptyState>
    );

  const failed = data.validation.filter((v) => v.status === "fail").length;
  const warned = data.validation.filter((v) => v.status === "warn").length;

  const columns: Column<GfeeYear>[] = [
    { key: "data_year", header: "Year", sticky: true, value: (r) => r.data_year },
    { key: "population", header: "Population", value: (r) => r.population },
    { key: "total", header: "Total G-Fee", numeric: true, value: (r) => fmtBps(r.primary.total_bps) },
    { key: "ongoing", header: "Ongoing", numeric: true, value: (r) => fmtBps(r.primary.ongoing_bps) },
    { key: "upfront", header: "Upfront", numeric: true, value: (r) => fmtBps(r.primary.upfront_bps) },
    { key: "gap", header: "Gap", numeric: true, value: (r) => fmtBps(r.primary.gap_bps) },
    {
      key: "report",
      header: "Source report",
      value: (r) => r.primary.report_title,
      render: (r) => (
        <a className="underline" href={r.primary.source_url} target="_blank" rel="noreferrer">{r.primary.report_key}</a>
      ),
    },
    {
      key: "restated",
      header: "Restatements",
      value: (r) => (r.restatements.length ? `${r.restatements.length}` : ""),
      render: (r) =>
        r.restatements.length ? (
          <button className="underline text-xs" onClick={() => setSelected(r)}>
            {r.restatements.length} restatement(s)
          </button>
        ) : (
          <span className="text-xs text-subtle">none</span>
        ),
    },
  ];

  const allPoints: GfeeDataPoint[] = selected ? [selected.primary, ...selected.restatements] : [];

  return (
    <div className="space-y-5">
      <GlassCard className="flex flex-wrap items-center justify-between gap-3 p-4">
        <div className="text-sm text-muted">
          {data.summary.years} calendar year(s) · {data.summary.reports} report(s) · {data.summary.first_year}–{data.summary.last_year}
        </div>
        <span className="text-xs text-subtle">
          Source:{" "}
          <a className="underline" href={data.source.index_url} target="_blank" rel="noreferrer">fhfa.gov</a>
          {" "}· published annually only (no consistent quarterly headline figure)
        </span>
      </GlassCard>

      <GlassCard variant="data" className="p-4 sm:p-5">
        <h3 className="mb-1 text-sm font-semibold">Total Average Guarantee Fee by calendar year</h3>
        <p className="mb-3 text-xs text-subtle">
          Basis points (bps). "Primary" value is from the report whose own title year matches the data year; click
          "restatements" to see every other report's figure for that same year - nothing is overwritten or averaged.
        </p>
        <DataTable caption="FHFA Total Average Guarantee Fee" rows={data.years} rowKey={(r) => `${r.data_year}-${r.population}`} columns={columns} maxHeight="32rem" />
      </GlassCard>

      {selected && (
        <GlassCard className="p-4 sm:p-5">
          <h3 className="mb-2 flex items-center justify-between text-sm font-semibold">
            <span>{selected.data_year} ({selected.population}) · all published values</span>
            <button className="text-xs underline" onClick={() => setSelected(null)}>close</button>
          </h3>
          <ul className="space-y-2 text-sm">
            {allPoints.map((p) => (
              <li key={p.report_key} className="border-b border-white/10 pb-2 last:border-0">
                <div className="flex flex-wrap items-baseline gap-2">
                  <span className="font-medium">{p.report_title}</span>
                  <span>{fmtBps(p.total_bps)}</span>
                  {p.restated_from !== null && <Badge tone="warning">restated from {fmtBps(p.restated_from)}</Badge>}
                </div>
                <div className="mt-1 text-xs text-subtle">"{p.quote}"</div>
                {p.restated_note && <div className="mt-1 text-xs text-subtle">{p.restated_note}</div>}
              </li>
            ))}
          </ul>
        </GlassCard>
      )}

      <GlassCard className="p-4 sm:p-5">
        <h3 className="mb-2 text-sm font-semibold">
          Validation{" "}
          {failed ? <Badge tone="negative">{failed} check(s) failed</Badge> : warned ? <Badge tone="warning">{warned} warning(s)</Badge> : <Badge tone="positive">All checks passed</Badge>}
        </h3>
        <ul className="space-y-1.5 text-sm">
          {data.validation.map((c) => (
            <li key={c.name}>
              <span className="font-medium">{c.name}</span>
              <span className="block text-xs text-subtle">{c.detail}</span>
            </li>
          ))}
        </ul>
        {data.gaps.length > 0 && (
          <div className="mt-3">
            <h4 className="mb-1 text-xs font-semibold uppercase text-subtle">Documented gaps</h4>
            <ul className="space-y-1 text-xs text-subtle">
              {data.gaps.map((g) => <li key={`${g.report_key}-${g.reason}`}>{g.report_key}: {g.reason}</li>)}
            </ul>
          </div>
        )}
      </GlassCard>
    </div>
  );
}
