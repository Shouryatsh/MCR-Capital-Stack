import { ExternalLink, FileText } from "lucide-react";
import type { GnmaFigure, Provenance } from "../lib/types";

/** Where a GNMA number came from: report, page, financial statement note. */
export function GnmaCitation({ f }: { f: GnmaFigure }) {
  return (
    <p className="text-xs text-subtle" data-testid="gnma-citation">
      <FileText className="mr-1 inline size-3.5 align-text-bottom" aria-hidden="true" />
      <a href={f.source_url} target="_blank" rel="noreferrer" className="text-aurora-cyan underline-offset-2 hover:underline">
        {f.source_report}
        <ExternalLink className="ml-0.5 inline size-3" aria-hidden="true" />
        <span className="sr-only"> (opens the official Ginnie Mae PDF)</span>
      </a>
      {" · "}PDF p.{f.pdf_page}
      {f.printed_page && <> (printed {f.printed_page})</>}
      {f.note && <> · {f.note}</>}
    </p>
  );
}

/** Provenance of one CET1 / adjusted-assets value, in the same wording as the Streamlit app. */
export function SourceCitation({ o, label }: { o: Provenance | null | undefined; label?: string }) {
  if (!o) return <span className="text-xs text-subtle">no source</span>;
  const col = o.column_name ? ` [${o.column_name}]` : "";
  return (
    <span className="text-xs text-subtle" title={`${label ?? o.field_label}: printed ${o.raw_value} (${o.units_detected})`}>
      {o.source_file}, {o.location} · {o.table_name} · {o.field_label}
      {col}
    </span>
  );
}
