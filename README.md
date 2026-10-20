# MCR Dashboard

CET1-based leverage ratio for Fannie Mae and Freddie Mac (plus up to 8 more benchmarks you configure), with the file, table and line item behind every number. Python + Streamlit + SQLite. **All dollar amounts are $ millions.**

> **CET1-based leverage ratio = CET1 amount ÷ Adjusted total assets.**
> For the GSEs, "CET1 amount" is the **CET1 minimum capital requirement** (Minimum Capital Requirement column), as you specified. It is published in $ billions and converted to millions (61 → 61,000). Because it is rounded to the nearest $1bn, GSE ratios are precise to about ±0.01 percentage points.

## Setup and run
```
pip install -r requirements.txt
python scripts/fetch.py --all        # one-off: download + parse every Fannie Mae and Freddie Mac disclosure
python scripts/fetch.py --ginnie     # download + extract every English Ginnie Mae annual report (GNMA exposure)
python scripts/fetch.py --fhlb       # download + extract every FHLB Office of Finance Combined Financial Report (Tables 9.1/9.2)
python scripts/fetch.py --gfee       # download + extract every FHFA Single-Family Guarantee Fees report (Total Average Guarantee Fee, annual)
python scripts/fetch.py --fdic       # download + extract every FDIC Annual Report Financial Section (Fund Balance, Minimum Reserve Ratio, Estimated Insured Deposits)
python scripts/serve.py              # Streamlit dev server -> http://localhost:8503
python scripts/serve.py --prod       # headless, file watcher off
python -m pytest                     # 147 Python tests
cd web && npm install && npm run build && cd ..
python scripts/serve_web.py          # React Aurora Glass UI + JSON API -> http://localhost:8504
cd web && npm test                   # 70 frontend tests;  npm run lint = type-check
```
Weekly/daily refresh (cron): `0 7 * * * cd /path/to/mcr-dashboard && python scripts/fetch.py >> logs/fetch.log 2>&1`

Optional access token (placeholder auth): set `MCR_TOKEN=...` before starting; the Streamlit app asks for it in the sidebar and the React UI shows a token prompt (the API expects it in an `X-MCR-Token` header).

## Pages
Streamlit (port 8503), after the tab reorganisation:
* **Overview** = the former Summary content: 10-slot table, narrative, CSV download.
* **Benchmarks** = the former Overview content: entity KPI cards, provenance, ratio history and peer comparison.
* **Summary** = the former Benchmarks content (period bar chart, rank/percentile table) plus the **GNMA Maximum Exposure to Loss** section.
* Data Sources (every source file, fetch log, ingest log, "fetch now" buttons incl. GNMA) · Uploads · Settings (precision, file-name pattern, benchmark slots, mapping editor).
Hovering a chart point shows the CET1 and adjusted-total-assets source (file, page, table, line item).

## React frontend (Aurora Glass UI, port 8504)
`web/` is a React + TypeScript + Tailwind + Recharts + Framer Motion + Lucide app served by `scripts/serve_web.py` together with a read-only JSON API (`mcr/api.py`, FastAPI). The API calls the same `store`, `ratio` and `gnma` code as Streamlit, so numbers, checks and provenance are identical; money is sent as exact integers and pre-formatted text. Streamlit is unchanged and keeps Uploads and Settings (linked from the sidebar).

| Route | Content |
|---|---|
| `/` Overview | Former Summary content (peer table, narrative, CSV) + KPI cards incl. the latest GNMA exposure |
| `/benchmark` Benchmark | Former Overview content (entity KPIs, provenance, ratio history, compare overlay) |
| `/summary` Summary | Former Benchmarks content (ranked bar chart, slot table) |
| `/source-values` Source values | As-published figures, one sub-tab per entity: **Fannie Mae**, **GNMA** (the former GNMA analytics page), **Freddie Mac**, **FHLBs** (Tables 9.1/9.2), **GSE GFEE** (FHFA Total Average Guarantee Fee, annual), **FDIC** (Deposit Insurance Fund headline figures, annual). `/gnma` redirects to the GNMA sub-tab |
| `/sources` Data sources | Source files, fetch and ingest logs, GNMA fetch button |

Endpoints: `GET /api/meta · /peers?period= · /entities · /entities/{provider}/series · /gnma · /fhlb · /gfee · /sources`, `POST|GET /api/gnma/refresh`, `GET /api/health` (docs at `/api/docs`). For frontend development run `python scripts/serve_web.py --reload` and `npm run dev` in `web/` (port 5173, proxies `/api`).
Design system: tokens and glass utilities in `web/src/index.css`; components in `web/src/components`. Animations are CSS/transform based and are disabled under `prefers-reduced-motion`; `backdrop-filter` has a solid fallback; tables and numbers sit on near-opaque surfaces.

## GNMA Maximum Exposure to Loss
**Total Maximum Exposure to Loss = Outstanding MBS + Outstanding MBS commitments**, extracted from the Notes to the Financial Statements of Ginnie Mae's official English annual reports (`https://www.ginniemae.gov/about_us/what_we_do/Annual_Reports/annual_reportYY.pdf`; index page `https://www.ginniemae.gov/about-us/what-we-do/budget-performance/annual-reports`). `python scripts/fetch.py --ginnie` (or the Data Sources buttons) downloads FY1999 onward to `raw/ginnie/`, extracts with `mcr/gnma.py`, and stores results in `gnma_exposure` / `gnma_gaps` (SQLite).
* **Units:** read from each file ("Dollars in thousands" FY2017+, "Dollars in billions" FY2012–FY2016); stored as exact integer US dollars (Decimal arithmetic, TEXT in SQLite). The dashboard shows the figure as published (e.g. `$2,613,623,651` USD thousands) and in full dollars (`$2,613,623,651,000`). FY2012–FY2016 are published rounded to $0.1bn/$1bn and are labelled as such.
* **Coverage:** FY2011 (comparative) and FY2012–FY2025 are extracted. FY1999–FY2010 are documented gaps: no table, or (FY1999) a table drawn without a text layer. FY2026 is not yet published. Nothing is estimated.
* **Traceability per observation:** source report and URL, fiscal year, reporting date, PDF page, printed page label, note heading, table, printed values and flags.
* **Validation:** total = MBS + commitments for every row; printed total equals computed total; FY2023 = $2,613,623,651 and FY2022 = $2,442,351,095 (thousands) exactly; a year header the text layer drops must be confirmed by another report; comparatives in successive reports are reconciled (one real restatement is surfaced: FY2015 commitments $129bn → $160bn in the FY2016 report).


## FHLBs Table 9.1 / 9.2 (risk-based and regulatory capital requirements)
Extracted from **Table 9.1 – Risk-Based Capital Requirements** and **Table 9.2 – Regulatory Capital Requirements** in the Federal Home Loan Banks Office of Finance quarterly **Combined Financial Report** (`https://www.fhlb-of.com/investor-resources/financial-reports/combined/`). `python scripts/fetch.py --fhlb` (or the Data Sources button) downloads each quarter's PDF to `raw/fhlb/`, extracts with `mcr/fhlb.py`, and stores results in `fhlb_capital` / `fhlb_gaps` (SQLite). Tables are located by title text, not by number, because the note numbering (9.1/9.2, 11.1/11.2, 13.1/13.2, 15.1/15.2, 16.1/16.2) shifts across years.
* **Fields ($ millions unless noted):** risk-based capital minimum requirement and actual; regulatory capital ratio minimum requirement and actual (%); regulatory capital minimum requirement and actual.
* **Coverage:** 42 quarterly reports, 2016Q1–2026Q2, all 11 FHLBanks (Atlanta, Boston, Chicago, Cincinnati, Dallas, Des Moines, Indianapolis, New York, Pittsburgh, San Francisco, Topeka) plus the system-wide **Combined** row, published in only some periods (and with 3 values instead of 4, since Combined omits a minimum ratio).
* **Traceability per observation:** source file and URL, table name, page/location, raw printed text, parsed value, unit.
* **Validation (`mcr/fhlb.py::validate`):** regulatory capital minimum ratio is exactly 4.00% for every bank/period; Combined regulatory capital reconciles to the sum of the 11 banks within a $5mm tolerance; all 11 FHLBanks are present for every period. All checks pass on the full dataset with zero gaps.

## GSE GFEE: FHFA Total Average Guarantee Fee (annual)
The **Total Average Guarantee Fee** charged by Fannie Mae and Freddie Mac on single-family mortgages, as published in FHFA's **Single-Family Guarantee Fees** report series (`https://www.fhfa.gov/reports/single-family-guarantee-fees`). `python scripts/fetch.py --gfee` downloads each report PDF to `raw/gfee/`, extracts with `mcr/gfee.py`, and stores results in `gfee_annual` / `gfee_gaps` (SQLite).
* **Scope (annual only, by design):** FHFA publishes this figure only as a calendar-year average; there is no consistently published quarterly "Total Average Guarantee Fee" anywhere in the report series (the one quarterly breakdown found, in the 2012 report's Table 15, is segmented by lender acquisition-volume group, not an overall total). This is a documented source limitation, flagged as a `warn`-status check, not a parsing gap.
* **Coverage:** 17 reports (2007–2024, one report per year from 2012 onward, two-year combined reports for 2007–2011), 18 calendar years, 44 data points. One additional report (`state-level.pdf`, state-level g-fee variation) is tracked in `mcr/gfee.py`'s report metadata but intentionally excluded from the annual series — different scope, not a source of the national annual total.
* **Parsing approach ("verify-quote"):** each calendar year's figure is transcribed directly from its report's own sentence/table (stored as a `quote`), since the report formats are not consistent enough across 17 years for one generic table parser (clean table 2022+; single-sentence narrative 2018–2021; multi-year "Chart 1" prose 2012–2017; dual-population standard-vs-all-loans narrative 2007–2012). At every ingest, `mcr/gfee.py` re-opens the PDF and confirms the quote is still literally present in the extracted text; if not, the point is dropped and recorded as a gap rather than kept stale.
* **Restatements and populations, never collapsed:** FHFA periodically restates prior years (methodology changes, e.g. the 2018 report's inclusion of buy-up/buy-down adjustments; lender/model data revisions). Every observation is kept and tagged with the report that published it — a given year can have more than one value, shown in the UI as a "primary" figure (from the report whose own title year matches the data year) plus every other report's restated figure. The 2007–2012 reports additionally report two parallel populations for the same year ("standard loans" vs. "all loans" including HARP and flexible-refinance loans); both are kept, tagged, and never reconciled into one number.
* **Validation (`mcr/gfee.py::validate`):** an "all loans" observation exists for every year 2007–2024; every restatement carries an explanatory note; the quarterly-data limitation is surfaced as an explicit warning.

## FDIC: Deposit Insurance Fund (DIF) headline figures (annual)
Three headline **Deposit Insurance Fund** figures transcribed from the "Financial Section" of each year's FDIC **Annual Report** (`https://www.fdic.gov/financial-reports/annual-reports`). `python scripts/fetch.py --fdic` downloads each year's Financial Section PDF to `raw/fdic/`, extracts with `mcr/fdic.py`, and stores results in `fdic_annual` / `fdic_gaps` (SQLite).
* **Fields:** Fund Balance - Ending ($ thousands, exact, from the Statement of Income and Fund Balance — the same report's own stated prior-year figure is kept alongside it for cross-checking); Minimum Reserve Ratio (%, the DIF's statutory floor in effect that year — 1.15% under the 2005 Reform Act for 2006–2009, raised to 1.35% by the Dodd-Frank Act for 2010–2024 — deliberately distinct from the FDIC Board's discretionary Designated Reserve Ratio target, e.g. 2.0% from 2011 onward, which is not what is stored); Estimated Insured Deposits ($ trillions, rounded to $0.1T, from the "Off-Balance-Sheet Exposure: Deposit Insurance" note, each with its own "as of" date that is not always December 31 — several years use September 30 of the data year).
* **Coverage:** 19 reports, calendar years 2006–2024. 2020–2024 downloaded directly from `www.fdic.gov`; 2006–2018 (not split into numbered sections pre-2019) retrieved from `archive.fdic.gov` via the Wayback Machine.
* **Parsing approach ("verify-quote", per-metric):** each of the three figures is transcribed from its own sentence/table (stored as a `quote`) and independently re-verified against the PDF's own extracted text at every ingest. Unlike GFEE's whole-point model, a quote that can no longer be located drops only that one metric for that year — the other two are kept if their own quotes still verify.
* **No restatements:** unlike GFEE, every FDIC report_key maps 1:1 to a single calendar year with no competing populations or genuine prior-year restatements — confirmed by cross-checking the full 2006–2024 Fund Balance chain (each year's reported prior-year figure exactly matches the previous year's own reported ending figure, including the 2021 report's apparent four-number sequence, which is a text-extraction column-ordering artifact, not an actual restatement).
* **Validation (`mcr/fdic.py::validate`):** all three figures exist for every year 2006–2024; the Fund Balance - Ending chain is internally consistent year-over-year; the Minimum Reserve Ratio matches the statutory floor for every year; Estimated Insured Deposits carries an explicit "as of" date for every year.

## Demo: upload a file and verify the ratio and provenance
1. Settings → Mappings → add provider **BankA**: CET1 sheet `CapitalTable`, field `Common Equity Tier 1 capital`; ATA sheet `AssetsTable`, field `Adjusted total assets`. Save.
2. Settings → Benchmarks: set slot 3 to name `Bank A`, provider `BankA`. Save.
3. Uploads → choose `sample_data/BankA_20260930_disclosure.xlsx` → **Parse uploaded files**.
4. Expect: CET1 amount 4,250; Adjusted total assets 61,800 ($ millions); ratio 6.88%; provenance `BankA_20260930_disclosure.xlsx · CapitalTable · Common Equity Tier 1 capital` (cell `CapitalTable!R4C2`) and `AssetsTable · Adjusted total assets`.
5. Overview → entity BankA shows the same values and the provenance expanders. Benchmarks → period 2026Q3 ranks it.

PDFs (Fannie Mae / Freddie Mac) need no mapping setup: upload e.g. `tests/fixtures/freddie_2Q26.pdf` and the provider is detected from the cover page.

## Uploads
Single or bulk; `.pdf`, `.xlsx`, `.csv`, or `.zip` packages. Checks: extension allow-list, 50 MB limit, file signature (a renamed `.exe` or a text file called `.pdf` is rejected), zip limits (60 members, 200 MB unpacked, names flattened so `../` cannot escape). Spreadsheets are matched by the configurable file-name pattern `ProviderName_YYYYMMDD_disclosure.xlsx` (the date gives the calendar quarter). "Only process the newest file per provider" picks the newest by filename date, else modification time. Errors name the file, field and cause (e.g. `[x.xlsx · 2026Q3] field not found: 'CET1_amount' (label 'Foo' with a number beside it not found on sheet 'CapitalTable')`).

## Mapping guide (`config/mappings.json`, editable in Settings)
Spreadsheet provider (`"kind": "tabular"`):
```json
{"BankA": {"kind": "tabular", "fields": {
  "CET1_amount":           {"sheet": "CapitalTable", "field": "Common Equity Tier 1 capital", "value_column": "Amount", "units": "millions"},
  "Adjusted_total_assets": {"sheet": "AssetsTable",  "field": "Adjusted total assets"}}}}
```
`field` is matched on the label cell (case/punctuation/footnote-insensitive; exact match preferred over contains); the value is the first number to its right (or under `value_column`). `sheet`, `value_column` and `units` are optional. **Units are detected from the file** ("(Dollars in millions)", "$ billions", "(in thousands)" in the row or any row above it). `units` is only a fallback when the file states none, and a detected unit always wins. No unit anywhere and no fallback → an error, never a guess. If a label matches several different numbers you get an "ambiguous mapping" error listing the cells; set `sheet`/`value_column`.

PDF provider (`"kind": "pdf"`): `table_title` (matched by title, not number: Fannie Mae's capital-metrics exhibit is 2.1 through Q3 2023 and 2.2 after), `anchor_regex` for the row label, `end_word` (last word of a wrapped label), `n_cells`/`integer_cells` (expected shape of the row), and `cell_index` (which number to take). The defaults encode the real column orders: **Fannie Mae** Exhibit 2.2 has 6 cells (Available | **Minimum** | Total | 3 ratios) → index 1; **Freddie Mac** Table 2.2 has 5 cells (**Minimum** | Buffers | Total | Available | Shortfall) → index 0. Adjusted total assets: Fannie Exhibit 11.1 Part 1 line 7; Freddie Table 11.1 "Adjusted Total Assets".

## Provenance
Each stored value keeps: `source_file`, `sheet_or_table_name`, `row_identifier`, `field_label`, `raw_value` (as printed, e.g. `$3,833,729`), `parsed_value`, `units_detected` (+ whether detected or from the mapping), `value_mm`, page/cell location, column name, source URL, ingest time (SQLite `data/mcr.db`, table `observations`).
Example, Freddie Mac 2025Q1: CET1 amount 49,000 ($ millions) ← `freddie_1Q25.pdf, p.10 · Table 2.2 · ERCF Available Capital and Capital Requirements · CET1 capital [Minimum Capital Requirement]`, printed `49` ($ billions); Adjusted total assets 3,833,729 ← `p.28 · Table 11.1 · Adjusted Total Assets`, printed `$3,833,729`.

## Validation (GSE PDFs)
Adjusted total assets must match the second table that repeats it (Fannie Exhibit 2.2 in $bn, Freddie Table 2.1 in $mm) to within that table's rounding; the CET1 minimum must be within $1bn of 4.5% × standardized RWA; both values must be positive. Failures are stored, flagged on screen, and never hidden.

## Freddie Mac fetcher
`scripts/fetch.py` (or Data Sources → Fetch) reads https://www.freddiemac.com/investors/ercf-public-disclosure, lists the `*_ercf_public_disclosure.pdf` links (the site currently offers 3Q23–2Q26), picks the newest by the quarter in the file name, saves it to `raw/freddie/`, records URL, size and `Last-Modified` in the fetch log, and parses it. The page offers PDFs only (no spreadsheets).

## Port conflicts
`scripts/serve.py` checks the port (default `MCR_PORT` or 8503) before starting:
* an **older MCR Dashboard** there is stopped, the event is logged in `logs/conflicts.log`, and its command line is saved;
* **any other program** is left running, MCR takes the next free port and logs it (`--kill-foreign` stops it only if you explicitly ask).

Rollback: `python scripts/serve.py --rollback` relaunches the last stopped command line (`data/last_stopped.json`); the log tells you what was stopped and when. The original Fannie Mae-only dashboard (`../fannie-capital`, port 8502) is a separate app and unaffected.

## Acceptance status
| Criterion | Status |
|---|---|
| Upload a file → CET1, ATA, ratio, provenance shown | Done (xlsx/csv/pdf/zip; see demo) |
| Freddie Mac fetch retrieves and parses ≥1 file | Done, all 12 PDFs (3Q23–2Q26) parse with all checks passing |
| Benchmarks page lists 10 peers with ratios and ranks | **Partly:** 10 slots exist; only Fannie Mae and Freddie Mac are configured. Name the other 8 in Settings → Benchmarks and upload their files (mappings are needed for them) |
| Units labelled as millions everywhere | Done (the GSE minimum is shown converted; the printed unit is kept in provenance) |
| No duplicate dashboard at the path | Done (`serve.py`) |

## Source values: minimum capital ratio and risk-weighted assets (Fannie Mae, Freddie Mac)
`mcr/capital.py` reads three more values from each ERCF disclosure PDF, using the same position-aware reader and provenance as CET1 / adjusted total assets, and stores them as exact decimals in `capital_metrics` (with `capital_checks`):

| Value | Fannie Mae | Freddie Mac | Unit |
|---|---|---|---|
| Minimum capital ratio (CET1) | Exhibit 2.2, CET1 row, *Minimum Capital Ratio Requirement* | Table 2.2, risk-based capital **ratios**, CET1 row, *Minimum Capital Requirement* | percent |
| Total risk-weighted assets | Exhibit 2.1 *RWA Summary*, Total | Table 2.1, Risk-weighted Assets (Standardized Approach) | $ millions |
| Credit risk-weighted assets | Exhibit 2.1 *RWA Summary*, Credit risk | Table 2.1, Credit Risk | $ millions |

Tables are matched by title, not exhibit number. RWA is read from the unrounded **millions** tables (Fannie's Exhibit 2.2 also shows it rounded to $ billions, which is not used). Verified: Fannie Mae December 2023 = 4.5%, 1,357,097 and 1,240,896; Freddie Mac December 2023 = 4.5%, 1,008,893 and 884,404. All 27 local disclosures (Fannie 2022Q4–2026Q2, Freddie 3Q23–2Q26) extract with every check passing.
Checks per period: credit RWA is within total; credit + market + operational RWA equals total exactly; minimum ratio × total RWA is within $1bn of the published CET1 minimum amount (that amount is published rounded to $1bn). A value that cannot be read is flagged and not stored.
New disclosures are captured automatically by the normal ingest. To re-read the local PDFs: `python scripts/fetch.py --capital`. The entity list is `config/source_entities.json` (add entities without code changes); `GET /api/source-values` and `/api/source-values/{key}`.

## GNMA-adjusted benchmarks and the Benchmark Calculations tab
`mcr/benchmarks.py` is the only place benchmark maths lives; the React UI just displays what `GET /api/benchmarks` returns. Definitions are data in `config/benchmarks.json` (created from `DEFAULT_BENCHMARKS`): a formula over named inputs, assumptions and other benchmarks (`benchmark_<n>`), using only `+ - * / ( )`, numbers and names.

| # | Benchmark | Formula | Status |
|---|---|---|---|
| 1 | Leverage based CET1 (GSEs) | `gnma_total_exposure * adjustment_pct` with `adjustment_pct = 0.01` | **Confirmed** |
| 2 | GSE Risk Based Capital | `gnma_total_exposure * risk_weight_pct * minimum_cet1_ratio_pct` with `risk_weight_pct = 0.17`, `minimum_cet1_ratio_pct = 0.045` | **Confirmed** |
| 3–10 | "Benchmark N (definition required)" | none | **Requires business confirmation**: no formula exists in the project, its documentation or the supplied requirements, so no number is produced |

To activate one, set its `status` to `"confirmed"` and supply `formula`, `assumptions` and `assumption_meta` in `config/benchmarks.json`. Available inputs: `gnma_total_exposure`, `gnma_outstanding_mbs`, `gnma_outstanding_mbs_commitments`, and `cet1_<provider>` / `ata_<provider>` (e.g. `cet1_fannie_mae`), the last two only for the quarter ending on the GNMA fiscal year end (Sept 30). Missing inputs produce a flagged "missing input", never a substituted value; circular dependencies, unknown inputs, division by zero and out-of-range assumptions are reported per benchmark and isolated from the others.

**Units (one conversion per stage):** source values keep their published units (GNMA USD thousands; CET1/assets $ millions or billions) → converted once to exact USD (`Decimal`) → formulas run in USD at 60-digit precision, with no intermediate rounding → the final USD result is divided by 1,000,000,000 once for display (`$26.14B`, two decimals; full precision such as `26.13623651` is in the calculation details). Year-over-year changes use the unrounded values.

**Benchmark 1, September 30, 2023:** GNMA exposure `$2,613,623,651` is printed in **USD thousands**, i.e. $2,613,623,651,000. 1% = **$26,136,236,510 = $26.14B**, which is `$26,136,236.51` in USD thousands (the figure in the specification). Treating the printed number as whole dollars would give $0.03B, which is 1,000× too small, so that reading is rejected by a unit-sanity validation and a test.

**Benchmark 2, September 30, 2023:** the same GNMA exposure ($2,613,623,651,000) × 17% risk weight × 4.5% minimum CET1 capital ratio = **$19,994,220,930.15 = $19.99B**.

React: the **Benchmark** tab leads with the benchmark KPI cards, history chart and a 10-row comparison table (all USD billions), followed by the entity view (CET1 and adjusted total assets stay in $ millions, labelled). The **Benchmark Calculations** tab has A. Source data (official vs derived inputs with units and sources), B. Assumptions (editable fields, validated server-side with immediate recalculation, `PUT|DELETE /api/benchmarks/{n}/assumptions/{name}`) and C. Results with expandable step-by-step calculations, benchmark / fiscal-year filters and a validation panel. `assumptions_version` identifies the exact set of formulas and assumptions behind the numbers.

## Limitations
* Benchmarks 2–10 have no confirmed definition (see above). The Streamlit app does not show the benchmark calculations; they are React-only.
* Two front ends over one data layer: Streamlit (all pages, incl. Uploads and Settings) and the React UI (read-only analytics: Overview, Benchmark, Summary, GNMA analytics, Data sources). Uploads and Settings are not re-implemented in React; the API is read-only apart from the GNMA refresh action.
* The 8 additional peers are not defined yet; non-GSE banks do not publish an ERCF "minimum capital requirement", so for them the CET1 amount is whatever line you map (typically reported CET1 capital), which is a different definition than the GSE ratio. The Summary shows the provenance so the difference is visible.
* The token gate is a placeholder, not production authentication.
