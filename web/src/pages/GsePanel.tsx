import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Badge, GlassCard } from "../components/GlassCard";
import { ChecksCard } from "../components/ChecksCard";
import { DataTable, type Column } from "../components/DataTable";
import { axisProps, CHART, FinancialChart, GlassTooltip } from "../components/FinancialChart";
import { KpiCard } from "../components/KpiCard";
import { EmptyState, ErrorState, LoadingState } from "../components/States";
import { useApi } from "../lib/hooks";
import { fmtDate } from "../lib/format";
import type { SourceCell, SourceEntityDetail, SourcePeriod } from "../lib/types";

const cite = (c: SourceCell) => `${c.source_file}, ${c.location} · ${c.table_name}`;
const unitLabel = (u: string) => (u === "percent" ? "percent as published" : `${u} as published`);

/** Source values for a GSE: the figures exactly as published, per quarter, with where each one was read. */
export function GsePanel({ entityKey }: { entityKey: string }) {
  const { data, error, loading, reload } = useApi<SourceEntityDetail>(`/source-values/${encodeURIComponent(entityKey)}`);
  if (loading && !data) return <LoadingState label="Loading source values" />;
  if (error) return <ErrorState error={error} onRetry={reload} />;
  if (!data) return null;
  if (!data.periods.length) return <EmptyState title={`No ${data.name} source values yet`}>Ingest a disclosure from Uploads or Data sources, then refresh.</EmptyState>;

  const periods = data.periods;
  const latest = periods[periods.length - 1];
  const hist = (field: string) => periods.filter((p) => p.values[field]).map((p) => Number(p.values[field].value));
  const accents = ["teal", "blue", "violet", "emerald", "teal"] as const;
  const rows = periods.map((p) => ({
    period: p.period, total: p.values.total_rwa ? Number(p.values.total_rwa.value) : null, credit: p.values.credit_rwa ? Number(p.values.credit_rwa.value) : null,
    total__text: p.values.total_rwa?.text, credit__text: p.values.credit_rwa?.text, label: p.label,
  }));
  const metricCols: Column<SourcePeriod>[] = data.metrics.map((m) => ({
    key: m.field, header: `${m.label} (${m.unit === "percent" ? "%" : "$ millions"})`, numeric: true,
    value: (p) => (p.values[m.field] ? Number(p.values[m.field].value) : null),
    render: (p) => p.values[m.field]?.text ?? <span className="text-warn" title="Not available for this period">missing</span>,
  }));
  const columns: Column<SourcePeriod>[] = [
    { key: "period", header: "Period", sticky: true, className: "whitespace-nowrap", render: (p) => <span className="font-medium">{p.label} {p === latest && <Badge tone="accent">Latest</Badge>}</span> },
    { key: "period_end", header: "Period end", className: "whitespace-nowrap", render: (p) => (p.period_end ? fmtDate(p.period_end) : "—") },
    ...metricCols,
    { key: "checks", header: "Checks", value: (p) => p.checks.filter((c) => c.status === "fail").length, render: (p) => {
      const fail = p.checks.filter((c) => c.status === "fail"); const warn = p.checks.filter((c) => c.status === "warn");
      return fail.length ? <Badge tone="negative" title={fail.map((c) => c.detail).join("; ")}>{fail.length} failed</Badge> : warn.length ? <Badge tone="warning" title={warn.map((c) => c.detail).join("; ")}>{warn.length} warning</Badge> : <Badge tone="positive">Pass</Badge>; } },
  ];

  return (
    <div className="space-y-5">
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {data.metrics.filter((m) => latest.values[m.field]).map((m, i) => {
          const c = latest.values[m.field];
          return (
            <KpiCard key={m.field} accent={accents[i % accents.length]} title={m.label} value={c.text}
              caption={`${latest.label} · ${unitLabel(m.unit)}`} spark={hist(m.field)} sparkLabel={`${data.name} ${m.label} history`}
              footer={<span title={`Printed as ${c.raw_value}`}>{cite(c)}</span>} />
          );
        })}
      </div>

      {data.reference && (
        <GlassCard as="section" variant="data" className="p-4" aria-label="Verification against supplied values">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h2 className="text-sm font-semibold">Verification · {data.reference.label} <span className="font-normal text-subtle">({data.reference.source})</span></h2>
            <Badge tone={data.reference.matches ? "positive" : "negative"}>{data.reference.matches ? "Matches supplied values" : "Does not match"}</Badge>
          </div>
          <dl className="mt-3 grid gap-2 sm:grid-cols-3">
            {data.metrics.filter((m) => m.field in data.reference!.expected).map((m) => {
              const expected = data.reference!.expected[m.field]; const found = data.reference!.found[m.field];
              const cell = periods.find((p) => p.period === data.reference!.period)?.values[m.field];
              return (
                <div key={m.field} className="rounded-lg border border-white/5 bg-ink-900/60 px-3 py-2 text-sm">
                  <dt className="text-xs text-muted">{m.label}</dt>
                  <dd className="tnum font-semibold">{cell?.text ?? "—"}</dd>
                  <dd className="text-[11px] text-subtle">supplied {m.unit === "percent" ? `${expected}%` : Number(expected).toLocaleString("en-US")} · {found === expected ? "equal" : "different"}</dd>
                </div>
              );
            })}
          </dl>
        </GlassCard>
      )}

      {rows.some((r) => r.total != null) && (
        <FinancialChart title="Risk-weighted assets" description="USD millions as published. Hover for the exact values." height={300}
          summary={`${data.name} total risk-weighted assets were ${latest.values.total_rwa?.text} and credit risk-weighted assets ${latest.values.credit_rwa?.text} ($ millions) in ${latest.label}, across ${rows.length} quarters.`}>
          <ResponsiveContainer width="100%" height="100%" minWidth={0}>
            <LineChart data={rows} margin={{ top: 12, right: 16, bottom: 0, left: 0 }}>
              <CartesianGrid stroke={CHART.grid} vertical={false} />
              <XAxis dataKey="period" {...axisProps} />
              <YAxis {...axisProps} width={76} domain={["auto", "auto"]} tickFormatter={(v: number) => v.toLocaleString("en-US")} label={{ value: "USD (millions)", angle: -90, position: "insideLeft", fill: CHART.axis, fontSize: 11, dx: 4 }} />
              <Legend verticalAlign="top" height={28} iconType="circle" wrapperStyle={{ fontSize: 12, color: CHART.axis }} />
              <Tooltip content={<GlassTooltip format={(v, p) => String((p.payload as Record<string, unknown>)?.[`${p.dataKey}__text`] ?? v)} title={(l, row) => `${String(row?.label ?? l)}`} />} />
              <Line type="monotone" dataKey="total" name="Total RWA" stroke={CHART.teal} strokeWidth={2.5} dot={{ r: 3 }} connectNulls />
              <Line type="monotone" dataKey="credit" name="Credit RWA" stroke={CHART.violet} strokeWidth={2.5} dot={{ r: 3 }} connectNulls />
            </LineChart>
          </ResponsiveContainer>
        </FinancialChart>
      )}

      <section aria-label="Source values by period" className="space-y-2">
        <h2 className="text-base font-semibold">{data.name} source values by period</h2>
        <DataTable<SourcePeriod> caption={`${data.name} source values by period`} rows={periods} rowKey={(p) => p.period} columns={columns} filterable filterPlaceholder="Filter periods…"
          initialSort={{ key: "period", dir: "asc" }} maxHeight="30rem" rowClassName={(p) => (p === latest ? "bg-aurora-teal/5" : undefined)}
          detailLabel={(p) => p.label}
          renderDetail={(p) => (
            <ul className="space-y-2 text-xs" data-testid="provenance">
              {data.metrics.filter((m) => p.values[m.field]).map((m) => { const c = p.values[m.field]; return (
                <li key={m.field} className="rounded-lg border border-white/5 bg-ink-900/60 p-2.5">
                  <p className="font-medium text-fg">{m.label}: <span className="tnum">{c.text}</span> <span className="text-subtle">(printed {c.raw_value}, {c.unit})</span></p>
                  <p className="text-muted">{c.source_file} · {c.location} · {c.table_name} · {c.line_item}{c.column_name && ` [${c.column_name}]`}</p>
                </li>); })}
              {p.checks.map((k) => <li key={k.name} className="text-muted"><Badge tone={k.status === "pass" ? "positive" : k.status === "warn" ? "warning" : "negative"}>{k.status}</Badge> {k.name}: {k.detail}</li>)}
            </ul>
          )} />
      </section>

      <ChecksCard checks={data.validation} label={`${data.name} validation`} subtitle={`${data.validation.length} checks on completeness, consistency and the supplied reference values`} />
    </div>
  );
}
