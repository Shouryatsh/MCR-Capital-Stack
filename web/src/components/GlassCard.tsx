import type { ElementType, HTMLAttributes, ReactNode } from "react";

export function cx(...parts: (string | false | null | undefined)[]) {
  return parts.filter(Boolean).join(" ");
}

interface GlassProps extends HTMLAttributes<HTMLElement> {
  as?: ElementType;
  /** "data" = near-opaque surface for tables and charts so dense numbers stay crisp. */
  variant?: "glass" | "data";
  hover?: boolean;
}

export function GlassCard({ as: Tag = "div", variant = "glass", hover = false, className, ...rest }: GlassProps) {
  return <Tag className={cx(variant === "glass" ? "glass" : "glass-data", hover && "glass-hover", className)} {...rest} />;
}

type Tone = "positive" | "negative" | "neutral" | "warning" | "accent" | "violet";
const TONES: Record<Tone, string> = {
  positive: "text-pos border-pos/30 bg-pos/10",
  negative: "text-neg border-neg/30 bg-neg/10",
  neutral: "text-neutral border-neutral/25 bg-neutral/10",
  warning: "text-warn border-warn/30 bg-warn/10",
  accent: "text-aurora-teal border-aurora-teal/30 bg-aurora-teal/10",
  violet: "text-aurora-violet border-aurora-violet/30 bg-aurora-violet/15",
};

export function Badge({ tone = "neutral", children, title }: { tone?: Tone; children: ReactNode; title?: string }) {
  return (
    <span title={title} className={cx("inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-medium whitespace-nowrap", TONES[tone])}>
      {children}
    </span>
  );
}
