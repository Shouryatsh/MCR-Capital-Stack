import type { BenchmarksResponse, BenchResult, EntitySeries, GnmaFigure, GnmaResponse, Meta, PeersResponse, Provenance, SourceCell, SourceEntityDetail, SourcePeriod } from "../lib/types";

/** API-shaped fixtures for tests only (production code never imports this). Values mirror the real GNMA reference years. */
const gf = (fy: number, mbs: number, com: number, extra: Partial<GnmaFigure> = {}): GnmaFigure => {
  const total = mbs + com;
  const k = (n: number) => `$${(n / 1000).toLocaleString("en-US")}`;
  return {
    fiscal_year: fy, reporting_date: `${fy}-09-30`, role: "current", source_report: `annual_report${String(fy).slice(2)}.pdf`,
    source_url: `https://www.ginniemae.gov/about_us/what_we_do/Annual_Reports/annual_report${String(fy).slice(2)}.pdf`,
    pdf_page: 96, printed_page: "A-20", note: "Note 2: Summary of Significant Accounting Policies", table_title: "Maximum exposure to loss",
    table_kind: "maximum_exposure_to_loss", units: "thousands", mbs_raw: "", commitments_raw: "", total_raw: "", mbs_usd: mbs, commitments_usd: com,
    total_usd: total, reported_total_usd: total, precision_usd: 1000, flags: [], ok: true,
    mbs_usd_text: `$${mbs.toLocaleString("en-US")}`, commitments_usd_text: `$${com.toLocaleString("en-US")}`, total_usd_text: `$${total.toLocaleString("en-US")}`,
    total_published: `${k(total)} (USD thousands)`, mbs_published: k(mbs), commitments_published: k(com), ...extra,
  };
};

const y21 = gf(2021, 2_125_591_309_000, 301_023_584_000, { role: "comparative", pdf_page: 94, printed_page: "A-24" });
const y22 = gf(2022, 2_284_456_605_000, 157_894_490_000, { yoy: { prior_fiscal_year: 2021, total_abs_usd: 2_442_351_095_000 - 2_426_614_893_000, total_pct: 0.6485, mbs_abs_usd: 158_865_296_000, mbs_pct: 7.4737, commitments_abs_usd: -143_129_094_000, commitments_pct: -47.5471, rounded: false } });
const y23 = gf(2023, 2_472_843_019_000, 140_780_632_000, { latest: true, yoy: { prior_fiscal_year: 2022, total_abs_usd: 171_272_556_000, total_pct: 7.0126, mbs_abs_usd: 188_386_414_000, mbs_pct: 8.2468, commitments_abs_usd: -17_113_858_000, commitments_pct: -10.8386, rounded: false } });

export const gnmaFixture: GnmaResponse = {
  source: { index_url: "https://www.ginniemae.gov/about-us/what-we-do/budget-performance/annual-reports", provider: "GNMA" },
  series: [y21, y22, y23],
  observations: [y21, y22, y23],
  validation: [
    { name: "Total = Outstanding MBS + commitments (every observation)", status: "pass", detail: "3 observation(s) checked" },
    { name: "FY2023 equals the reference total $2,613,623,651 (USD thousands)", status: "pass", detail: "extracted $2,613,623,651 (USD thousands)" },
    { name: "Comparative figures in successive reports reconcile", status: "warn", detail: "1 comparison differs" },
  ],
  reconciliation: [{ fiscal_year: 2022, component: "Total", report_a: "annual_report22.pdf", usd_a: 2_442_351_095_000, report_b: "annual_report23.pdf", usd_b: 2_442_351_095_000, difference_usd: 0, status: "match" }],
  gaps: [{ fiscal_year: 2010, source_report: "annual_report10.pdf", reason: "no 'Outstanding MBS' table found in the report text" }],
  reference: { "2023": { mbs: 2_472_843_019_000, commitments: 140_780_632_000, total: 2_613_623_651_000 }, "2022": { mbs: 2_284_456_605_000, commitments: 157_894_490_000, total: 2_442_351_095_000 } },
};

export const metaFixture: Meta = { app_name: "MCR Dashboard", units: "$ millions", ratio_decimals: 2, primary_provider: "Fannie Mae", last_updated: "2026-10-13T20:00:54Z", has_cet1: true, has_gnma: true, periods: ["2026Q2", "2026Q1"] };

const prov = (file: string): Provenance => ({ source_file: file, table_name: "Exhibit 2.2", row_identifier: "r", field_label: "Common equity tier 1 capital", raw_value: "66", parsed_value: 66, units_detected: "billions", units_source: "detected", value_mm: 66000, location: "p.9", column_name: "Minimum Capital Requirement", source_url: "", ingested_at: "2026-10-13T20:00:54Z" });

export const peersFixture: PeersResponse = {
  periods: ["2026Q2", "2026Q1"], period: "2026Q2",
  rows: [
    { slot: 1, name: "Fannie Mae", provider: "Fannie Mae", status: "ok", period: "2026Q2", cet1_mm: 66000, ata_mm: 4434746, ratio: 0.014882, rank: 1, of: 2, percentile: 100, failed_checks: [], cet1_src: prov("2026Q2.pdf"), ata_src: prov("2026Q2.pdf") },
    { slot: 2, name: "Freddie Mac", provider: "Freddie Mac", status: "ok", period: "2026Q2", cet1_mm: 57000, ata_mm: 3905479, ratio: 0.014595, rank: 2, of: 2, percentile: 50, failed_checks: [], cet1_src: prov("2Q26.pdf"), ata_src: prov("2Q26.pdf") },
    ...Array.from({ length: 8 }, (_, i) => ({ slot: i + 3, name: "", provider: "", status: "not configured", period: "", cet1_mm: null, ata_mm: null, ratio: null, rank: null, of: null, percentile: null, failed_checks: [], cet1_src: null, ata_src: null })),
  ],
  stats: { have: 2, slots: 10, top: "Fannie Mae", top_ratio: 0.014882, bottom: "Freddie Mac", bottom_ratio: 0.014595, average: 0.0147385, primary: "Fannie Mae", primary_rank: 1, primary_of: 2, primary_percentile: 100 },
};

export const seriesFixture = (provider: string, ratios: [string, number][]): EntitySeries => ({
  provider,
  series: ratios.map(([period, ratio], i) => ({ period, ratio, cet1_mm: 66000, ata_mm: 66000 / ratio, cet1: prov("a.pdf"), ata: prov("a.pdf"), checks: [], failed: [],
    ratio_change: i ? ratio - ratios[i - 1][1] : null, previous_period: i ? ratios[i - 1][0] : null })),
});

const BENCH = {
  // exposure (USD) and the B1 result for the specified 1% and for an edited 2%, as the engine returns them (strings, full precision)
  2021: { exp: "2426614893000", "0.01": ["24266148930", "24.26614893", "$24.27B", "$24,266,148.93"], "0.02": ["48532297860", "48.53229786", "$48.53B", "$48,532,297.86"] },
  2022: { exp: "2442351095000", "0.01": ["24423510950", "24.42351095", "$24.42B", "$24,423,510.95"], "0.02": ["48847021900", "48.8470219", "$48.85B", "$48,847,021.90"] },
  2023: { exp: "2613623651000", "0.01": ["26136236510", "26.13623651", "$26.14B", "$26,136,236.51"], "0.02": ["52272473020", "52.27247302", "$52.27B", "$52,272,473.02"] },
} as const;

/** API-shaped /benchmarks payload: Benchmark 1 confirmed, Benchmarks 2-10 awaiting confirmation. */
export const benchFixture = (pct: "0.01" | "0.02" = "0.01"): BenchmarksResponse => {
  const names = ["Leverage based CET1 (GSEs)", ...Array.from({ length: 9 }, (_, i) => `Benchmark ${i + 2} (definition required)`)];
  const results: BenchResult[] = [];
  for (let n = 1; n <= 10; n++) {
    for (const fy of [2021, 2022, 2023] as const) {
      const b = BENCH[fy];
      const base = { number: n, name: names[n - 1], fiscal_year: fy, reporting_date: `${fy}-09-30`, depends_on: [] };
      if (n === 1) {
        const [u, bn, text, th] = b[pct];
        results.push({ ...base, status: "ok", message: "", formula: "gnma_total_exposure * adjustment_pct", assumptions: { adjustment_pct: pct },
          calculation: `${Number(b.exp).toLocaleString("en-US")} × ${pct} = ${Number(u).toLocaleString("en-US")}`, result_usd: u, result_billions: bn, result_billions_text: text, result_thousands_text: th,
          inputs: [{ name: "gnma_total_exposure", label: "GNMA Total Maximum Exposure to Loss", kind: "derived", fiscal_year: fy, reporting_date: `${fy}-09-30`, usd: b.exp,
            billions: String(Number(b.exp) / 1e9), billions_text: `$${(Number(b.exp) / 1e9).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}B`,
            source_units: "USD thousands", source_raw: "2,613,623,651", source_report: `annual_report${String(fy).slice(2)}.pdf`, source_url: `https://www.ginniemae.gov/x/annual_report${String(fy).slice(2)}.pdf`,
            location: "PDF p.96 (printed A-20) · Note 2: Summary of Significant Accounting Policies", note: "" }] });
      } else {
        results.push({ ...base, status: "unconfirmed", message: "Formula and assumptions have not been established.", formula: null, assumptions: {}, calculation: "", inputs: [],
          result_usd: null, result_billions: null, result_billions_text: "—", result_thousands_text: null });
      }
    }
  }
  const l = results.find((r) => r.number === 1 && r.fiscal_year === 2023)!;
  const p = results.find((r) => r.number === 1 && r.fiscal_year === 2022)!;
  const diff = BigInt(l.result_usd!) - BigInt(p.result_usd!);
  return {
    units: { engine: "USD", display: "USD (billions)", divisor: 1_000_000_000, display_decimals: 2, pipeline: "Source values are converted once to exact USD; formulas run in USD at full precision; results are divided by 1,000,000,000 once for display." },
    assumptions_version: pct === "0.01" ? "4c43ee77e5f6" : "a1b2c3d4e5f6",
    definitions: names.map((name, i) => ({ number: i + 1, key: `k${i + 1}`, name, description: i ? "Formula and assumptions have not been established." : "GNMA Total Maximum Exposure to Loss multiplied by the 1% leverage-based CET1 adjustment.",
      formula: i ? null : "gnma_total_exposure * adjustment_pct", status: i ? "unconfirmed" : "confirmed", confirmed: !i, reference: i ? "No definition supplied; requires business confirmation." : "Business specification",
      problem: null, inputs: i ? [] : ["gnma_total_exposure"],
      assumptions: i ? [] : [{ name: "adjustment_pct", label: "Adjustment percentage", unit: "fraction (0.01 = 1%)", value: pct, default: "0.01", min: "0", max: "1", min_exclusive: true, editable: true }] })),
    periods: [2021, 2022, 2023].map((fy) => ({ fiscal_year: fy, reporting_date: `${fy}-09-30` })),
    inputs: ([2021, 2022, 2023] as const).flatMap((fy) => (["gnma_outstanding_mbs", "gnma_total_exposure"] as const).map((name) => ({
      name, label: name === "gnma_total_exposure" ? "GNMA Total Maximum Exposure to Loss" : "GNMA Outstanding MBS", kind: name === "gnma_total_exposure" ? "derived" as const : "official" as const, fiscal_year: fy,
      reporting_date: `${fy}-09-30`, usd: BENCH[fy].exp, billions: String(Number(BENCH[fy].exp) / 1e9), billions_text: `$${(Number(BENCH[fy].exp) / 1e9).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}B`,
      source_units: "USD thousands", source_raw: "2,613,623,651", source_report: `annual_report${String(fy).slice(2)}.pdf`, source_url: "", location: "PDF p.96 (printed A-20)", note: "" }))),
    results,
    summary: names.map((name, i) => i === 0 ? { number: 1, name, status: "confirmed", formula: "gnma_total_exposure * adjustment_pct", latest: l, prior: p,
      yoy: { prior_fiscal_year: 2022, abs_usd: diff.toString(), abs_billions_text: `+$${(Number(diff) / 1e9).toFixed(2)}B`, pct: pct === "0.01" ? 7.0126 : 7.0126 }, periods_calculated: 3, periods_total: 3, problem: null }
      : { number: i + 1, name, status: "unconfirmed", formula: null, latest: null, prior: null, yoy: null, periods_calculated: 0, periods_total: 3, problem: "Formula and assumptions have not been established." }),
    validation: [
      { name: "GNMA Total Maximum Exposure to Loss = Outstanding MBS + Outstanding MBS Commitments", status: "pass", detail: "3 fiscal year(s) checked" },
      { name: "Benchmark 1 uses the business-specified 1% adjustment", status: pct === "0.01" ? "pass" : "warn", detail: pct === "0.01" ? "adjustment_pct = 0.01" : "adjustment_pct has been changed to 0.02" },
      { name: "All benchmarks have a confirmed definition", status: "warn", detail: "Benchmark(s) 2, 3, 4, 5, 6, 7, 8, 9, 10 require business confirmation; no result is shown for them" },
    ],
  };
};

const cell = (value: string, text: string, unit: string, extra: Partial<SourceCell> = {}): SourceCell => ({
  value, text, unit, raw_value: text.replace("%", ""), source_file: "fannie_2023Q4.pdf", source_url: "", table_name: "Exhibit 2.1 · RWA Summary", line_item: "Total (Standardized Approach RWA)",
  column_name: "", location: "p.10", ...extra,
});
const gse = (key: string, name: string, periods: SourcePeriod[], reference: SourceEntityDetail["reference"]): SourceEntityDetail => ({
  key, name, kind: "gse", provider: name,
  metrics: [
    { field: "CET1_amount", label: "CET1 minimum capital requirement", unit: "USD millions" }, { field: "Adjusted_total_assets", label: "Adjusted total assets", unit: "USD millions" },
    { field: "min_capital_ratio", label: "Minimum capital ratio (CET1)", unit: "percent" }, { field: "total_rwa", label: "Total risk-weighted assets", unit: "USD millions" },
    { field: "credit_rwa", label: "Credit risk-weighted assets", unit: "USD millions" },
  ],
  periods, reference,
  validation: [
    { name: "Minimum capital ratio, total RWA and credit RWA found for every stored period", status: "pass", detail: `${periods.length} period(s)` },
    reference ? { name: "December 2023 matches the verification values (min ratio 4.5%, total RWA 1,357,097, credit RWA 1,240,896 $ millions)", status: reference.matches ? "pass" : "fail", detail: "found" }
      : { name: "Independent verification values", status: "warn", detail: "No reference values supplied for this entity" },
  ],
});
const fannieQ = (period: string, label: string, end: string, total: string, credit: string): SourcePeriod => ({
  period, label, period_end: end, checks: [{ name: "rwa_components_sum_to_total", status: "pass", detail: "sums" }],
  values: {
    CET1_amount: cell("61000", "61,000", "USD millions", { table_name: "Exhibit 2.2 · Capital Metrics", line_item: "Common equity tier 1 capital" }),
    Adjusted_total_assets: cell("4552448", "4,552,448", "USD millions", { table_name: "Exhibit 11.1", line_item: "Adjusted total assets" }),
    min_capital_ratio: cell("4.5", "4.5%", "percent", { raw_value: "4.5", table_name: "Exhibit 2.2 · Capital Metrics", column_name: "Minimum Capital Ratio Requirement", line_item: "Common equity tier 1 capital" }),
    total_rwa: cell(total.replace(/,/g, ""), total, "USD millions"),
    credit_rwa: cell(credit.replace(/,/g, ""), credit, "USD millions", { line_item: "Credit risk (Standardized Approach RWA)" }),
  },
});
export const fannieSource = gse("fannie-mae", "Fannie Mae", [
  fannieQ("2023Q3", "September 2023", "2023-09-30", "1,346,280", "1,232,998"), fannieQ("2023Q4", "December 2023", "2023-12-31", "1,357,097", "1,240,896"),
], { period: "2023Q4", label: "December 2023", source: "Provided for verification (December 2023 results)", expected: { min_capital_ratio: "4.5", total_rwa: "1357097", credit_rwa: "1240896" },
  found: { min_capital_ratio: "4.5", total_rwa: "1357097", credit_rwa: "1240896" }, matches: true });
export const freddieSource = gse("freddie-mac", "Freddie Mac", [{
  period: "2023Q4", label: "December 2023", period_end: "2023-12-31", checks: [],
  values: {
    min_capital_ratio: cell("4.5", "4.5%", "percent", { source_file: "4Q23.pdf", table_name: "Table 2.2 · ERCF Available Capital" }),
    total_rwa: cell("1008893", "1,008,893", "USD millions", { source_file: "4Q23.pdf", table_name: "Table 2.1 · Adjusted Total Assets and Standardized RWA" }),
    credit_rwa: cell("884404", "884,404", "USD millions", { source_file: "4Q23.pdf", table_name: "Table 2.1" }),
  },
}], null);
export const sourceIndex = { entities: [
  { key: "fannie-mae", name: "Fannie Mae", kind: "gse", note: "", status: "data", summary: "2 quarterly disclosure(s)" },
  { key: "gnma", name: "GNMA", kind: "gnma", note: "", status: "data", summary: "3 fiscal year(s)" },
  { key: "freddie-mac", name: "Freddie Mac", kind: "gse", note: "", status: "data", summary: "1 quarterly disclosure(s)" },
  { key: "fhlbs", name: "FHLBs", kind: "placeholder", note: "Federal Home Loan Banks", status: "empty", summary: "No source values loaded yet" },
  { key: "fdic", name: "FDIC", kind: "placeholder", note: "Federal Deposit Insurance Corporation", status: "empty", summary: "No source values loaded yet" },
] };

export const routes: Record<string, unknown> = {
  "/source-values": sourceIndex,
  "/source-values/fannie-mae": fannieSource,
  "/source-values/freddie-mac": freddieSource,
  "/source-values/fhlbs": { key: "fhlbs", name: "FHLBs", kind: "placeholder", periods: [], metrics: [], validation: [], reference: null },
  "/benchmarks": benchFixture(),
  "/meta": metaFixture,
  "/peers": peersFixture,
  "/entities": { providers: ["Fannie Mae", "Freddie Mac"], primary: "Fannie Mae" },
  "/entities/Fannie Mae/series": seriesFixture("Fannie Mae", [["2026Q1", 0.0147], ["2026Q2", 0.014882]]),
  "/entities/Freddie Mac/series": seriesFixture("Freddie Mac", [["2026Q1", 0.0144], ["2026Q2", 0.014595]]),
  "/gnma": gnmaFixture,
  "/sources": { observations: [], fetch_log: [], ingest_log: [] },
};
