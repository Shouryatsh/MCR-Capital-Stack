import { Calculator, Database, Landmark, LayoutDashboard, ListOrdered, Scale, type LucideIcon } from "lucide-react";

export interface NavItem {
  to: string;
  label: string;
  icon: LucideIcon;
  title: string;
  description: string;
  /** Pages driven by the reporting-period selector in the top bar. */
  usesPeriod?: boolean;
}

/**
 * Tab mapping (matches the Streamlit app after the reorganisation):
 *  Overview  = former Summary content · Benchmark = former Overview content · Summary = former Benchmarks content.
 */
export const NAV: NavItem[] = [
  { to: "/", label: "Overview", icon: LayoutDashboard, title: "Overview", usesPeriod: true,
    description: "Peer summary for the selected period: CET1-based leverage ratios, ranks and percentiles." },
  { to: "/benchmark", label: "Benchmark", icon: Scale, title: "Benchmark",
    description: "GNMA-adjusted benchmark results in USD billions, plus one entity in depth: CET1, adjusted total assets and ratio history." },
  { to: "/calculations", label: "Benchmark Calculations", icon: Calculator, title: "Benchmark Calculations",
    description: "Inputs, assumptions, formulas and the step-by-step calculation behind every benchmark result." },
  { to: "/summary", label: "Summary", icon: ListOrdered, title: "Summary", usesPeriod: true,
    description: "Ranked ratio chart and the ten benchmark slots for the selected period." },
  { to: "/source-values", label: "Source values", icon: Landmark, title: "Source values",
    description: "Figures exactly as published, one sub-tab per entity: Fannie Mae, GNMA, Freddie Mac, FHLBs, FDIC." },
  { to: "/sources", label: "Data sources", icon: Database, title: "Data sources",
    description: "Every source file, fetch log and ingest log behind the stored values." },
];

export const streamlitUrl = () => `${window.location.protocol}//${window.location.hostname}:8503`;
