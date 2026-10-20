import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { fannieSource } from "./fixtures";
import { mockApi, renderApp } from "./helpers";

const rowsOf = (t: HTMLElement) => within(t).getAllByRole("row").slice(1);
const tabs = () => within(screen.getByRole("tablist", { name: "Entities" })).getAllByRole("tab");

describe("Source values tab", () => {
  it("replaces GNMA analytics in the navigation and is titled Source values", async () => {
    mockApi();
    renderApp("/source-values");
    const nav = await screen.findByRole("navigation", { name: "Primary" });
    expect(within(nav).getByRole("link", { name: /Source values/ })).toHaveAttribute("href", "/source-values");
    expect(within(nav).queryByRole("link", { name: /GNMA analytics/ })).not.toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Source values");
  });

  it("has one sub-tab per entity in the requested order, Fannie Mae selected first", async () => {
    mockApi();
    renderApp("/source-values");
    await screen.findByRole("tablist", { name: "Entities" });
    expect(tabs().map((t) => t.textContent?.replace(/\(.*\)/, "").trim())).toEqual(["Fannie Mae", "GNMA", "Freddie Mac", "FHLBs", "FDIC"]);
    expect(tabs()[0]).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tabpanel")).toHaveAccessibleName(/^Fannie Mae/);
  });

  it("Fannie Mae shows the minimum capital ratio, total RWA and credit RWA, matching the verification values", async () => {
    mockApi();
    renderApp("/source-values");
    const ratio = await screen.findByRole("region", { name: "Minimum capital ratio (CET1)" });
    expect(ratio).toHaveTextContent("4.5%");
    expect(ratio).toHaveTextContent("December 2023 · percent as published");
    const total = screen.getByRole("region", { name: "Total risk-weighted assets" });
    expect(total).toHaveTextContent("1,357,097");
    expect(total).toHaveTextContent("USD millions as published");
    expect(total).toHaveTextContent("fannie_2023Q4.pdf, p.10 · Exhibit 2.1 · RWA Summary");
    expect(screen.getByRole("region", { name: "Credit risk-weighted assets" })).toHaveTextContent("1,240,896");
    const ver = screen.getByRole("region", { name: "Verification against supplied values" });
    expect(ver).toHaveTextContent("Verification · December 2023");
    expect(within(ver).getByText("Matches supplied values")).toBeInTheDocument();
    expect(within(ver).getByText("supplied 4.5% · equal")).toBeInTheDocument();
    expect(within(ver).getByText("supplied 1,357,097 · equal")).toBeInTheDocument();
    expect(within(ver).getByText("supplied 1,240,896 · equal")).toBeInTheDocument();
  });

  it("flags a mismatch with the supplied values instead of hiding it", async () => {
    mockApi({ "/source-values/fannie-mae": { ...fannieSource, reference: { ...fannieSource.reference!, matches: false, found: { ...fannieSource.reference!.found, total_rwa: "1357098" } } } });
    renderApp("/source-values");
    expect(await screen.findByText("Does not match")).toBeInTheDocument();
    expect(screen.getByText("supplied 1,357,097 · different")).toBeInTheDocument();
  });

  it("lists every period chronologically with units in the headers, latest marked, and provenance on expand", async () => {
    mockApi();
    renderApp("/source-values");
    const t = await screen.findByRole("table", { name: "Fannie Mae source values by period" });
    const head = within(t).getAllByRole("columnheader").map((h) => h.textContent);
    expect(head).toEqual(expect.arrayContaining([expect.stringContaining("Minimum capital ratio (CET1) (%)"), expect.stringContaining("Total risk-weighted assets ($ millions)"), expect.stringContaining("Credit risk-weighted assets ($ millions)")]));
    const rows = rowsOf(t);
    expect(rows).toHaveLength(2);
    expect(rows[0]).toHaveTextContent("September 2023");
    expect(rows[1]).toHaveTextContent("December 2023");
    expect(rows[1]).toHaveTextContent("Latest");
    expect(rows[1]).toHaveTextContent("1,357,097");
    expect(rows[1]).toHaveTextContent("4.5%");
    await userEvent.click(within(rows[1]).getByRole("button", { name: /Show details: December 2023/ }));
    const prov = await screen.findByTestId("provenance");
    expect(prov).toHaveTextContent("Total risk-weighted assets: 1,357,097 (printed 1,357,097, USD millions)");
    expect(prov).toHaveTextContent("fannie_2023Q4.pdf · p.10 · Exhibit 2.1 · RWA Summary");
    expect(prov).toHaveTextContent("[Minimum Capital Ratio Requirement]");
  });

  it("charts the RWA series in USD millions with an accessible summary", async () => {
    mockApi();
    renderApp("/source-values");
    expect(await screen.findByRole("img", { name: /total risk-weighted assets were 1,357,097 and credit risk-weighted assets 1,240,896 \(\$ millions\) in December 2023/ })).toBeInTheDocument();
  });

  it("Freddie Mac has its own sub-tab with its own values, and no verification claim it cannot make", async () => {
    mockApi();
    renderApp("/source-values");
    await userEvent.click(await screen.findByRole("tab", { name: /Freddie Mac/ }));
    expect(await screen.findByRole("region", { name: "Total risk-weighted assets" })).toHaveTextContent("1,008,893");
    expect(screen.getByRole("region", { name: "Credit risk-weighted assets" })).toHaveTextContent("884,404");
    expect(screen.getByRole("region", { name: "Minimum capital ratio (CET1)" })).toHaveTextContent("4.5%");
    expect(screen.queryByRole("region", { name: "Verification against supplied values" })).not.toBeInTheDocument();
    expect(screen.queryByText("1,357,097")).not.toBeInTheDocument(); // nothing from the Fannie Mae tab leaks across
    const checks = screen.getByRole("region", { name: "Freddie Mac validation" });
    await userEvent.click(within(checks).getByRole("button", { name: /Validation/ }));
    expect(within(checks).getByText("Independent verification values")).toBeInTheDocument();
  });

  it("the GNMA sub-tab keeps the previous GNMA analytics content", async () => {
    mockApi();
    renderApp("/source-values");
    await userEvent.click(await screen.findByRole("tab", { name: /GNMA/ }));
    expect(await screen.findByText("Validated reference values (2023 Annual Report, Notes p. A-20)")).toBeInTheDocument();
    expect(screen.getByRole("table", { name: "GNMA Maximum Exposure to Loss by fiscal year" })).toBeInTheDocument();
  });

  it("FHLBs and FDIC are honest empty tabs, not invented data", async () => {
    mockApi();
    renderApp("/source-values");
    await userEvent.click(await screen.findByRole("tab", { name: /FHLBs/ }));
    expect(await screen.findByText("No FHLBs source values yet")).toBeInTheDocument();
    expect(screen.getByText(/no values are estimated/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("tab", { name: /FDIC/ }));
    expect(await screen.findByText("No FDIC source values yet")).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });

  it("is keyboard accessible: arrow keys move between tabs and the selection is in the URL-driven panel", async () => {
    mockApi();
    renderApp("/source-values");
    const first = (await screen.findAllByRole("tab"))[0];
    first.focus();
    await userEvent.keyboard("{ArrowRight}");
    expect(tabs()[1]).toHaveAttribute("aria-selected", "true");
    expect(tabs()[1]).toHaveFocus();
    expect(tabs()[0]).toHaveAttribute("tabindex", "-1");
    await userEvent.keyboard("{End}");
    expect(tabs()[4]).toHaveAttribute("aria-selected", "true");
    await userEvent.keyboard("{ArrowRight}");
    expect(tabs()[0]).toHaveAttribute("aria-selected", "true"); // wraps
  });

  it("deep links select the entity, and the old /gnma address redirects to the GNMA sub-tab", async () => {
    mockApi();
    const first = renderApp("/source-values?entity=freddie-mac");
    expect(await screen.findByRole("region", { name: "Total risk-weighted assets" })).toHaveTextContent("1,008,893");
    first.unmount();
    renderApp("/gnma");
    expect(await screen.findByText("Validated reference values (2023 Annual Report, Notes p. A-20)")).toBeInTheDocument();
    expect(tabs()[1]).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Source values");
  });

  it("shows loading, error and empty-period states", async () => {
    vi.stubGlobal("fetch", vi.fn(() => new Promise(() => {})));
    const a = renderApp("/source-values");
    expect((await screen.findAllByTestId("loading-state")).length).toBeGreaterThan(0);
    a.unmount();
    vi.unstubAllGlobals();

    mockApi({}, (path) => (path === "/source-values/fannie-mae" ? { status: 500, body: { detail: "capital table missing" } } : undefined));
    const b = renderApp("/source-values");
    expect(await screen.findByRole("alert")).toHaveTextContent("capital table missing");
    b.unmount();
    vi.unstubAllGlobals();

    mockApi({ "/source-values/fannie-mae": { ...fannieSource, periods: [], reference: null } });
    renderApp("/source-values");
    await waitFor(() => expect(screen.getByText("No Fannie Mae source values yet")).toBeInTheDocument());
  });
});
