import { CalendarDays, Menu, RefreshCw } from "lucide-react";
import type { Meta } from "../lib/types";
import { fmtTimestamp } from "../lib/format";
import { cx } from "./GlassCard";
import type { NavItem } from "./nav";

interface Props {
  item: NavItem;
  meta: Meta | null;
  refreshing: boolean;
  failed: boolean;
  period: string | null;
  onPeriod: (p: string) => void;
  onRefresh: () => void;
  onMenu: () => void;
}

export function TopNavigation({ item, meta, refreshing, failed, period, onPeriod, onRefresh, onMenu }: Props) {
  const showPeriod = item.usesPeriod && meta && meta.periods.length > 0;
  return (
    <header className="glass mx-3 mt-3 flex flex-wrap items-center gap-x-4 gap-y-3 px-4 py-3 lg:mx-0 lg:mr-3" data-testid="top-nav">
      <button type="button" onClick={onMenu} aria-label="Open navigation menu" className="rounded-lg p-2 text-muted hover:bg-white/5 lg:hidden">
        <Menu className="size-5" aria-hidden="true" />
      </button>
      <div className="min-w-0 flex-1 basis-60">
        <h1 className="truncate text-xl font-semibold tracking-tight sm:text-2xl">{item.title}</h1>
        <p className="text-xs text-muted sm:text-sm">{item.description}</p>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        {showPeriod && (
          <label className="flex items-center gap-2 text-xs text-muted">
            <CalendarDays className="size-4 text-aurora-teal" aria-hidden="true" />
            <span className="sr-only sm:not-sr-only">Reporting period</span>
            <select
              value={period ?? ""}
              onChange={(e) => onPeriod(e.target.value)}
              className="rounded-lg border border-white/10 bg-ink-900/80 px-2.5 py-1.5 text-sm text-fg"
              aria-label="Reporting period"
            >
              {meta!.periods.map((p) => (
                <option key={p} value={p}>
                  {p}
                </option>
              ))}
            </select>
          </label>
        )}
        <p className="flex items-center gap-2 text-xs text-subtle" role="status" aria-live="polite" data-testid="freshness">
          <span className={cx("size-2 rounded-full", failed ? "bg-neg" : refreshing ? "animate-pulse bg-warn" : "bg-pos")} aria-hidden="true" />
          {failed ? "Data unavailable" : refreshing ? "Refreshing…" : `Updated ${fmtTimestamp(meta?.last_updated)}`}
        </p>
        <button
          type="button"
          onClick={onRefresh}
          disabled={refreshing}
          aria-label="Refresh data"
          className="inline-flex items-center gap-2 rounded-lg border border-white/15 bg-white/5 px-3 py-1.5 text-sm hover:border-aurora-teal/50 hover:bg-aurora-teal/10 disabled:opacity-60"
        >
          <RefreshCw className={cx("size-4", refreshing && "animate-spin")} aria-hidden="true" />
          <span className="hidden sm:inline">Refresh</span>
        </button>
      </div>
    </header>
  );
}
