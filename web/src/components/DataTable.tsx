import { ArrowDown, ArrowUp, ArrowUpDown, ChevronRight, Search } from "lucide-react";
import { Fragment, useId, useMemo, useState, type ReactNode } from "react";
import { cx, GlassCard } from "./GlassCard";
import { EmptyState } from "./States";

export interface Column<T> {
  key: string;
  header: string;
  render?: (row: T) => ReactNode;
  /** Value used for sorting and the text filter; defaults to row[key]. */
  value?: (row: T) => string | number | null | undefined;
  align?: "left" | "right";
  /** Numeric/financial column: right-aligned, tabular figures. */
  numeric?: boolean;
  sortable?: boolean;
  /** Keep the column visible while scrolling horizontally. */
  sticky?: boolean;
  className?: string;
  /** Extra classes for the header cell (e.g. to tint a derived column). */
  headerClassName?: string;
}

interface Props<T> {
  columns: Column<T>[];
  rows: T[];
  rowKey: (row: T, index: number) => string;
  caption: string;
  filterable?: boolean;
  filterPlaceholder?: string;
  initialSort?: { key: string; dir: "asc" | "desc" };
  maxHeight?: string;
  empty?: string;
  rowClassName?: (row: T) => string | undefined;
  toolbar?: ReactNode;
  /** When set, each row gets an expand button that reveals this panel (e.g. the calculation behind a result). */
  renderDetail?: (row: T) => ReactNode;
  detailLabel?: (row: T) => string;
}

export function DataTable<T>({ columns, rows, rowKey, caption, filterable, filterPlaceholder = "Filter rows…", initialSort, maxHeight = "28rem", empty = "No rows to show.", rowClassName, toolbar, renderDetail, detailLabel }: Props<T>) {
  const [sort, setSort] = useState(initialSort ?? null);
  const [q, setQ] = useState("");
  const [open, setOpen] = useState<Set<string>>(new Set());
  const inputId = useId();

  const cell = (c: Column<T>, r: T) => (c.value ? c.value(r) : ((r as Record<string, unknown>)[c.key] as string | number | null | undefined));

  const shown = useMemo(() => {
    let out = rows;
    const needle = q.trim().toLowerCase();
    if (needle) out = out.filter((r) => columns.some((c) => String(cell(c, r) ?? "").toLowerCase().includes(needle)));
    if (sort) {
      const col = columns.find((c) => c.key === sort.key);
      if (col) {
        const dir = sort.dir === "asc" ? 1 : -1;
        out = [...out].sort((a, b) => {
          const x = cell(col, a);
          const y = cell(col, b);
          if (x == null && y == null) return 0;
          if (x == null) return 1; // blanks always last
          if (y == null) return -1;
          return (typeof x === "number" && typeof y === "number" ? x - y : String(x).localeCompare(String(y), undefined, { numeric: true })) * dir;
        });
      }
    }
    return out;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rows, columns, q, sort]);

  const toggle = (key: string) =>
    setSort((s) => (s?.key === key ? (s.dir === "asc" ? { key, dir: "desc" } : null) : { key, dir: "asc" }));

  return (
    <GlassCard variant="data" className="overflow-hidden">
      {(filterable || toolbar) && (
        <div className="flex flex-wrap items-center gap-3 border-b border-white/5 px-4 py-3">
          {filterable && (
            <div className="relative min-w-48 flex-1 sm:max-w-xs">
              <label htmlFor={inputId} className="sr-only">
                {filterPlaceholder}
              </label>
              <Search className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-subtle" aria-hidden="true" />
              <input
                id={inputId}
                type="search"
                value={q}
                onChange={(e) => setQ(e.target.value)}
                placeholder={filterPlaceholder}
                className="w-full rounded-lg border border-white/10 bg-ink-900/70 py-1.5 pr-3 pl-8 text-sm text-fg placeholder:text-subtle"
              />
            </div>
          )}
          <p className="text-xs text-subtle" aria-live="polite">
            {shown.length} of {rows.length} rows
          </p>
          <div className="ml-auto flex items-center gap-2">{toolbar}</div>
        </div>
      )}
      <div className="scroll-thin overflow-auto" style={{ maxHeight }} tabIndex={0} role="region" aria-label={`${caption} (scrollable)`}>
        <table className="w-full border-separate border-spacing-0 text-sm">
          <caption className="sr-only">{caption}</caption>
          <thead>
            <tr>
              {renderDetail && <th scope="col" className="sticky top-0 z-10 w-10 border-b border-white/10 bg-ink-800/95 px-2 py-2.5"><span className="sr-only">Details</span></th>}
              {columns.map((c) => {
                const right = c.align === "right" || c.numeric;
                const active = sort?.key === c.key;
                const sortable = c.sortable !== false;
                return (
                  <th
                    key={c.key}
                    scope="col"
                    aria-sort={active ? (sort!.dir === "asc" ? "ascending" : "descending") : sortable ? "none" : undefined}
                    className={cx(
                      "sticky top-0 z-10 border-b border-white/10 bg-ink-800/95 px-3 py-2.5 text-xs font-semibold tracking-wide whitespace-nowrap text-muted uppercase",
                      right ? "text-right" : "text-left",
                      c.sticky && "left-0 z-20",
                      c.headerClassName,
                    )}
                  >
                    {sortable ? (
                      <button type="button" onClick={() => toggle(c.key)} className={cx("inline-flex items-center gap-1 uppercase hover:text-fg", right && "flex-row-reverse")}>
                        {c.header}
                        {active ? (sort!.dir === "asc" ? <ArrowUp className="size-3" aria-hidden="true" /> : <ArrowDown className="size-3" aria-hidden="true" />) : <ArrowUpDown className="size-3 opacity-40" aria-hidden="true" />}
                      </button>
                    ) : (
                      c.header
                    )}
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody>
            {shown.map((r, i) => {
              const key = rowKey(r, i);
              const isOpen = open.has(key);
              return (
                <Fragment key={key}>
                  <tr className={cx("group", rowClassName?.(r))}>
                    {renderDetail && (
                      <td className="border-b border-white/5 px-2 py-2.5 align-top">
                        <button type="button" aria-expanded={isOpen} aria-label={`${isOpen ? "Hide" : "Show"} details${detailLabel ? `: ${detailLabel(r)}` : ""}`}
                          onClick={() => setOpen((s) => { const n = new Set(s); if (n.has(key)) n.delete(key); else n.add(key); return n; })}
                          className="rounded-md p-1 text-muted hover:bg-white/10 hover:text-fg">
                          <ChevronRight className={cx("size-4 transition-transform", isOpen && "rotate-90")} aria-hidden="true" />
                        </button>
                      </td>
                    )}
                    {columns.map((c) => (
                      <td
                        key={c.key}
                        className={cx(
                          "border-b border-white/5 px-3 py-2.5 align-top transition-colors group-hover:bg-aurora-cyan/5",
                          (c.align === "right" || c.numeric) && "text-right",
                          c.numeric && "tnum whitespace-nowrap",
                          c.sticky && "sticky left-0 bg-ink-900/95",
                          c.className,
                        )}
                      >
                        {c.render ? c.render(r) : (cell(c, r) ?? "—")}
                      </td>
                    ))}
                  </tr>
                  {renderDetail && isOpen && (
                    <tr>
                      <td colSpan={columns.length + 1} className="border-b border-white/10 bg-ink-950/40 p-0">
                        <div className="p-4">{renderDetail(r)}</div>
                      </td>
                    </tr>
                  )}
                </Fragment>
              );
            })}
          </tbody>
        </table>
        {shown.length === 0 && <EmptyState compact title={empty} />}
      </div>
    </GlassCard>
  );
}
