import { Loader2, RefreshCw } from "lucide-react";
import { ActionButton } from "../components/Buttons";
import { DataTable, type Column } from "../components/DataTable";
import { GlassCard } from "../components/GlassCard";
import { ErrorState, LoadingState } from "../components/States";
import { useGnmaRefresh } from "../lib/gnmaRefresh";
import { useApi } from "../lib/hooks";
import { fmtMm } from "../lib/format";
import type { SourcesResponse } from "../lib/types";

type Row = Record<string, string | number | null>;

const cols = (spec: [string, string, boolean?][]): Column<Row>[] =>
  spec.map(([key, header, numeric]) => ({ key, header, numeric, className: numeric ? undefined : "whitespace-normal break-words" }));

export function DataSourcesPage() {
  const { data, error, loading, reload } = useApi<SourcesResponse>("/sources");
  const refresh = useGnmaRefresh();
  if (loading && !data) return <LoadingState label="Loading data sources" cards={0} />;
  if (error) return <ErrorState error={error} onRetry={reload} />;
  if (!data) return null;

  return (
    <div className="space-y-6">
      <GlassCard className="flex flex-wrap items-center justify-between gap-3 p-4">
        <p className="text-sm text-muted">
          GNMA annual reports are downloaded from ginniemae.gov and re-extracted. GSE disclosures (Fannie Mae, Freddie Mac) are fetched from the Streamlit app’s Data Sources page or <code>scripts/fetch.py</code>.
        </p>
        <ActionButton onClick={refresh.start} disabled={refresh.running}>
          {refresh.running ? <Loader2 className="size-4 animate-spin" aria-hidden="true" /> : <RefreshCw className="size-4" aria-hidden="true" />}
          {refresh.running ? "Fetching reports…" : "Fetch GNMA annual reports"}
        </ActionButton>
      </GlassCard>
      {refresh.error && <ErrorState error={new Error(refresh.error)} />}

      <section className="space-y-2" aria-label="Source files">
        <h2 className="text-base font-semibold">Source files behind every stored value</h2>
        <DataTable<Row> caption="Stored observations and their source files" rows={data.observations} rowKey={(_, i) => String(i)} filterable maxHeight="26rem"
          columns={[...cols([["provider", "Provider"], ["period", "Period"], ["field", "Field"], ["source_file", "Source file"], ["table_name", "Table"], ["field_label", "Line item"], ["column_name", "Column"], ["location", "Location"], ["raw_value", "As printed"], ["units_detected", "Units"]]),
            { key: "value_mm", header: "Value ($ millions)", numeric: true, render: (r) => fmtMm(r.value_mm as number) },
            ...cols([["ingested_at", "Ingested"]])]} />
      </section>
      <section className="space-y-2" aria-label="Fetch log">
        <h2 className="text-base font-semibold">Fetch log</h2>
        <DataTable<Row> caption="Fetch log" rows={data.fetch_log} rowKey={(_, i) => String(i)} filterable maxHeight="18rem" columns={cols([["ts", "Time"], ["url", "URL"], ["status", "Status"], ["detail", "Detail"]])} />
      </section>
      <section className="space-y-2" aria-label="Ingest log">
        <h2 className="text-base font-semibold">Ingest log</h2>
        <DataTable<Row> caption="Ingest log" rows={data.ingest_log} rowKey={(_, i) => String(i)} filterable maxHeight="18rem" columns={cols([["ts", "Time"], ["file", "File"], ["provider", "Provider"], ["period", "Period"], ["status", "Status"], ["detail", "Detail"]])} />
      </section>
    </div>
  );
}
