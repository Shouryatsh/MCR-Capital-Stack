import { useState } from "react";
import { DataTable, type Column } from "../components/DataTable";
import { Badge, GlassCard } from "../components/GlassCard";
import { EmptyState, ErrorState, LoadingState } from "../components/States";
import { useApi } from "../lib/hooks";
import type { FhlbPeriod, FhlbResponse } from "../lib/types";

interface BankRow {
  bank: string;
  derived: boolean;
  values: Record<string, { text: string; title: string } | undefined>;
}

/** Source values: FHLBanks Office of Finance Combined Financial Report, Table 9.1 (Risk-Based Capital Requirements)
 * and Table 9.2 (Regulatory Capital Requirements), one row per FHLBank (+ system-wide Combined where published). */
export function FhlbPage() {
  const { data, error, loading, reload } = useApi<FhlbResponse>("/fhlb");
  const [periodIdx, setPeriodIdx] = useState<number | null>(null);

  if (loading && !data) return <LoadingState label="Loading FHLB source values" />;
  if (error) return <ErrorState error={error} onRetry={reload} />;
  if (!data || data.periods.length === 0)
    return (
      <EmptyState title="No FHLB source values yet">
        Run <code>python scripts/fetch.py --fhlb</code> to download and extract the Combined Financial Reports.
      </EmptyState>
    );

  const periods = data.periods;
  const idx = periodIdx ?? periods.length - 1;
  const period: FhlbPeriod = periods[idx];
  const failed = data.validation.filter((v) => v.status === "fail").length;
  const warned = data.validation.filter((v) => v.status === "warn").length;

  const rows: BankRow[] = data.banks
    .filter((b) => period.banks[b])
    .map((bank) => ({
      bank,
      derived: (period.derived_banks ?? []).includes(bank),
      values: Object.fromEntries(
        data.fields.map((f) => {
          const cell = period.banks[bank]?.[f.field];
          const title = !cell ? "" : cell.source_note ? `Derived: ${cell.source_note}` : cell.derived ? `Derived: ${f.formula}` : `${cell.table_name} · ${cell.source_file}${cell.location ? " · " + cell.location : ""}`;
          return [f.field, cell ? { text: cell.text, title } : undefined];
        }),
      ),
    }));

  const columns: Column<BankRow>[] = [
    { key: "bank", header: "FHLBank", sticky: true, render: (r) => (r.derived ? <span title="Not published in this report; derived from the 11 FHLBanks">{r.bank} (derived)</span> : r.bank) },
    ...data.fields.map((f): Column<BankRow> => ({
      key: f.field,
      header: f.derived ? `${f.label} (derived)` : f.label,
      numeric: true,
      value: (r) => r.values[f.field]?.text ?? null,
      render: (r) => <span title={r.values[f.field]?.title}>{r.values[f.field]?.text ?? "—"}</span>,
      ...(f.derived && { className: "bg-aurora-violet/15 text-aurora-violet font-medium", headerClassName: "!bg-aurora-violet/25 !text-aurora-violet" }),
    })),
  ];
  const derived = data.fields.filter((f) => f.derived);

  return (
    <div className="space-y-5">
      <GlassCard className="flex flex-wrap items-center justify-between gap-3 p-4">
        <div className="flex items-center gap-3">
          <label htmlFor="fhlb-period" className="text-sm text-muted">Reporting period</label>
          <select id="fhlb-period" className="glass-data rounded-lg px-2 py-1 text-sm" value={idx}
                  onChange={(e) => setPeriodIdx(Number(e.target.value))}>
            {periods.map((p, i) => (
              <option key={p.period} value={i}>{p.period} · {p.label || p.report_date}</option>
            ))}
          </select>
        </div>
        <span className="text-xs text-subtle">
          {periods.length} quarterly report(s) · {data.banks.length} entities · source:{" "}
          <a className="underline" href={data.source.index_url} target="_blank" rel="noreferrer">fhlb-of.com</a>
        </span>
      </GlassCard>

      <GlassCard variant="data" className="p-4 sm:p-5">
        <h3 className="mb-1 text-sm font-semibold">Table 9.1 / 9.2 · as of {period.label || period.report_date}</h3>
        <p className="mb-3 text-xs text-subtle">$ millions unless noted; Combined is a system-wide total published for analysis only, not every period.</p>
        {derived.length > 0 && (
          <ul className="mb-3 space-y-1 text-xs text-subtle">
            {derived.map((f) => (
              <li key={f.field}>
                <Badge tone="violet">Derived</Badge> <span className="font-medium text-fg">{f.label}</span> = {f.formula}
              </li>
            ))}
          </ul>
        )}
        {period.derived_banks && period.derived_banks.length > 0 && (
          <p className="mb-3 text-xs text-subtle">
            <Badge tone="warning">Derived row</Badge> The {period.label || period.report_date} report does not publish a Combined row, so it is derived:
            the dollar amounts are the sum of the 11 FHLBanks, and the actual regulatory capital ratio is total regulatory capital ÷ total assets implied by each bank's own ratio.
            The minimum ratio is not published for Combined and is left blank.
          </p>
        )}
        <DataTable caption={`FHLB capital requirements, ${period.period}`} rows={rows} rowKey={(r) => r.bank} columns={columns} maxHeight="32rem"
                   rowClassName={(r) => (r.derived ? "[&>td]:!bg-warn/10 [&>td]:!text-warn [&>td]:font-medium" : undefined)} />
      </GlassCard>

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
              {data.gaps.map((g) => <li key={`${g.period}-${g.reason}`}>{g.period}: {g.reason}</li>)}
            </ul>
          </div>
        )}
      </GlassCard>
    </div>
  );
}
