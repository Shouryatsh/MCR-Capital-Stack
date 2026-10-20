const nf = new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 });

/** $ millions, thousands separators, no decimals (matches the Streamlit app's fmt_mm). */
export const fmtMm = (v: number | null | undefined) => (v == null ? "—" : nf.format(Math.round(v)));

/** Ratio (0.0149) -> "1.49%" with the configured number of decimals. */
export const fmtPct = (r: number | null | undefined, decimals = 2) => (r == null ? "—" : `${(r * 100).toFixed(decimals)}%`);

/** Already-a-percentage value with an explicit sign: 7.0126 -> "+7.01%". */
export const fmtSignedPct = (p: number | null | undefined, decimals = 2) =>
  p == null ? "—" : `${p > 0 ? "+" : p < 0 ? "−" : ""}${Math.abs(p).toFixed(decimals)}%`;

/** Percentage-point change between two ratios (decimals): 0.0003 -> "+0.03 pp". */
export const fmtPp = (delta: number | null | undefined, decimals = 2) =>
  delta == null ? "—" : `${delta > 0 ? "+" : delta < 0 ? "−" : ""}${Math.abs(delta * 100).toFixed(decimals)} pp`;

/** Exact whole US dollars (integers up to 2^53 are exact in a double): 2613623651000 -> "$2,613,623,651,000". */
export const fmtUsd = (v: number | null | undefined) => (v == null ? "—" : `${v < 0 ? "−" : ""}$${nf.format(Math.abs(v))}`);

export const fmtSignedUsd = (v: number | null | undefined) =>
  v == null ? "—" : `${v > 0 ? "+" : v < 0 ? "−" : ""}$${nf.format(Math.abs(v))}`;

/** Axis/tooltip shorthand only: $3,010.7B. Never used for a reported figure. */
export const fmtBillions = (usd: number) => `$${(usd / 1e9).toLocaleString("en-US", { maximumFractionDigits: 1 })}B`;

/** 2023-09-30 -> "September 30, 2023" (parsed as UTC so the day never shifts with the viewer's time zone). */
export const fmtDate = (iso: string) =>
  new Date(`${iso}T00:00:00Z`).toLocaleDateString("en-US", { timeZone: "UTC", year: "numeric", month: "long", day: "numeric" });

export const fmtTimestamp = (iso: string | null | undefined) =>
  iso ? new Date(iso).toLocaleString("en-US", { dateStyle: "medium", timeStyle: "short" }) : "never";

export const direction = (v: number | null | undefined): "up" | "down" | "flat" => (v == null || v === 0 ? "flat" : v > 0 ? "up" : "down");

export function toCsv(rows: Record<string, string | number | null | undefined>[]): string {
  if (!rows.length) return "";
  const cols = Object.keys(rows[0]);
  const esc = (v: unknown) => {
    const s = v == null ? "" : String(v);
    return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  };
  return [cols.join(","), ...rows.map((r) => cols.map((c) => esc(r[c])).join(","))].join("\r\n");
}

export function downloadCsv(filename: string, rows: Record<string, string | number | null | undefined>[]) {
  const url = URL.createObjectURL(new Blob([toCsv(rows)], { type: "text/csv;charset=utf-8" }));
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}
