import type { ReactNode } from "react";
import { GlassCard } from "./GlassCard";

export const CHART = {
  teal: "#2dd4bf",
  cyan: "#22d3ee",
  violet: "#8b7cf6",
  blue: "#4f8cff",
  emerald: "#34d399",
  coral: "#fb7185",
  amber: "#fbbf24",
  grid: "rgba(148,163,205,0.14)",
  axis: "#9aa8c4",
  series: ["#2dd4bf", "#8b7cf6", "#4f8cff", "#fbbf24", "#fb7185", "#34d399"],
};

export const axisProps = { stroke: "transparent", tick: { fill: CHART.axis, fontSize: 11 }, tickLine: false } as const;

interface FrameProps {
  title: string;
  description?: string;
  /** Plain-language summary for assistive tech (the data table elsewhere on the page is the full equivalent). */
  summary: string;
  actions?: ReactNode;
  height?: number;
  children: ReactNode;
}

/** Consistent glass frame + accessible summary around every Recharts chart. */
export function FinancialChart({ title, description, summary, actions, height = 320, children }: FrameProps) {
  return (
    <GlassCard as="section" variant="data" className="p-4 sm:p-5" aria-label={title}>
      <header className="mb-3 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold">{title}</h2>
          {description && <p className="mt-0.5 text-xs text-subtle">{description}</p>}
        </div>
        {actions}
      </header>
      <figure className="m-0" role="group" aria-label={`${title} chart`}>
        <div style={{ height }} role="img" aria-label={summary}>
          {children}
        </div>
        <figcaption className="sr-only">{summary}</figcaption>
      </figure>
    </GlassCard>
  );
}

interface TooltipRow {
  name?: string | number;
  value?: number | string;
  color?: string;
  dataKey?: string | number;
  payload?: Record<string, unknown>;
}

interface TooltipProps {
  active?: boolean;
  payload?: TooltipRow[];
  label?: string | number;
  title?: (label: string | number | undefined, row: Record<string, unknown> | undefined) => ReactNode;
  format: (value: number, row: TooltipRow) => string;
  footer?: (row: Record<string, unknown> | undefined) => ReactNode;
}

export function GlassTooltip({ active, payload, label, title, format, footer }: TooltipProps) {
  if (!active || !payload?.length) return null;
  const first = payload[0].payload;
  return (
    <div className="glass-data min-w-44 px-3 py-2 text-xs shadow-xl">
      <p className="mb-1 font-semibold text-fg">{title ? title(label, first) : label}</p>
      <ul className="space-y-0.5">
        {payload.map((p, i) => (
          <li key={i} className="flex items-center justify-between gap-4">
            <span className="flex items-center gap-1.5 text-muted">
              <span className="size-2 rounded-full" style={{ background: p.color }} aria-hidden="true" />
              {p.name}
            </span>
            <span className="tnum font-medium text-fg">{typeof p.value === "number" ? format(p.value, p) : p.value}</span>
          </li>
        ))}
      </ul>
      {footer && <div className="mt-1.5 border-t border-white/10 pt-1.5 text-subtle">{footer(first)}</div>}
    </div>
  );
}
