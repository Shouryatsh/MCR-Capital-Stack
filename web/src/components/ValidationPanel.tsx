import { CheckCircle2, ChevronDown, ShieldAlert, TriangleAlert } from "lucide-react";
import { useState } from "react";
import type { GnmaGap, GnmaReconciliation, GnmaValidation } from "../lib/types";
import { fmtUsd } from "../lib/format";
import { Badge, cx, GlassCard } from "./GlassCard";
import { DataTable } from "./DataTable";

const ICON = { pass: CheckCircle2, warn: TriangleAlert, fail: ShieldAlert } as const;
const COLOR = { pass: "text-pos", warn: "text-warn", fail: "text-neg" } as const;

export function ValidationStatus({ checks }: { checks: GnmaValidation[] }) {
  const failed = checks.filter((c) => c.status === "fail").length;
  const warned = checks.filter((c) => c.status === "warn").length;
  if (failed) return <Badge tone="negative">{failed} validation check{failed > 1 ? "s" : ""} failed</Badge>;
  if (warned) return <Badge tone="warning">Validated · {warned} reconciliation note{warned > 1 ? "s" : ""}</Badge>;
  return <Badge tone="positive">All validation checks passed</Badge>;
}

export function ValidationPanel({ checks, reconciliation, gaps }: { checks: GnmaValidation[]; reconciliation: GnmaReconciliation[]; gaps: GnmaGap[] }) {
  const [open, setOpen] = useState(false);
  const notable = reconciliation.filter((r) => r.status !== "match");
  return (
    <GlassCard as="section" variant="data" className="p-4 sm:p-5" aria-label="Data validation and provenance">
      <button type="button" aria-expanded={open} onClick={() => setOpen((o) => !o)} className="flex w-full items-center justify-between gap-3 text-left">
        <span>
          <span className="block text-base font-semibold">Validation, reconciliation and gaps</span>
          <span className="text-xs text-subtle">
            {checks.length} checks · {reconciliation.length} cross-report comparisons · {gaps.length} documented gaps
          </span>
        </span>
        <span className="flex items-center gap-3">
          <ValidationStatus checks={checks} />
          <ChevronDown className={cx("size-4 transition-transform", open && "rotate-180")} aria-hidden="true" />
        </span>
      </button>
      {open && (
        <div className="mt-4 space-y-5">
          <ul className="space-y-2">
            {checks.map((c) => {
              const Icon = ICON[c.status];
              return (
                <li key={c.name} className="flex gap-2 text-sm">
                  <Icon className={cx("mt-0.5 size-4 shrink-0", COLOR[c.status])} aria-label={c.status} />
                  <span>
                    <span className="font-medium">{c.name}</span>
                    <span className="block text-xs text-subtle">{c.detail}</span>
                  </span>
                </li>
              );
            })}
          </ul>
          <div>
            <h3 className="mb-2 text-sm font-semibold">
              Comparatives reconciled across reports <span className="font-normal text-subtle">({notable.length} not an exact match)</span>
            </h3>
            <DataTable
              caption="Cross-report reconciliation"
              rows={reconciliation}
              rowKey={(r) => `${r.fiscal_year}-${r.component}-${r.report_a}-${r.report_b}`}
              filterable
              maxHeight="18rem"
              initialSort={{ key: "status", dir: "desc" }}
              columns={[
                { key: "fiscal_year", header: "FY", value: (r) => r.fiscal_year, render: (r) => `FY${r.fiscal_year}` },
                { key: "component", header: "Component" },
                { key: "report_a", header: "Report A" },
                { key: "usd_a", header: "A (USD)", numeric: true, render: (r) => fmtUsd(r.usd_a) },
                { key: "report_b", header: "Report B" },
                { key: "usd_b", header: "B (USD)", numeric: true, render: (r) => fmtUsd(r.usd_b) },
                { key: "difference_usd", header: "A − B", numeric: true, render: (r) => fmtUsd(r.difference_usd) },
                { key: "status", header: "Status", render: (r) => <Badge tone={r.status === "match" ? "positive" : r.status === "MISMATCH" ? "negative" : "warning"}>{r.status}</Badge> },
              ]}
            />
          </div>
          {gaps.length > 0 && (
            <div>
              <h3 className="mb-1 text-sm font-semibold">Years without a reliable figure</h3>
              <p className="mb-2 text-xs text-subtle">Flagged, never estimated or interpolated.</p>
              <DataTable
                caption="Documented extraction gaps"
                rows={gaps}
                rowKey={(g) => `${g.fiscal_year}-${g.source_report}-${g.reason}`}
                maxHeight="14rem"
                columns={[
                  { key: "fiscal_year", header: "FY", render: (g) => `FY${g.fiscal_year}` },
                  { key: "source_report", header: "Report" },
                  { key: "reason", header: "Reason", className: "whitespace-normal" },
                ]}
              />
            </div>
          )}
        </div>
      )}
    </GlassCard>
  );
}
