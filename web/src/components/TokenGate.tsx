import { KeyRound } from "lucide-react";
import { useState } from "react";
import { setToken } from "../lib/api";
import { GlassCard } from "./GlassCard";

/** Shown when the API answers 401 (MCR_TOKEN is set on the server) – same placeholder gate as the Streamlit app. */
export function TokenGate({ onSubmit, rejected }: { onSubmit: () => void; rejected: boolean }) {
  const [value, setValue] = useState("");
  return (
    <div className="grid min-h-dvh place-items-center p-4">
      <GlassCard as="form" className="w-full max-w-sm space-y-4 p-6" onSubmit={(e: React.FormEvent) => { e.preventDefault(); setToken(value); onSubmit(); }}>
        <div className="flex items-center gap-2">
          <KeyRound className="size-5 text-aurora-teal" aria-hidden="true" />
          <h1 className="text-lg font-semibold">MCR Dashboard</h1>
        </div>
        <label className="block text-sm text-muted">
          Access token
          <input
            type="password"
            value={value}
            onChange={(e) => setValue(e.target.value)}
            autoFocus
            className="mt-1 w-full rounded-lg border border-white/10 bg-ink-900/80 px-3 py-2 text-fg"
          />
        </label>
        {rejected && <p role="alert" className="text-sm text-neg">That token was not accepted.</p>}
        <button type="submit" className="w-full rounded-lg bg-gradient-to-r from-aurora-teal to-aurora-cyan px-3 py-2 text-sm font-semibold text-ink-950">
          Continue
        </button>
      </GlassCard>
    </div>
  );
}
