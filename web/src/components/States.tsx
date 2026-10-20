import { AlertTriangle, DatabaseZap, RefreshCw } from "lucide-react";
import type { ReactNode } from "react";
import { ApiError } from "../lib/api";
import { cx, GlassCard } from "./GlassCard";

export function Skeleton({ className }: { className?: string }) {
  return <div className={cx("skeleton", className)} />;
}

export function LoadingState({ label = "Loading data", cards = 3 }: { label?: string; cards?: number }) {
  return (
    <div role="status" aria-live="polite" aria-busy="true" data-testid="loading-state">
      <span className="sr-only">{label}…</span>
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {Array.from({ length: cards }, (_, i) => (
          <GlassCard key={i} className="space-y-3 p-5">
            <Skeleton className="h-3 w-1/3" />
            <Skeleton className="h-8 w-2/3" />
            <Skeleton className="h-12 w-full" />
          </GlassCard>
        ))}
      </div>
      <GlassCard variant="data" className="mt-4 p-5">
        <Skeleton className="h-64 w-full" />
      </GlassCard>
    </div>
  );
}

export function ErrorState({ error, onRetry }: { error: ApiError | Error; onRetry?: () => void }) {
  return (
    <GlassCard role="alert" className="flex flex-col items-start gap-3 border-neg/30 p-6">
      <div className="flex items-center gap-2 text-neg">
        <AlertTriangle className="size-5" aria-hidden="true" />
        <h2 className="font-semibold">Couldn’t load this data</h2>
      </div>
      <p className="text-sm text-muted">{error.message}</p>
      {onRetry && (
        <button type="button" onClick={onRetry} className="inline-flex items-center gap-2 rounded-lg border border-white/15 px-3 py-1.5 text-sm hover:bg-white/5">
          <RefreshCw className="size-4" aria-hidden="true" /> Try again
        </button>
      )}
    </GlassCard>
  );
}

export function EmptyState({ title, children, compact }: { title: string; children?: ReactNode; compact?: boolean }) {
  return (
    <div className={cx("flex flex-col items-center gap-2 text-center text-muted", compact ? "p-6" : "glass p-10")}>
      <DatabaseZap className="size-6 text-subtle" aria-hidden="true" />
      <p className="font-medium text-fg">{title}</p>
      {children && <div className="max-w-prose text-sm">{children}</div>}
    </div>
  );
}
