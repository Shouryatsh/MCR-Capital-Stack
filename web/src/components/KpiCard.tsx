import { ArrowDownRight, ArrowUpRight, Minus } from "lucide-react";
import { useId, type ReactNode } from "react";
import { Area, AreaChart, ResponsiveContainer, YAxis } from "recharts";
import { cx, GlassCard } from "./GlassCard";

export interface Delta {
  /** Preformatted absolute change, e.g. "+$171,272,556,000" or "+0.03 pp". */
  abs: string;
  /** Preformatted percentage change, e.g. "+7.01%". */
  pct?: string;
  direction: "up" | "down" | "flat";
  /** What it is compared with, e.g. "vs FY2022" – always shown so the periods are never ambiguous. */
  label: string;
  /** "auto": up = green, down = red. "neutral": direction without judgement (e.g. exposure size). */
  tone?: "auto" | "neutral";
}

export interface KpiCardProps {
  title: string;
  value: ReactNode;
  /** Small line under the value (units, as-of date). */
  caption?: ReactNode;
  delta?: Delta | null;
  /** Real historical values only; the sparkline is hidden when there are fewer than 2. */
  spark?: number[];
  sparkLabel?: string;
  accent?: "teal" | "violet" | "blue" | "emerald";
  footer?: ReactNode;
  featured?: boolean;
}

const ACCENT = { teal: "#2dd4bf", violet: "#8b7cf6", blue: "#4f8cff", emerald: "#34d399" } as const;

export function Sparkline({ values, color, label }: { values: number[]; color: string; label?: string }) {
  const id = useId().replace(/:/g, "");
  const data = values.map((v, i) => ({ i, v }));
  return (
    <div className="h-12 w-full" role="img" aria-label={label ?? `Trend over ${values.length} periods`}>
      <ResponsiveContainer width="100%" height="100%" minWidth={0}>
        <AreaChart data={data} margin={{ top: 4, right: 0, bottom: 0, left: 0 }}>
          <defs>
            <linearGradient id={id} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={color} stopOpacity={0.45} />
              <stop offset="100%" stopColor={color} stopOpacity={0} />
            </linearGradient>
          </defs>
          <YAxis hide domain={["dataMin", "dataMax"]} />
          <Area type="monotone" dataKey="v" stroke={color} strokeWidth={2} fill={`url(#${id})`} isAnimationActive={false} />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

export function DeltaPill({ delta }: { delta: Delta }) {
  const Icon = delta.direction === "up" ? ArrowUpRight : delta.direction === "down" ? ArrowDownRight : Minus;
  const tone =
    delta.tone === "neutral" || delta.direction === "flat"
      ? "text-neutral"
      : delta.direction === "up"
        ? "text-pos"
        : "text-neg";
  return (
    <p className="mt-2 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-xs" data-testid="kpi-delta">
      <span className={cx("inline-flex items-center gap-0.5 font-semibold tnum", tone)}>
        <Icon className="size-3.5" aria-hidden="true" />
        {delta.abs}
        {delta.pct && <span className="font-medium opacity-90">({delta.pct})</span>}
      </span>
      <span className="text-subtle">{delta.label}</span>
    </p>
  );
}

export function KpiCard({ title, value, caption, delta, spark, sparkLabel, accent = "teal", footer, featured }: KpiCardProps) {
  const color = ACCENT[accent];
  return (
    <GlassCard as="section" hover aria-label={title} className={cx("relative overflow-hidden p-4 sm:p-5", featured && "sm:col-span-2")}>
      <div aria-hidden="true" className="pointer-events-none absolute -top-16 -right-10 size-40 rounded-full opacity-25 blur-3xl" style={{ background: color }} />
      <h3 className="text-xs font-medium tracking-wide text-muted uppercase">{title}</h3>
      <p className={cx("mt-2 font-semibold tracking-tight tnum", featured ? "text-3xl sm:text-4xl" : "text-2xl sm:text-3xl")}>{value}</p>
      {caption && <p className="mt-1 text-xs text-subtle">{caption}</p>}
      {delta && <DeltaPill delta={delta} />}
      {spark && spark.length >= 2 && (
        <div className="mt-3">
          <Sparkline values={spark} color={color} label={sparkLabel} />
        </div>
      )}
      {footer && <div className="mt-3 border-t border-white/5 pt-2 text-xs text-subtle">{footer}</div>}
    </GlassCard>
  );
}
