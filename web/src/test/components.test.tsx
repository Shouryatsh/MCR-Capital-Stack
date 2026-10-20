import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { DataTable, type Column } from "../components/DataTable";
import { KpiCard } from "../components/KpiCard";

interface R { name: string; amount: number | null }
const rows: R[] = [{ name: "Beta", amount: 20 }, { name: "Alpha", amount: 3 }, { name: "Gamma", amount: null }];
const cols: Column<R>[] = [
  { key: "name", header: "Name" },
  { key: "amount", header: "Amount", numeric: true, render: (r) => (r.amount == null ? "—" : `$${r.amount}`) },
];
const names = () => screen.getAllByRole("row").slice(1).map((r) => within(r).getAllByRole("cell")[0].textContent);

describe("DataTable", () => {
  it("sorts numerically, flips direction, then clears, with blanks always last", async () => {
    render(<DataTable columns={cols} rows={rows} rowKey={(r) => r.name} caption="t" />);
    expect(names()).toEqual(["Beta", "Alpha", "Gamma"]);
    const header = screen.getByRole("columnheader", { name: /amount/i });
    await userEvent.click(within(header).getByRole("button"));
    expect(names()).toEqual(["Alpha", "Beta", "Gamma"]);
    expect(header).toHaveAttribute("aria-sort", "ascending");
    await userEvent.click(within(header).getByRole("button"));
    expect(names()).toEqual(["Beta", "Alpha", "Gamma"]);
    expect(header).toHaveAttribute("aria-sort", "descending");
    await userEvent.click(within(header).getByRole("button"));
    expect(header).toHaveAttribute("aria-sort", "none");
  });

  it("filters rows, reports the count and shows an empty state", async () => {
    render(<DataTable columns={cols} rows={rows} rowKey={(r) => r.name} caption="t" filterable />);
    await userEvent.type(screen.getByRole("searchbox"), "alp");
    expect(names()).toEqual(["Alpha"]);
    expect(screen.getByText("1 of 3 rows")).toBeInTheDocument();
    await userEvent.clear(screen.getByRole("searchbox"));
    await userEvent.type(screen.getByRole("searchbox"), "zzz");
    expect(screen.getByText("No rows to show.")).toBeInTheDocument();
  });

  it("right-aligns numeric columns and exposes an accessible caption and scroll region", () => {
    render(<DataTable columns={cols} rows={rows} rowKey={(r) => r.name} caption="Totals" />);
    expect(screen.getByRole("table", { name: "Totals" })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: /Totals \(scrollable\)/ })).toHaveAttribute("tabindex", "0");
    expect(within(screen.getAllByRole("row")[1]).getAllByRole("cell")[1]).toHaveClass("text-right", "tnum");
  });
});

describe("KpiCard", () => {
  it("shows value, delta with its comparison period and a labelled sparkline", () => {
    render(<KpiCard title="Total" value="$2,613,623,651" delta={{ abs: "+$171,272,556,000", pct: "+7.01%", direction: "up", label: "vs FY2022", tone: "neutral" }} spark={[1, 2, 3]} sparkLabel="History" />);
    expect(screen.getByText("$2,613,623,651")).toBeInTheDocument();
    expect(screen.getByTestId("kpi-delta")).toHaveTextContent("+$171,272,556,000(+7.01%)vs FY2022");
    expect(screen.getByRole("img", { name: "History" })).toBeInTheDocument();
  });

  it("never draws a sparkline or delta from fewer than two real points / no comparison", () => {
    render(<KpiCard title="Solo" value="1" spark={[5]} delta={null} />);
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
    expect(screen.queryByTestId("kpi-delta")).not.toBeInTheDocument();
  });

  it("colours auto deltas by direction but keeps neutral ones neutral", () => {
    const { rerender } = render(<KpiCard title="R" value="1" delta={{ abs: "-0.1 pp", direction: "down", label: "vs x", tone: "auto" }} />);
    expect(screen.getByText("-0.1 pp").closest("span")).toHaveClass("text-neg");
    rerender(<KpiCard title="R" value="1" delta={{ abs: "-0.1 pp", direction: "down", label: "vs x", tone: "neutral" }} />);
    expect(screen.getByText("-0.1 pp").closest("span")).toHaveClass("text-neutral");
  });
});
