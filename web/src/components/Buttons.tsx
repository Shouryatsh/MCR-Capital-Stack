import type { ButtonHTMLAttributes } from "react";

export function ActionButton({ children, ...rest }: ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      type="button"
      {...rest}
      className="inline-flex items-center gap-2 rounded-lg border border-white/15 bg-white/5 px-3 py-1.5 text-sm font-medium text-fg transition hover:border-aurora-teal/50 hover:bg-aurora-teal/10 disabled:cursor-not-allowed disabled:opacity-50"
    >
      {children}
    </button>
  );
}
