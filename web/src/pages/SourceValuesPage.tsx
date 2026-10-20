import { useId } from "react";
import { useSearchParams } from "react-router-dom";
import { EntityTabs } from "../components/EntityTabs";
import { EmptyState, ErrorState, LoadingState } from "../components/States";
import { useApi } from "../lib/hooks";
import type { SourceEntity } from "../lib/types";
import { GnmaPage } from "./GnmaPage";
import { GsePanel } from "./GsePanel";
import { FhlbPage } from "./FhlbPage";
import { GfeePage } from "./GfeePage";
import { FdicPage } from "./FdicPage";

/** Source values: as-published figures, one sub-tab per entity (Fannie Mae, GNMA, Freddie Mac, FHLBs, FDIC, ...). */
export function SourceValuesPage() {
  const { data, error, loading, reload } = useApi<{ entities: SourceEntity[] }>("/source-values");
  const [params, setParams] = useSearchParams();
  const panelId = useId();
  if (loading && !data) return <LoadingState label="Loading source values" cards={0} />;
  if (error) return <ErrorState error={error} onRetry={reload} />;
  const entities = data?.entities ?? [];
  if (!entities.length) return <EmptyState title="No entities configured">Add entities to config/source_entities.json.</EmptyState>;
  const active = entities.find((e) => e.key === params.get("entity")) ?? entities[0];

  return (
    <div className="space-y-5">
      <EntityTabs entities={entities} active={active.key} panelId={panelId} onSelect={(key) => setParams({ entity: key }, { replace: true })} />
      <div role="tabpanel" id={panelId} aria-labelledby={`tab-${active.key}`} tabIndex={-1} className="space-y-5">
        <h2 className="text-lg font-semibold">{active.name} <span className="font-normal text-muted">· source values</span></h2>
        {active.kind === "gnma" ? <GnmaPage /> : active.kind === "gse" ? <GsePanel key={active.key} entityKey={active.key} /> : active.kind === "fhlb" ? <FhlbPage /> : active.kind === "gfee" ? <GfeePage /> : active.kind === "fdic" ? <FdicPage /> : (
          <EmptyState title={`No ${active.name} source values yet`}>
            {active.note ? `${active.note}. ` : ""}Nothing has been loaded for this entity, and no values are estimated. Once a source is ingested it will appear here.
          </EmptyState>
        )}
      </div>
    </div>
  );
}
