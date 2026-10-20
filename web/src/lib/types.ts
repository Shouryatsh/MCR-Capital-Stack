export interface Provenance {
  source_file: string;
  table_name: string;
  row_identifier: string;
  field_label: string;
  raw_value: string;
  parsed_value: number;
  units_detected: string;
  units_source: string;
  value_mm: number;
  location: string;
  column_name: string;
  source_url: string;
  ingested_at: string;
}

export interface Meta {
  app_name: string;
  units: string;
  ratio_decimals: number;
  primary_provider: string;
  last_updated: string | null;
  has_cet1: boolean;
  has_gnma: boolean;
  periods: string[];
}

export interface PeerRow {
  slot: number;
  name: string;
  provider: string;
  status: string;
  period: string;
  cet1_mm: number | null;
  ata_mm: number | null;
  ratio: number | null;
  rank: number | null;
  of: number | null;
  percentile: number | null;
  failed_checks: string[];
  cet1_src: Provenance | null;
  ata_src: Provenance | null;
}

export interface PeerStats {
  have: number;
  slots: number;
  top: string;
  top_ratio: number;
  bottom: string;
  bottom_ratio: number;
  average: number;
  primary: string | null;
  primary_rank: number | null;
  primary_of: number | null;
  primary_percentile: number | null;
}

export interface PeersResponse {
  periods: string[];
  period: string | null;
  rows: PeerRow[];
  stats: PeerStats | null;
}

export interface EntitiesResponse {
  providers: string[];
  primary: string | null;
}

export interface Check {
  name: string;
  status: string;
  detail: string;
}

export interface SeriesPoint {
  period: string;
  ratio: number;
  cet1_mm: number;
  ata_mm: number;
  cet1: Provenance;
  ata: Provenance;
  checks: Check[];
  failed: string[];
  ratio_change: number | null;
  previous_period: string | null;
}

export interface EntitySeries {
  provider: string;
  series: SeriesPoint[];
}

export interface GnmaYoy {
  prior_fiscal_year: number;
  total_abs_usd: number;
  total_pct: number | null;
  mbs_abs_usd: number;
  mbs_pct: number | null;
  commitments_abs_usd: number;
  commitments_pct: number | null;
  rounded: boolean;
}

export interface GnmaFigure {
  fiscal_year: number;
  reporting_date: string;
  role: "current" | "comparative";
  source_report: string;
  source_url: string;
  pdf_page: number;
  printed_page: string;
  note: string;
  table_title: string;
  table_kind: string;
  units: string;
  mbs_raw: string;
  commitments_raw: string;
  total_raw: string;
  mbs_usd: number;
  commitments_usd: number;
  total_usd: number;
  reported_total_usd: number | null;
  precision_usd: number;
  flags: string[];
  ok: boolean;
  mbs_usd_text: string;
  commitments_usd_text: string;
  total_usd_text: string;
  total_published: string;
  mbs_published: string;
  commitments_published: string;
  yoy?: GnmaYoy | null;
  latest?: boolean;
}

export interface GnmaValidation {
  name: string;
  status: "pass" | "warn" | "fail";
  detail: string;
}

export interface GnmaReconciliation {
  fiscal_year: number;
  component: string;
  report_a: string;
  usd_a: number;
  report_b: string;
  usd_b: number;
  difference_usd: number;
  status: string;
}

export interface GnmaGap {
  fiscal_year: number;
  source_report: string;
  reason: string;
}

export interface GnmaResponse {
  source: { index_url: string; provider: string };
  series: GnmaFigure[];
  observations: GnmaFigure[];
  validation: GnmaValidation[];
  reconciliation: GnmaReconciliation[];
  gaps: GnmaGap[];
  reference: Record<string, { mbs: number; commitments: number; total: number }>;
}

export interface RefreshStatus {
  running: boolean;
  started: string | null;
  finished: string | null;
  reports: number;
  with_figures: number;
  error: string | null;
}

export interface SourcesResponse {
  observations: Record<string, string | number | null>[];
  fetch_log: Record<string, string | null>[];
  ingest_log: Record<string, string | null>[];
}

export interface BenchInput {
  name: string;
  label: string;
  kind: "official" | "derived";
  /** "ratio" inputs are dimensionless: `usd` is then the exact fraction and `billions_text` is a percent. */
  unit?: "usd" | "ratio";
  fiscal_year: number;
  reporting_date: string;
  usd: string;
  billions: string;
  billions_text: string;
  source_units: string;
  source_raw: string;
  source_report: string;
  source_url: string;
  location: string;
  note: string;
}

export interface BenchResult {
  number: number;
  name: string;
  fiscal_year: number;
  reporting_date: string;
  status: "ok" | "missing_input" | "unconfirmed" | "invalid_assumption" | "error";
  message: string;
  formula: string | null;
  calculation: string;
  assumptions: Record<string, string>;
  inputs: BenchInput[];
  depends_on: string[];
  result_usd: string | null;
  result_billions: string | null;
  result_billions_text: string;
  result_thousands_text: string | null;
}

export interface BenchAssumption {
  name: string;
  label: string;
  unit: string;
  value: string;
  default: string | null;
  min: string | null;
  max: string | null;
  min_exclusive: boolean;
  editable: boolean;
}

export interface BenchDefinition {
  number: number;
  key: string;
  name: string;
  description: string;
  formula: string | null;
  status: string;
  confirmed: boolean;
  reference: string;
  problem: string | null;
  inputs: string[];
  assumptions: BenchAssumption[];
}

export interface BenchSummary {
  number: number;
  name: string;
  status: string;
  formula: string | null;
  latest: BenchResult | null;
  prior: BenchResult | null;
  yoy: { prior_fiscal_year: number; abs_usd: string; abs_billions_text: string; pct: number | null } | null;
  periods_calculated: number;
  periods_total: number;
  problem: string | null;
}

export interface BenchmarksResponse {
  units: { engine: string; display: string; divisor: number; display_decimals: number; pipeline: string };
  assumptions_version: string;
  definitions: BenchDefinition[];
  periods: { fiscal_year: number; reporting_date: string }[];
  inputs: BenchInput[];
  results: BenchResult[];
  summary: BenchSummary[];
  validation: GnmaValidation[];
}

export interface SourceEntity {
  key: string;
  name: string;
  kind: "gse" | "gnma" | "fhlb" | "gfee" | "fdic" | "placeholder";
  note: string;
  status: "data" | "empty";
  summary: string;
}

export interface SourceCell {
  value: string;
  text: string;
  unit: string;
  raw_value: string;
  source_file: string;
  source_url: string;
  table_name: string;
  line_item: string;
  column_name: string;
  location: string;
}

export interface SourcePeriod {
  period: string;
  label: string;
  period_end: string;
  values: Record<string, SourceCell>;
  checks: { name: string; status: "pass" | "warn" | "fail"; detail: string }[];
}

export interface SourceEntityDetail {
  key: string;
  name: string;
  kind: string;
  provider?: string;
  note?: string;
  metrics: { field: string; label: string; unit: string }[];
  periods: SourcePeriod[];
  reference: { period: string; label: string; source: string; expected: Record<string, string>; found: Record<string, string | null>; matches: boolean } | null;
  validation: GnmaValidation[];
}

export interface FhlbCell {
  value: number;
  text: string;
  unit: string;
  raw_value?: string;
  source_file?: string;
  source_url?: string;
  table_name?: string;
  location?: string;
  derived?: boolean;
  source_note?: string;
}

export interface FhlbPeriod {
  period: string;
  report_date: string;
  label: string;
  period_end: string;
  derived_banks?: string[];
  banks: Record<string, Record<string, FhlbCell>>;
}

export interface FhlbField {
  field: string;
  label: string;
  unit: string;
  table: string;
  derived?: boolean;
  formula?: string;
}

export interface FhlbGap {
  period: string;
  reason: string;
}

export interface FhlbResponse {
  source: { index_url: string; provider: string };
  banks: string[];
  fields: FhlbField[];
  periods: FhlbPeriod[];
  gaps: FhlbGap[];
  validation: GnmaValidation[];
}

export interface GfeeDataPoint {
  report_key: string;
  report_title: string;
  source_url: string;
  total_bps: number;
  ongoing_bps: number | null;
  upfront_bps: number | null;
  gap_bps: number | null;
  quote: string;
  restated_from: number | null;
  restated_note: string;
}

export interface GfeeYear {
  data_year: string;
  population: string;
  primary: GfeeDataPoint;
  restatements: GfeeDataPoint[];
}

export interface GfeeGap {
  report_key: string;
  reason: string;
}

export interface GfeeResponse {
  source: { index_url: string; provider: string };
  years: GfeeYear[];
  gaps: GfeeGap[];
  validation: GnmaValidation[];
  summary: { years: number; first_year: string | null; last_year: string | null; reports: number };
}

export interface FdicDataPoint {
  report_key: string;
  report_title: string;
  source_url: string;
  fund_balance_ending: number | null;
  fund_balance_prior: number | null;
  fund_balance_quote: string;
  min_reserve_ratio_pct: number | null;
  min_reserve_ratio_quote: string;
  insured_deposits_trillions: number | null;
  insured_deposits_as_of: string;
  insured_deposits_quote: string;
}

export interface FdicGap {
  report_key: string;
  reason: string;
}

export interface FdicResponse {
  source: { index_url: string; provider: string };
  years: FdicDataPoint[];
  gaps: FdicGap[];
  validation: GnmaValidation[];
  summary: { years: number; first_year: string | null; last_year: string | null; reports: number };
}
