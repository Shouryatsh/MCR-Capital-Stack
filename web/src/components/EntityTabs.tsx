import { useRef, type KeyboardEvent } from "react";
import type { SourceEntity } from "../lib/types";
import { cx } from "./GlassCard";

/** Accessible tablist (arrow keys, Home/End) for the entity sub-tabs. The panel is rendered by the caller. */
export function EntityTabs({ entities, active, onSelect, panelId }: { entities: SourceEntity[]; active: string; onSelect: (key: string) => void; panelId: string }) {
  const refs = useRef<(HTMLButtonElement | null)[]>([]);
  const onKey = (e: KeyboardEvent, i: number) => {
    const n = entities.length;
    const next = e.key === "ArrowRight" ? (i + 1) % n : e.key === "ArrowLeft" ? (i - 1 + n) % n : e.key === "Home" ? 0 : e.key === "End" ? n - 1 : null;
    if (next == null) return;
    e.preventDefault();
    onSelect(entities[next].key);
    refs.current[next]?.focus();
  };
  return (
    <div role="tablist" aria-label="Entities" className="glass flex gap-1 overflow-x-auto p-1.5 scroll-thin">
      {entities.map((e, i) => {
        const on = e.key === active;
        return (
          <button key={e.key} ref={(el) => { refs.current[i] = el; }} role="tab" id={`tab-${e.key}`} type="button" aria-selected={on} aria-controls={panelId} tabIndex={on ? 0 : -1}
            onClick={() => onSelect(e.key)} onKeyDown={(ev) => onKey(ev, i)}
            className={cx("relative flex shrink-0 items-center gap-2 rounded-xl px-4 py-2 text-sm font-medium transition-colors",
              on ? "border border-aurora-teal/30 bg-gradient-to-r from-aurora-teal/20 to-aurora-violet/10 text-fg shadow-[0_0_24px_-8px_rgb(45_212_191/0.5)]" : "border border-transparent text-muted hover:bg-white/5 hover:text-fg")}>
            {e.name}
            <span className={cx("size-1.5 rounded-full", e.status === "data" ? "bg-pos" : "bg-subtle/60")} title={e.summary} aria-hidden="true" />
            <span className="sr-only">{e.status === "data" ? `(${e.summary})` : "(no data yet)"}</span>
          </button>
        );
      })}
    </div>
  );
}
