import { CheckCircle2, ChevronDown, ShieldAlert, TriangleAlert } from "lucide-react";
import { useState } from "react";
import type { GnmaValidation } from "../lib/types";
import { cx, GlassCard } from "./GlassCard";
import { ValidationStatus } from "./ValidationPanel";

const ICON = {
  pass: <CheckCircle2 className="size-4 shrink-0 text-pos" aria-label="pass" />,
  warn: <TriangleAlert className="size-4 shrink-0 text-warn" aria-label="warning" />,
  fail: <ShieldAlert className="size-4 shrink-0 text-neg" aria-label="fail" />,
};

/** Collapsible list of validation checks (collapsed by default so the main view stays uncluttered). */
export function ChecksCard({ checks, label, subtitle }: { checks: GnmaValidation[]; label: string; subtitle: string }) {
  const [open, setOpen] = useState(false);
  return (
    <GlassCard as="section" variant="data" className="p-4" aria-label={label}>
      <button type="button" aria-expanded={open} onClick={() => setOpen((o) => !o)} className="flex w-full items-center justify-between gap-3 text-left">
        <span><span className="block text-base font-semibold">Validation</span><span className="text-xs text-subtle">{subtitle}</span></span>
        <span className="flex items-center gap-3"><ValidationStatus checks={checks} /><ChevronDown className={cx("size-4 transition-transform", open && "rotate-180")} aria-hidden="true" /></span>
      </button>
      {open && (
        <ul className="mt-3 space-y-2">
          {checks.map((c) => (
            <li key={c.name} className="flex gap-2 text-sm">{ICON[c.status]}<span><span className="font-medium">{c.name}</span><span className="block text-xs text-subtle">{c.detail}</span></span></li>
          ))}
        </ul>
      )}
    </GlassCard>
  );
}
