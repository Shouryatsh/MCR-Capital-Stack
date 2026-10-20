import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";


import { gnmaFixture, routes } from "./fixtures";
import { mockApi, renderApp } from "./helpers";

const h1 = () => screen.getByRole("heading", { level: 1 });

afterEach(() => vi.unstubAllGlobals());

describe("navigation and the tab mapping", () => {
  it("lists the sections in order with the current page marked", async () => {
    mockApi();
    renderApp("/");
    const nav = await screen.findByRole("navigation", { name: "Primary" });
    expect(within(nav).getAllByRole("link").map((a) => a.textContent?.replace("(current page)", ""))).toEqual(
      ["Overview", "Benchmark", "Benchmark Calculations", "Summary", "Source values", "Data sources"]);
    expect(within(nav).getByRole("link", { name: /Overview/ })).toHaveAttribute("aria-current", "page");
  });

  it("Overview shows the former Summary content: narrative, ten-slot table and CSV download", async () => {
    mockApi();
    renderApp("/");
    expect(await screen.findByText(/2 of 10 benchmarks have data/)).toBeInTheDocument();
    expect(screen.getByText(/Fannie Mae has the highest CET1-based leverage ratio \(1\.49%\)/)).toBeInTheDocument();
    expect(screen.getByText(/8 benchmark slot\(s\) are not configured/)).toBeInTheDocument();
    expect(screen.getByRole("table", { name: "Benchmark summary for 2026Q2" })).toBeInTheDocument();
    expect(screen.getAllByRole("row")).toHaveLength(11); // header + 10 slots
    expect(screen.getByRole("button", { name: /Download summary CSV/ })).toBeInTheDocument();
    expect(screen.queryByLabelText("Entity")).not.toBeInTheDocument(); // that is the Benchmark page
    expect(h1()).toHaveTextContent("Overview");
  });

  it("Benchmark shows the former Overview content: entity picker, KPIs, provenance, ratio history", async () => {
    mockApi();
    renderApp("/benchmark");
    expect(await screen.findByRole("heading", { name: /Fannie Mae · 2026Q2/ })).toBeInTheDocument();
    expect(screen.getByLabelText("Entity")).toHaveValue("Fannie Mae");
    expect(screen.getByRole("button", { name: "Freddie Mac", pressed: true })).toBeInTheDocument(); // default compare
    expect(screen.getByText("Provenance: CET1 amount")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Ratio history" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "History" })).toBeInTheDocument();
    expect(screen.getAllByText("66,000").length).toBeGreaterThan(0); // KPI card and history table
    expect(screen.queryByRole("table", { name: /Benchmark summary/ })).not.toBeInTheDocument();
    expect(h1()).toHaveTextContent("Benchmark");
  });

  it("Summary shows the former Benchmarks content: ranked chart and slot table", async () => {
    mockApi();
    renderApp("/summary");
    expect(await screen.findByText(/2 of 10 benchmark slots have data for 2026Q2/)).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "CET1-based leverage ratio by benchmark" })).toBeInTheDocument();
    expect(screen.getByRole("table", { name: "Benchmark slots for 2026Q2" })).toBeInTheDocument();
    expect(screen.getByText(/Rank 1 = highest ratio/)).toBeInTheDocument();
  });

  it("navigates between pages and updates the page title", async () => {
    mockApi();
    renderApp("/");
    await screen.findByText(/2 of 10 benchmarks have data/);
    await userEvent.click(within(screen.getByRole("navigation", { name: "Primary" })).getByRole("link", { name: /Source values/ }));
    await waitFor(() => expect(h1()).toHaveTextContent("Source values"));
    await userEvent.click(await screen.findByRole("tab", { name: /GNMA/ }));
    expect(await screen.findByText("Validated reference values (2023 Annual Report, Notes p. A-20)")).toBeInTheDocument();
  });

  it("only shows the period selector where a period applies", async () => {
    mockApi();
    const { unmount } = renderApp("/");
    expect(await screen.findByRole("combobox", { name: "Reporting period" })).toHaveValue("2026Q2");
    unmount();
    renderApp("/gnma");
    await screen.findByText("Total Maximum Exposure to Loss");
    expect(screen.queryByRole("combobox", { name: "Reporting period" })).not.toBeInTheDocument();
  });

  it("changing the period re-queries the peers for that period", async () => {
    const f = mockApi();
    renderApp("/");
    await screen.findByText(/2 of 10 benchmarks have data/);
    await userEvent.selectOptions(screen.getByRole("combobox", { name: "Reporting period" }), "2026Q1");
    await waitFor(() => expect(f.mock.calls.some(([u]) => String(u).includes("/peers?period=2026Q1"))).toBe(true));
  });
});

describe("GNMA source values (sub-tab)", () => {
  it("shows the validated reference totals exactly, with reporting dates", async () => {
    mockApi();
    renderApp("/gnma");
    const ref = await screen.findByRole("region", { name: "Reference value validation" });
    expect(within(ref).getByText("September 30, 2023")).toBeInTheDocument();
    expect(within(ref).getByText("$2,613,623,651")).toBeInTheDocument();
    expect(within(ref).getByText("September 30, 2022")).toBeInTheDocument();
    expect(within(ref).getByText("$2,442,351,095")).toBeInTheDocument();
    expect(within(ref).getAllByText("Matches reference")).toHaveLength(2);
  });

  it("headline KPI is the latest year with units, full dollars, YoY and a citation", async () => {
    mockApi();
    renderApp("/gnma");
    const kpi = await screen.findByRole("region", { name: "Total Maximum Exposure to Loss" });
    expect(within(kpi).getByText("$2,613,623,651")).toBeInTheDocument();
    expect(kpi).toHaveTextContent("FY2023 · as of September 30, 2023 · USD thousands as published");
    expect(kpi).toHaveTextContent("= $2,613,623,651,000");
    expect(within(kpi).getByTestId("kpi-delta")).toHaveTextContent("+$171,272,556,000(+7.01%)vs FY2022");
    const cite = within(kpi).getByTestId("gnma-citation");
    expect(cite).toHaveTextContent("annual_report23.pdf");
    expect(cite).toHaveTextContent("PDF p.96 (printed A-20)");
    expect(within(cite).getByRole("link")).toHaveAttribute("href", expect.stringMatching(/Annual_Reports\/annual_report23\.pdf$/));
  });

  it("separate component KPIs show MBS and commitments", async () => {
    mockApi();
    renderApp("/gnma");
    const mbs = await screen.findByRole("region", { name: "Outstanding MBS" });
    expect(mbs).toHaveTextContent("$2,472,843,019");
    const com = screen.getByRole("region", { name: "Outstanding MBS commitments" });
    expect(com).toHaveTextContent("$140,780,632");
    expect(within(com).getByTestId("kpi-delta")).toHaveTextContent("−$17,113,858,000(−10.84%)");
  });

  it("historical table is chronological, marks the latest year, and never invents a first-year change", async () => {
    mockApi();
    renderApp("/gnma");
    const table = await screen.findByRole("table", { name: "GNMA Maximum Exposure to Loss by fiscal year" });
    const body = within(table).getAllByRole("row").slice(1);
    expect(body.map((r) => within(r).getAllByRole("cell")[0].textContent)).toEqual([
      expect.stringContaining("FY2021"), expect.stringContaining("FY2022"), expect.stringContaining("FY2023")]);
    const cells = (i: number) => within(body[i]).getAllByRole("cell").map((c) => c.textContent);
    expect(cells(2)[0]).toContain("Latest");
    expect(cells(2)).toEqual(expect.arrayContaining(["September 30, 2023", "$2,472,843,019,000", "$140,780,632,000", "$2,613,623,651,000", "$2,613,623,651 (USD thousands)", "+$171,272,556,000", "+7.01%"]));
    expect(cells(1)).toEqual(expect.arrayContaining(["September 30, 2022", "$2,442,351,095,000", "$2,442,351,095 (USD thousands)"]));
    expect(cells(0)[0]).toContain("comparative");
    expect(cells(0)).toEqual(expect.arrayContaining(["—", "—"])); // no FY2020 → no YoY
    expect(within(body[2]).getByRole("link", { name: /annual_report23\.pdf/ })).toBeInTheDocument();
    expect(body[2]).toHaveTextContent("PDF p.96 (printed A-20)");
    expect(body[2]).toHaveTextContent("Note 2: Summary of Significant Accounting Policies");
  });

  it("filters the table and chart range by fiscal year", async () => {
    mockApi();
    renderApp("/gnma");
    const table = await screen.findByRole("table", { name: "GNMA Maximum Exposure to Loss by fiscal year" });
    await userEvent.selectOptions(screen.getByRole("combobox", { name: "From fiscal year" }), "2022");
    expect(within(table).getAllByRole("row")).toHaveLength(3);
    await userEvent.type(screen.getByRole("searchbox"), "2023");
    expect(within(table).getAllByRole("row")).toHaveLength(2);
  });

  it("toggles the chart view and exposes an accessible chart summary", async () => {
    mockApi();
    renderApp("/gnma");
    await screen.findByRole("heading", { name: "Historical exposure" });
    // FY2021 total = 2,125,591,309,000 + 301,023,584,000
    expect(screen.getByRole("img", { name: /Total Maximum Exposure to Loss rose from \$2,426\.6B in FY2021 to \$2,613\.6B in FY2023/ })).toBeInTheDocument();
    const total = screen.getByRole("button", { name: "Total" });
    await userEvent.click(total);
    expect(total).toHaveAttribute("aria-pressed", "true");
  });

  it("shows validation status and, once expanded, checks, reconciliation and documented gaps", async () => {
    mockApi();
    renderApp("/gnma");
    const panel = await screen.findByRole("region", { name: "Data validation and provenance" });
    expect(within(panel).getByText(/Validated · 1 reconciliation note/)).toBeInTheDocument();
    expect(within(panel).queryByText(/Years without a reliable figure/)).not.toBeInTheDocument();
    await userEvent.click(within(panel).getByRole("button", { name: /Validation, reconciliation and gaps/ }));
    expect(within(panel).getByText("FY2023 equals the reference total $2,613,623,651 (USD thousands)")).toBeInTheDocument();
    expect(within(panel).getByText("Years without a reliable figure")).toBeInTheDocument();
    expect(within(panel).getByText(/no 'Outstanding MBS' table found/)).toBeInTheDocument();
  });

  it("flags a failed validation and a reference mismatch instead of hiding it", async () => {
    const bad = { ...gnmaFixture, validation: [{ name: "Total = Outstanding MBS + commitments (every observation)", status: "fail" as const, detail: "x" }],
      series: gnmaFixture.series.map((f) => (f.fiscal_year === 2023 ? { ...f, total_usd: f.total_usd + 1000 } : f)) };
    mockApi({ "/gnma": bad });
    renderApp("/gnma");
    expect((await screen.findAllByText("1 validation check failed")).length).toBeGreaterThan(0);
    expect(screen.getByText("Does not match")).toBeInTheDocument();
  });

  it("says so when there is no GNMA data and offers the fetch action", async () => {
    mockApi({ "/gnma": { ...gnmaFixture, series: [], observations: [], validation: [] } });
    renderApp("/gnma");
    expect(await screen.findByText("No GNMA data yet")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Fetch GNMA reports/ })).toBeInTheDocument();
  });

  it("starts a refresh with POST and follows it to completion", async () => {
    let polls = 0;
    const f = mockApi({}, (path, init) => {
      if (path !== "/gnma/refresh") return undefined;
      if (init?.method === "POST") return { status: 202, body: { running: true, started: "t", finished: null, reports: 0, with_figures: 0, error: null } };
      polls += 1;
      return { body: { running: false, started: "t", finished: "t2", reports: 27, with_figures: 15, error: null } };
    });
    renderApp("/gnma");
    await userEvent.click(await screen.findByRole("button", { name: /Fetch GNMA reports/ }));
    expect(await screen.findByText(/15 of 27 annual reports yielded figures/)).toBeInTheDocument();
    expect(polls).toBeGreaterThan(0);
    expect(f.mock.calls.some(([, i]) => (i as RequestInit | undefined)?.method === "POST")).toBe(true);
  });
});

describe("states, shell and access", () => {
  it("shows a loading skeleton while data is pending", async () => {
    vi.stubGlobal("fetch", vi.fn(() => new Promise(() => {})));
    renderApp("/gnma");
    expect((await screen.findAllByTestId("loading-state")).length).toBeGreaterThan(0);
  });

  it("shows an error with retry when the API fails, then recovers", async () => {
    let fail = true;
    mockApi({}, (path) => (path === "/gnma" && fail ? { status: 500, body: { detail: "database is locked" } } : undefined));
    renderApp("/gnma");
    expect(await screen.findByRole("alert")).toHaveTextContent("database is locked");
    fail = false;
    await userEvent.click(screen.getByRole("button", { name: /Try again/ }));
    expect(await screen.findByText("Validated reference values (2023 Annual Report, Notes p. A-20)")).toBeInTheDocument();
  });

  it("reports an unreachable API plainly", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.reject(new TypeError("fetch failed"))));
    renderApp("/");
    expect(await screen.findByText(/Cannot reach the MCR API/)).toBeInTheDocument();
    expect(screen.getByTestId("freshness")).toHaveTextContent("Data unavailable");
  });

  it("empty database shows an empty state, not a crash", async () => {
    mockApi({ "/meta": { ...routes["/meta"] as object, periods: [], has_cet1: false }, "/peers": { periods: [], period: null, rows: [], stats: null } });
    renderApp("/");
    expect(await screen.findByText("No data yet")).toBeInTheDocument();
  });

  it("asks for the access token on 401 and sends it afterwards", async () => {
    const f = mockApi({}, (_path, init) => {
      const token = new Headers(init?.headers).get("X-MCR-Token");
      return token === "s3cret" ? undefined : { status: 401, body: { detail: "access token required" } };
    });
    renderApp("/gnma");
    await userEvent.type(await screen.findByLabelText("Access token"), "s3cret");
    await userEvent.click(screen.getByRole("button", { name: "Continue" }));
    expect(await screen.findByText("Validated reference values (2023 Annual Report, Notes p. A-20)")).toBeInTheDocument();
    expect(f.mock.calls.some(([, i]) => new Headers((i as RequestInit).headers).get("X-MCR-Token") === "s3cret")).toBe(true);
  });

  it("Refresh re-fetches the data", async () => {
    const f = mockApi();
    renderApp("/gnma");
    await screen.findByText("Validated reference values (2023 Annual Report, Notes p. A-20)");
    const before = f.mock.calls.filter(([u]) => String(u).endsWith("/gnma")).length;
    await userEvent.click(screen.getByRole("button", { name: "Refresh data" }));
    await waitFor(() => expect(f.mock.calls.filter(([u]) => String(u).endsWith("/gnma")).length).toBeGreaterThan(before));
  });

  it("sidebar collapses and expands", async () => {
    mockApi();
    renderApp("/");
    const side = await screen.findByTestId("sidebar");
    expect(side).toHaveAttribute("data-collapsed", "false");
    await userEvent.click(screen.getByRole("button", { name: "Collapse sidebar" }));
    expect(side).toHaveAttribute("data-collapsed", "true");
    expect(screen.getByRole("button", { name: "Expand sidebar" })).toHaveAttribute("aria-expanded", "false");
  });

  it("mobile drawer opens from the menu button and closes with Escape or after navigating", async () => {
    mockApi();
    renderApp("/");
    await userEvent.click(await screen.findByRole("button", { name: "Open navigation menu" }));
    const dialog = await screen.findByRole("dialog", { name: "Navigation menu" });
    await userEvent.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    await userEvent.click(screen.getByRole("button", { name: "Open navigation menu" }));
    await userEvent.click(within(await screen.findByRole("dialog")).getByRole("link", { name: "Benchmark" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(dialog).toBeDefined();
  });

  it("provides a skip link and the aurora backdrop is decorative", async () => {
    mockApi();
    renderApp("/");
    expect(await screen.findByRole("link", { name: "Skip to content" })).toHaveAttribute("href", "#main");
    expect(screen.getByTestId("aurora-background")).toHaveAttribute("aria-hidden", "true");
  });
});
