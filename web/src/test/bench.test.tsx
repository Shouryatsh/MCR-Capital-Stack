import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { benchFixture } from "./fixtures";
import { mockApi, renderApp } from "./helpers";

const table = (name: string) => screen.findByRole("table", { name });
const bodyRows = (t: HTMLElement) => within(t).getAllByRole("row").slice(1);

describe("Benchmark tab: GNMA-adjusted results in USD billions", () => {
  it("shows Benchmark 1 as a KPI in billions with full precision, change and formula", async () => {
    mockApi();
    renderApp("/benchmark");
    const kpi = await screen.findByRole("region", { name: "Benchmark 1 · Leverage based CET1 (GSEs)" });
    expect(within(kpi).getByText("$26.14B")).toBeInTheDocument();
    expect(kpi).toHaveTextContent("FY2023 · as of September 30, 2023 · USD (billions)");
    expect(kpi).toHaveTextContent("Full precision 26.13623651 USD billions"); // detail precision stays available
    expect(within(kpi).getByTestId("kpi-delta")).toHaveTextContent("+$1.71B(+7.01%)vs FY2022");
    expect(kpi).toHaveTextContent("gnma_total_exposure * adjustment_pct");
    expect(kpi).not.toHaveTextContent("$0.03B"); // 1,000x too small: the value if USD thousands were misread as dollars
  });

  it("lists all 10 benchmarks, in USD billions, and shows no number for the unconfirmed ones", async () => {
    mockApi();
    renderApp("/benchmark");
    const t = await table("Comparison of the ten GNMA-adjusted benchmarks in USD billions");
    const rows = bodyRows(t);
    expect(rows).toHaveLength(10);
    expect(within(t).getByRole("columnheader", { name: /Latest result \(USD billions\)/ })).toBeInTheDocument();
    expect(within(t).getByRole("columnheader", { name: /Prior year \(USD billions\)/ })).toBeInTheDocument();
    const first = within(rows[0]).getAllByRole("cell").map((c) => c.textContent);
    expect(first).toEqual(expect.arrayContaining(["1", "Leverage based CET1 (GSEs)", "$26.14B", "$24.42B", "+$1.71B", "+7.01%"]));
    for (const r of rows.slice(1)) {
      expect(within(r).getByText("Requires confirmation")).toBeInTheDocument();
      expect(r).not.toHaveTextContent(/\$[\d,.]+B/);
    }
    expect(t.textContent).not.toMatch(/\$\d{1,3}(,\d{3}){2,}/); // never raw dollars in the executive table
  });

  it("flags the unconfirmed benchmarks instead of inventing results and links to the calculations", async () => {
    mockApi();
    renderApp("/benchmark");
    const note = await screen.findByRole("note");
    expect(note).toHaveTextContent("1 of 10 benchmarks have a confirmed definition");
    expect(note).toHaveTextContent("Benchmarks 2, 3, 4, 5, 6, 7, 8, 9, 10 require business confirmation");
    expect(screen.getByRole("link", { name: /Inspect every calculation/ })).toHaveAttribute("href", "/calculations");
  });

  it("labels the chart axis and gives an accessible summary in billions", async () => {
    mockApi();
    renderApp("/benchmark");
    expect(await screen.findByRole("img", { name: /Benchmark 1 Leverage based CET1 \(GSEs\) rose from \$24\.27B in FY2021 to \$26\.14B in FY2023/ })).toBeInTheDocument();
    expect(screen.getByText(/Benchmark history/)).toBeInTheDocument();
  });

  it("keeps the entity (former Overview) content on the tab, labelled in $ millions", async () => {
    mockApi();
    renderApp("/benchmark");
    expect(await screen.findByRole("heading", { name: /Entity benchmark/ })).toHaveTextContent("$ millions");
    expect(await screen.findByLabelText("Entity")).toBeInTheDocument();
  });

  it("still shows the benchmark results when there is no entity data", async () => {
    mockApi({ "/entities": { providers: [], primary: null } });
    renderApp("/benchmark");
    expect((await screen.findAllByText("$26.14B")).length).toBeGreaterThan(0);
    expect(await screen.findByText("No data yet")).toBeInTheDocument();
  });

  it("shows an error for the benchmark section without breaking the rest of the page", async () => {
    mockApi({}, (path) => (path === "/benchmarks" ? { status: 500, body: { detail: "engine failed" } } : undefined));
    renderApp("/benchmark");
    expect(await screen.findByText("engine failed")).toBeInTheDocument();
    expect(await screen.findByLabelText("Entity")).toBeInTheDocument();
  });
});

describe("Benchmark Calculations tab", () => {
  it("is in the navigation and organised in sections A, B and C with the units note", async () => {
    mockApi();
    renderApp("/calculations");
    expect(await screen.findByRole("heading", { name: "A. Source data" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "B. Benchmark assumptions" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "C. Calculated benchmark results" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Benchmark Calculations");
    expect(screen.getByRole("note", { name: "Units" })).toHaveTextContent("USD (billions)");
    expect(screen.getByRole("note", { name: "Units" })).toHaveTextContent("4c43ee77e5f6");
  });

  it("source data separates official values from derived ones and keeps units and sources", async () => {
    mockApi();
    renderApp("/calculations");
    const t = await table("Benchmark source data");
    const rows = bodyRows(t);
    expect(rows).toHaveLength(6); // 2 inputs x 3 fiscal years
    const fy23 = rows.filter((r) => r.textContent?.includes("FY2023") && r.textContent.includes("Total Maximum Exposure"))[0];
    expect(fy23).toHaveTextContent("Derived");
    expect(fy23).toHaveTextContent("$2,613.62B");
    expect(fy23).toHaveTextContent("$2,613,623,651,000");
    expect(fy23).toHaveTextContent("USD thousands");
    expect(fy23).toHaveTextContent("PDF p.96 (printed A-20)");
    expect(within(rows.find((r) => r.textContent?.includes("Outstanding MBS"))!).getByText("Official source")).toBeInTheDocument();
  });

  it("assumptions table lists all 10 benchmarks with an editable field only for the confirmed one", async () => {
    mockApi();
    renderApp("/calculations");
    const t = await table("Benchmark assumptions and formulas");
    const rows = bodyRows(t);
    expect(rows).toHaveLength(10);
    expect(within(rows[0]).getByRole("textbox", { name: /Adjustment percentage/ })).toHaveValue("0.01");
    expect(within(rows[0]).getByText("Editable")).toBeInTheDocument();
    expect(rows[0]).toHaveTextContent("gnma_total_exposure * adjustment_pct");
    expect(rows[0]).toHaveTextContent("FY2021–FY2023 (Sept 30)");
    expect(rows[0]).toHaveTextContent("$26.14B");
    expect(within(rows[0]).getByText("Calculated")).toBeInTheDocument();
    for (const r of rows.slice(1)) {
      expect(within(r).queryByTestId("assumption-editor")).not.toBeInTheDocument();
      expect(within(r).getByText("Requires confirmation")).toBeInTheDocument();
    }
  });

  it("results hide unconfirmed benchmarks by default, in chronological order, and can include them", async () => {
    mockApi();
    renderApp("/calculations");
    const t = await table("Calculated benchmark results by fiscal year");
    expect(bodyRows(t).map((r) => within(r).getAllByRole("cell")[2].textContent)).toEqual(["FY2021", "FY2022", "FY2023Latest"]);
    expect(bodyRows(t)[2]).toHaveTextContent("$26.14B");
    await userEvent.click(screen.getByRole("checkbox", { name: /awaiting confirmation/ }));
    expect(bodyRows(t)).toHaveLength(30);
  });

  it("expands a result to show the exact formula, inputs with sources, assumptions and the unit reconciliation", async () => {
    mockApi();
    renderApp("/calculations");
    const t = await table("Calculated benchmark results by fiscal year");
    await userEvent.click(within(t).getByRole("button", { name: "Show details: Benchmark 1 FY2023" }));
    const d = await screen.findByTestId("calculation-detail");
    expect(within(d).getByTestId("calculation-line")).toHaveTextContent("2,613,623,651,000 × 0.01 = 26,136,236,510");
    expect(d).toHaveTextContent("gnma_total_exposure * adjustment_pct");
    expect(d).toHaveTextContent("GNMA Total Maximum Exposure to Loss");
    expect(d).toHaveTextContent("annual_report23.pdf · PDF p.96 (printed A-20)");
    expect(d).toHaveTextContent("26.13623651 USD billions");
    expect(d).toHaveTextContent("$26,136,236,510 USD");
    expect(d).toHaveTextContent("$26,136,236.51 (the unit GNMA prints)");
    expect(d).toHaveTextContent("adjustment_pct = 0.01");
    await userEvent.click(within(t).getByRole("button", { name: "Hide details: Benchmark 1 FY2023" }));
    expect(screen.queryByTestId("calculation-detail")).not.toBeInTheDocument();
  });

  it("explains why an unconfirmed benchmark has no result", async () => {
    mockApi();
    renderApp("/calculations");
    await userEvent.click(await screen.findByRole("checkbox", { name: /awaiting confirmation/ }));
    await userEvent.click(screen.getByRole("button", { name: "Show details: Benchmark 2 FY2023" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Requires business confirmation. Formula and assumptions have not been established.");
  });

  it("filters by benchmark and fiscal year across all three sections", async () => {
    mockApi();
    renderApp("/calculations");
    await table("Benchmark source data");
    await userEvent.selectOptions(screen.getByRole("combobox", { name: "Fiscal year" }), "2022");
    expect(bodyRows(await table("Benchmark source data"))).toHaveLength(2);
    expect(bodyRows(await table("Calculated benchmark results by fiscal year"))).toHaveLength(1);
    await userEvent.selectOptions(screen.getByRole("combobox", { name: "Benchmark" }), "3");
    expect(bodyRows(await table("Benchmark assumptions and formulas"))).toHaveLength(1);
  });

  it("editing the assumption saves, recalculates and announces it; the server is sent the typed value", async () => {
    const f = mockApi({}, (path, init) => (path === "/benchmarks/1/assumptions/adjustment_pct" && init?.method === "PUT" ? { body: benchFixture("0.02") } : undefined));
    renderApp("/calculations");
    const field = await screen.findByRole("textbox", { name: /Adjustment percentage/ });
    await userEvent.clear(field);
    await userEvent.type(field, "0.02");
    await userEvent.click(screen.getByRole("button", { name: "Save Adjustment percentage" }));
    const put = f.mock.calls.find(([, i]) => (i as RequestInit | undefined)?.method === "PUT")!;
    expect(JSON.parse((put[1] as RequestInit).body as string)).toEqual({ value: "0.02" });
    expect(await screen.findByText("Benchmark 1 Adjustment percentage saved; results recalculated.")).toBeInTheDocument();
    const t = await table("Calculated benchmark results by fiscal year");
    expect(bodyRows(t)[2]).toHaveTextContent("$52.27B");
    expect(screen.getByRole("note", { name: "Units" })).toHaveTextContent("a1b2c3d4e5f6"); // new assumptions version
    expect(screen.getByRole("button", { name: "Reset Adjustment percentage to 0.01" })).toBeInTheDocument();
  });

  it("shows the server's validation message for a rejected edit and changes nothing", async () => {
    mockApi({}, (path, init) => (init?.method === "PUT" && path.startsWith("/benchmarks/1/") ? { status: 422, body: { detail: "adjustment_pct: must be at most 1" } } : undefined));
    renderApp("/calculations");
    const field = await screen.findByRole("textbox", { name: /Adjustment percentage/ });
    await userEvent.clear(field);
    await userEvent.type(field, "7");
    await userEvent.click(screen.getByRole("button", { name: "Save Adjustment percentage" }));
    expect(await screen.findByText("adjustment_pct: must be at most 1")).toBeInTheDocument();
    expect(bodyRows(await table("Calculated benchmark results by fiscal year"))[2]).toHaveTextContent("$26.14B");
  });

  it("reset returns to the default and recalculates", async () => {
    let edited = true;
    mockApi({}, (path, init) => {
      if (path === "/benchmarks" ) return { body: benchFixture(edited ? "0.02" : "0.01") };
      if (init?.method === "DELETE") { edited = false; return { body: benchFixture("0.01") }; }
      return undefined;
    });
    renderApp("/calculations");
    await userEvent.click(await screen.findByRole("button", { name: "Reset Adjustment percentage to 0.01" }));
    expect(await screen.findByText("Benchmark 1 Adjustment percentage reset; results recalculated.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Reset Adjustment/ })).not.toBeInTheDocument();
    expect(bodyRows(await table("Calculated benchmark results by fiscal year"))[2]).toHaveTextContent("$26.14B");
  });

  it("validation is collapsed by default and lists warnings for unconfirmed benchmarks when opened", async () => {
    mockApi();
    renderApp("/calculations");
    const card = await screen.findByRole("region", { name: "Benchmark validation" });
    expect(within(card).queryByText(/require business confirmation/)).not.toBeInTheDocument();
    await userEvent.click(within(card).getByRole("button", { name: /Validation/ }));
    expect(within(card).getByText(/Benchmark\(s\) 2, 3, 4, 5, 6, 7, 8, 9, 10 require business confirmation/)).toBeInTheDocument();
    expect(within(card).getByText("Benchmark 1 uses the business-specified 1% adjustment")).toBeInTheDocument();
  });

  it("shows loading, error and empty states", async () => {
    vi.stubGlobal("fetch", vi.fn(() => new Promise(() => {})));
    const { unmount } = renderApp("/calculations");
    expect((await screen.findAllByTestId("loading-state")).length).toBeGreaterThan(0);
    unmount();
    vi.unstubAllGlobals();

    mockApi({}, (path) => (path === "/benchmarks" ? { status: 500, body: { detail: "engine failed" } } : undefined));
    const second = renderApp("/calculations");
    expect(await screen.findByRole("alert")).toHaveTextContent("engine failed");
    second.unmount();
    vi.unstubAllGlobals();

    mockApi({ "/benchmarks": { ...benchFixture(), periods: [], inputs: [], results: [] } });
    renderApp("/calculations");
    await waitFor(() => expect(screen.getByText("No GNMA inputs yet")).toBeInTheDocument());
  });
});
