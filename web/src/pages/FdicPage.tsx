import { useState } from "react";
import { DataTable, type Column } from "../components/DataTable";
import { Badge, GlassCard } from "../components/GlassCard";
import { EmptyState, ErrorState, LoadingState } from "../components/States";
import { useApi } from "../lib/hooks";
import type { FdicDataPoint, FdicResponse } from "../lib/types";

function fmtThousands(v: number | null): string {
  if (v === null) return "—";
  return v < 0 ? `-$${Math.abs(v).toLocaleString()}` : `$${v.toLocaleString()}`;
}

function fmtPct(v: number | null): string {
  return v === null ? "—" : `${v.toFixed(2)}%`;
}

function fmtTrillions(v: number | null): string {
  return v === null ? "—" : `$${v.toFixed(1)}T`;
}

/** Source values: FDIC Deposit Insurance Fund figures from each year's Annual Report "Financial Section", one row
 * per calendar year. Unlike GSE GFEE, FDIC reports have no competing populations/restatements - each report_key
 * maps 1:1 to a single calendar year, so the table is the headline series directly. */
export function FdicPage() {
  const { data, error, loading, reload } = useApi<FdicResponse>("/fdic");
  const [selected, setSelected] = useState<FdicDataPoint | null>(null);

  if (loading && !data) return <LoadingState label="Loading FDIC source values" />;
  if (error) return <ErrorState error={error} onRetry={reload} />;
  if (!data || data.years.length === 0)
    return (
      <EmptyState title="No FDIC source values yet">
        Run <code>python scripts/fetch.py --fdic</code> to download and extract the FDIC Annual Report Financial Section PDFs.
      </EmptyState>
    );

  const failed = data.validation.filter((v) => v.status === "fail").length;
  const warned = data.validation.filter((v) => v.status === "warn").length;

  const columns: Column<FdicDataPoint>[] = [
    { key: "report_key", header: "Year", sticky: true, value: (r) => r.report_key },
    { key: "fund_balance", header: "Fund Balance - Ending ($ thousands)", numeric: true, value: (r) => fmtThousands(r.fund_balance_ending) },
    { key: "min_reserve_ratio", header: "Minimum Reserve Ratio", numeric: true, value: (r) => fmtPct(r.min_reserve_ratio_pct) },
    { key: "insured_deposits", header: "Estimated Insured Deposits", numeric: true, value: (r) => fmtTrillions(r.insured_deposits_trillions) },
    { key: "as_of", header: "Insured deposits as of", value: (r) => r.insured_deposits_as_of },
    {
      key: "report",
      header: "Source report",
      value: (r) => r.report_title,
      render: (r) => (
        <a className="underline" href={r.source_url} target="_blank" rel="noreferrer">{r.report_key}</a>
      ),
    },
    {
      key: "quotes",
      header: "Quotes",
      value: () => "",
      render: (r) => (
        <button className="underline text-xs" onClick={() => setSelected(r)}>
          view quotes
        </button>
      ),
    },
  ];

  return (
    <div className="space-y-5">
      <GlassCard className="flex flex-wrap items-center justify-between gap-3 p-4">
        <div className="text-sm text-muted">
          {data.summary.years} calendar year(s) · {data.summary.first_year}–{data.summary.last_year}
        </div>
        <span className="text-xs text-subtle">
          Source:{" "}
          <a className="underline" href={data.source.index_url} target="_blank" rel="noreferrer">fdic.gov</a>
          {" "}· one "Financial Section" report per calendar year
        </span>
      </GlassCard>

      <GlassCard variant="data" className="p-4 sm:p-5">
        <h3 className="mb-1 text-sm font-semibold">Deposit Insurance Fund (DIF) headline figures by calendar year</h3>
        <p className="mb-3 text-xs text-subtle">
          Fund Balance - Ending and Minimum Reserve Ratio are from the Statement of Income and Fund Balance and the
          Restoration Plan discussion, respectively. Estimated Insured Deposits is a rounded ($0.1T precision) figure
          from the "Off-Balance-Sheet Exposure: Deposit Insurance" note, with its own "as of" date (not always
          December 31). Click "view quotes" to see the exact published text each value was transcribed from.
        </p>
        <DataTable caption="FDIC Deposit Insurance Fund" rows={data.years} rowKey={(r) => r.report_key} columns={columns} maxHeight="32rem" />
      </GlassCard>

      {selected && (
        <GlassCard className="p-4 sm:p-5">
          <h3 className="mb-2 flex items-center justify-between text-sm font-semibold">
            <span>{selected.report_key} · published quotes</span>
            <button className="text-xs underline" onClick={() => setSelected(null)}>close</button>
          </h3>
          <ul className="space-y-2 text-sm">
            <li className="border-b border-white/10 pb-2">
              <div className="font-medium">Fund Balance - Ending: {fmtThousands(selected.fund_balance_ending)}</div>
              <div className="mt-1 text-xs text-subtle">"{selected.fund_balance_quote || "—"}"</div>
            </li>
            <li className="border-b border-white/10 pb-2">
              <div className="font-medium">Minimum Reserve Ratio: {fmtPct(selected.min_reserve_ratio_pct)}</div>
              <div className="mt-1 text-xs text-subtle">"{selected.min_reserve_ratio_quote || "—"}"</div>
            </li>
            <li>
              <div className="font-medium">
                Estimated Insured Deposits: {fmtTrillions(selected.insured_deposits_trillions)}
                {selected.insured_deposits_as_of && <span className="font-normal text-subtle"> (as of {selected.insured_deposits_as_of})</span>}
              </div>
              <div className="mt-1 text-xs text-subtle">"{selected.insured_deposits_quote || "—"}"</div>
            </li>
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
