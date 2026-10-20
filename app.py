"""MCR Dashboard (Streamlit). Run with: python scripts/serve.py   (or: streamlit run app.py)

Pages: Overview · Benchmarks · Summary · Data Sources · Uploads · Settings. CET1 amounts are $ millions; GNMA exposure is USD.
Overview = peer summary table · Benchmarks = entity KPIs and ratio history · Summary = period bar chart, slot table, GNMA exposure.
"""
import hmac
import json
import os
import tempfile
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from mcr import config, fannie, freddie, gnma, store
from mcr.ingest import ingest_upload
from mcr.mappings import load_mappings, save_mappings
from mcr.models import CANONICAL_FIELDS, FIELD_LABELS, MCRError
from mcr.ratio import benchmark_table, fmt_mm, fmt_ratio
from mcr.tabular import extract_field, load_grid

config.setup_logging()
st.set_page_config(page_title=config.APP_NAME, page_icon="📊", layout="wide")
UNITS = "$ millions"
ACCENT, ACCENT2 = "#2a6fdb", "#e0792b"

# ---- token gate (placeholder): set MCR_TOKEN to require a token; unset = open (local use)
_token = os.environ.get("MCR_TOKEN")
if _token:
    given = st.sidebar.text_input("Access token", type="password")
    if not given or not hmac.compare_digest(given, _token):
        st.title(config.APP_NAME)
        st.info("Enter the access token in the sidebar.")
        st.stop()

settings = config.load_settings()
dec = int(settings["ratio_decimals"])


# ---------------------------------------------------------------- helpers
def src_line(o: dict | None) -> str:
    if not o:
        return "no source"
    col = f" [{o['column_name']}]" if o.get("column_name") else ""
    return f"{o['source_file']}, {o['location']} · {o['table_name']} · {o['field_label']}{col}"


def prov_block(o: dict | None, title: str):
    """Expandable provenance record for one value."""
    if not o:
        return
    with st.expander(f"Provenance: {title}"):
        rec = {"source_file": o["source_file"], "sheet_or_table_name": o["table_name"], "row_identifier": o["row_identifier"],
               "field_label": o["field_label"], "raw_value": o["raw_value"], "parsed_value": f"{o['parsed_value']:,}",
               "units_detected": f"{o['units_detected']} ({o['units_source']})", "value ($ millions)": f"{o['value_mm']:,.0f}",
               "location": o["location"]}
        st.table(pd.DataFrame({"value": rec}))
        if o.get("source_url"):
            st.markdown(f"Source URL: [{o['source_url']}]({o['source_url']})")


def kpi(col, label, value, o):
    with col, st.container(border=True):
        st.caption(f"{label} ({UNITS})" if label != "Ratio" else "CET1-based leverage ratio")
        st.markdown(f"## {value}")
        st.caption(src_line(o) if o else "")


def providers_with_data() -> list[str]:
    return [r["provider"] for r in store.rows("SELECT DISTINCT provider FROM observations ORDER BY provider")]


def render_gnma_section():
    """GNMA Maximum Exposure to Loss (USD) from Ginnie Mae's English annual reports (extraction + checks: mcr/gnma.py)."""
    st.divider()
    st.header("GNMA · Maximum Exposure to Loss")
    figs = gnma.load_figures()
    series = gnma.headline_series(figs)
    if not series:
        st.info("No GNMA data yet. Use **Data Sources → Fetch GNMA annual reports**, or run `python scripts/fetch.py --ginnie`.")
        return
    latest = series[-1]
    checks = gnma.validate(figs)
    st.caption("Total Maximum Exposure to Loss = Outstanding MBS + Outstanding MBS commitments (Notes to the Financial Statements of the "
               "English annual reports). US dollars: each report prints thousands (FY2017 on) or billions (FY2012–FY2016); values are shown "
               "as published and in full dollars, with no rounding.")
    if any(c["status"] == "fail" for c in checks):
        st.error("⚠ GNMA validation failed: " + "; ".join(c["name"] for c in checks if c["status"] == "fail"))
    st.subheader(f"GNMA · FY{latest.fiscal_year} · {latest.reporting_date} (latest)")
    for col, label, usd in zip(st.columns(3), ("Total Maximum Exposure to Loss", "Outstanding MBS", "Outstanding MBS commitments"),
                               (latest.total_usd, latest.mbs_usd, latest.commitments_usd)):
        with col, st.container(border=True):
            st.caption(f"{label} (USD {latest.units})")
            st.markdown(f"## {latest.published(usd)}")
            st.caption(f"{gnma.fmt_usd(usd)} · {latest.source_report}, pdf p.{latest.pdf_page}")

    x = [f"FY{f.fiscal_year}" for f in series]
    cd = [[f.reporting_date, gnma.fmt_usd(f.mbs_usd), gnma.fmt_usd(f.commitments_usd), gnma.fmt_usd(f.total_usd),
           f"{f.published(f.total_usd)} (USD {f.units})", f.source_report, f.pdf_page] for f in series]
    hover = ("<b>%{x}</b> (as of %{customdata[0]})<br>Outstanding MBS %{customdata[1]}<br>Outstanding MBS commitments %{customdata[2]}"
             "<br><b>Total %{customdata[3]}</b><br>As published %{customdata[4]}<br><i>Source: %{customdata[5]}, pdf p.%{customdata[6]}</i><extra></extra>")
    fig = go.Figure()
    for name, attr, color in (("Outstanding MBS", "mbs_usd", ACCENT), ("Outstanding MBS commitments", "commitments_usd", ACCENT2)):
        fig.add_trace(go.Bar(x=x, y=[getattr(f, attr) / 1e9 for f in series], name=name, marker_color=color, customdata=cd, hovertemplate=hover))
    fig.add_annotation(x=x[-1], y=latest.total_usd / 1e9, text=f"Latest · {latest.reporting_date}", showarrow=True, arrowhead=2, ay=-30)
    fig.update_layout(barmode="stack", height=380, margin=dict(l=10, r=10, t=30, b=10), xaxis=dict(type="category"),
                      yaxis=dict(title="USD billions"), legend=dict(orientation="h", y=1.12))
    st.plotly_chart(fig, width="stretch")

    def row(f):
        warns = [fl.removeprefix("WARN: ") for fl in f.flags if fl.startswith("WARN")]
        return {"Fiscal year": f"FY{f.fiscal_year}", "Reporting date": f.reporting_date,
                "Outstanding MBS (USD)": gnma.fmt_usd(f.mbs_usd), "Outstanding MBS commitments (USD)": gnma.fmt_usd(f.commitments_usd),
                "Total Maximum Exposure to Loss (USD)": gnma.fmt_usd(f.total_usd),
                "Total as published": f.as_published_total(), "Total basis": "printed in report" if f.reported_total_usd is not None else "computed",
                "Latest": "◀ latest" if f is latest else ("comparative only" if f.role == "comparative" else ""),
                "Source report": f.source_url, "Page": f"pdf p.{f.pdf_page}" + (f" · printed {f.printed_page}" if f.printed_page else ""),
                "Note": f.note, "Checks": "⚠ " + "; ".join(warns) if warns else "✓ pass"}

    df = pd.DataFrame([row(f) for f in series])
    st.dataframe(df, hide_index=True, width="stretch", column_config={
        "Source report": st.column_config.LinkColumn("Source report", display_text=r"https://.*/(annual_report\d+\.pdf)")})
    exact = pd.DataFrame([{"fiscal_year": f.fiscal_year, "reporting_date": f.reporting_date, "outstanding_mbs_usd": str(f.mbs_usd),
                           "outstanding_mbs_commitments_usd": str(f.commitments_usd), "total_max_exposure_to_loss_usd": str(f.total_usd),
                           "published_units": f.units, "source_report": f.source_report, "source_url": f.source_url, "pdf_page": f.pdf_page,
                           "printed_page": f.printed_page, "note": f.note} for f in series])
    st.download_button("Download GNMA exposure CSV", exact.to_csv(index=False).encode("utf8"), file_name="gnma_max_exposure_to_loss.csv", mime="text/csv")

    with st.expander("GNMA validation, reconciliation, gaps and every observation"):
        icon = {"pass": "✓ pass", "warn": "⚠ warn", "fail": "✗ fail"}
        st.dataframe(pd.DataFrame([{"Status": icon[c["status"]], "Check": c["name"], "Detail": c["detail"]} for c in checks]),
                     hide_index=True, width="stretch")
        st.markdown("**Comparatives reconciled across reports** (a year's own report vs. the prior-year column of later reports)")
        rec = gnma.reconcile(figs)
        st.dataframe(pd.DataFrame([{"Fiscal year": f"FY{r['fiscal_year']}", "Component": r["component"], "Report A": r["report_a"],
                                    "A (USD)": gnma.fmt_usd(r["usd_a"]), "Report B": r["report_b"], "B (USD)": gnma.fmt_usd(r["usd_b"]),
                                    "A − B (USD)": f"{r['difference_usd']:,}", "Status": r["status"]} for r in rec]),
                     hide_index=True, width="stretch")
        gaps = gnma.load_gaps()
        if gaps:
            st.markdown("**Years without a reliable figure** (flagged, never estimated)")
            st.dataframe(pd.DataFrame([{"Fiscal year": f"FY{g['fiscal_year']}", "Report": g["source_report"], "Reason": g["reason"]} for g in gaps]),
                         hide_index=True, width="stretch")
        st.markdown("**All observations** (own-report and comparative columns) with provenance")
        st.dataframe(pd.DataFrame([{"Fiscal year": f"FY{f.fiscal_year}", "Role": f.role, "Reporting date": f.reporting_date,
                                    "Source report": f.source_report, "pdf page": f.pdf_page, "Printed page": f.printed_page, "Note": f.note,
                                    "Table": f.table_title, "Units": f.units, "Outstanding MBS (as printed)": f.mbs_raw,
                                    "Commitments (as printed)": f.commitments_raw, "Total (as printed)": f.total_raw,
                                    "Total (USD)": gnma.fmt_usd(f.total_usd), "Flags": " | ".join(f.flags)} for f in figs]),
                     hide_index=True, width="stretch")


# ---------------------------------------------------------------- sidebar
st.sidebar.title(f"📊 {config.APP_NAME}")
page = st.sidebar.radio("Navigate", ["Overview", "Benchmarks", "Summary", "Data Sources", "Uploads", "Settings"],
                        label_visibility="collapsed")
st.sidebar.caption(f"CET1 and assets are in **{UNITS}**; GNMA exposure is in US dollars.\n\nRatio = CET1 amount ÷ Adjusted total assets.")

st.title(config.APP_NAME)

# ================================================================ Benchmarks (content formerly on Overview)
if page == "Benchmarks":
    provs = providers_with_data()
    if not provs:
        st.warning("No data yet. Go to **Uploads** or **Data Sources** to ingest a disclosure.")
        st.stop()
    primary = settings["primary_provider"] if settings["primary_provider"] in provs else provs[0]
    prov = st.selectbox("Entity", provs, index=provs.index(primary))
    ser = [r for r in store.series(prov) if r["ratio"] is not None]
    if not ser:
        st.warning(f"{prov} has no complete period (both CET1 and adjusted total assets).")
        st.stop()
    last = ser[-1]
    bad = [r for r in ser if r["failed"]]
    if bad:
        st.error("⚠ Validation failed for: " + "; ".join(f"{r['period']} ({', '.join(k['name'] for k in r['failed'])})" for r in bad))
    st.subheader(f"{prov} · {last['period']}")
    c1, c2, c3 = st.columns(3)
    kpi(c1, "CET1 amount", fmt_mm(last["cet1"]["value_mm"]), last["cet1"])
    kpi(c2, "Adjusted total assets", fmt_mm(last["ata"]["value_mm"]), last["ata"])
    kpi(c3, "Ratio", fmt_ratio(last["ratio"], dec), None)
    prov_block(last["cet1"], "CET1 amount")
    prov_block(last["ata"], "Adjusted total assets")

    st.subheader("Ratio history")
    chosen = st.multiselect("Compare with", [p for p in provs if p != prov], default=[p for p in provs if p != prov][:1])
    fig = go.Figure()
    for i, p in enumerate([prov] + chosen):
        s = [r for r in store.series(p) if r["ratio"] is not None]
        fig.add_trace(go.Scatter(
            x=[r["period"] for r in s], y=[r["ratio"] * 100 for r in s], name=p, mode="lines+markers",
            line=dict(width=2, color=[ACCENT, ACCENT2, "#2f9e6f", "#8a5cc2"][i % 4]),
            customdata=[[fmt_mm(r["cet1"]["value_mm"]), fmt_mm(r["ata"]["value_mm"]), src_line(r["cet1"]), src_line(r["ata"])] for r in s],
            hovertemplate=("<b>%{fullData.name} %{x}</b><br>Ratio %{y:." + str(dec) + "f}%<br>CET1 %{customdata[0]} ($ millions)"
                           "<br>Adj. total assets %{customdata[1]} ($ millions)<br><i>CET1 src: %{customdata[2]}</i>"
                           "<br><i>ATA src: %{customdata[3]}</i><extra></extra>")))
    fig.update_layout(height=380, margin=dict(l=10, r=10, t=10, b=10), xaxis=dict(type="category"),
                      yaxis=dict(title="CET1 amount ÷ adjusted total assets (%)", ticksuffix="%"), legend=dict(orientation="h", y=1.1))
    st.plotly_chart(fig, width="stretch")
    st.subheader("History")
    st.dataframe(pd.DataFrame([{
        "Period": r["period"], f"CET1 amount ({UNITS})": r["cet1"]["value_mm"], f"Adjusted total assets ({UNITS})": r["ata"]["value_mm"],
        "Ratio (%)": round(r["ratio"] * 100, dec), "Checks": "✓ pass" if not r["failed"] else "✗ " + ", ".join(k["name"] for k in r["failed"]),
        "Source file": r["cet1"]["source_file"]} for r in reversed(ser)]), hide_index=True, width="stretch",
        column_config={f"CET1 amount ({UNITS})": st.column_config.NumberColumn(format="%,d"),
                       f"Adjusted total assets ({UNITS})": st.column_config.NumberColumn(format="%,d")})

# ================================================================ Summary (content formerly on Benchmarks, plus GNMA exposure)
elif page == "Summary":
    periods = sorted({r["period"] for r in store.rows("SELECT DISTINCT period FROM observations")}, reverse=True)
    if not periods:
        st.warning("No data yet.")
        render_gnma_section()
        st.stop()
    period = st.selectbox("Period", periods)
    bt = benchmark_table(period)
    have = [r for r in bt if r["ratio"] is not None]
    st.caption(f"{len(have)} of 10 benchmark slots have data for {period}. Unconfigured slots are set in **Settings → Benchmarks**.")
    if have:
        have_sorted = sorted(have, key=lambda r: r["ratio"], reverse=True)
        fig = go.Figure(go.Bar(
            x=[r["name"] for r in have_sorted], y=[r["ratio"] * 100 for r in have_sorted],
            marker_color=ACCENT, customdata=[[fmt_mm(r["cet1_mm"]), fmt_mm(r["ata_mm"]), src_line(r["cet1_src"]), src_line(r["ata_src"])] for r in have_sorted],
            hovertemplate=("<b>%{x}</b><br>Ratio %{y:." + str(dec) + "f}%<br>CET1 %{customdata[0]} ($ millions)<br>"
                           "Adj. total assets %{customdata[1]} ($ millions)<br><i>CET1 src: %{customdata[2]}</i><br><i>ATA src: %{customdata[3]}</i><extra></extra>")))
        fig.update_layout(height=360, margin=dict(l=10, r=10, t=10, b=10), yaxis=dict(title="Ratio (%)", ticksuffix="%"))
        st.plotly_chart(fig, width="stretch")
    st.dataframe(pd.DataFrame([{
        "Slot": r["slot"], "Benchmark": r["name"] or "—", "Status": r["status"], "Rank": f"{r['rank']} of {r['of']}" if r["rank"] else "—",
        "Percentile": f"{r['percentile']:.0f}" if r["percentile"] is not None else "—",
        "Ratio": fmt_ratio(r["ratio"], dec), f"CET1 ({UNITS})": fmt_mm(r["cet1_mm"]), f"Adj. total assets ({UNITS})": fmt_mm(r["ata_mm"])} for r in bt]),
        hide_index=True, width="stretch")
    st.caption("Rank 1 = highest ratio. Percentile = share of benchmarks with data whose ratio is at or below this one.")
    render_gnma_section()

# ================================================================ Overview (content formerly on Summary)
elif page == "Overview":
    periods = sorted({r["period"] for r in store.rows("SELECT DISTINCT period FROM observations")}, reverse=True)
    if not periods:
        st.warning("No data yet.")
        st.stop()
    period = st.selectbox("Period", periods)
    bt = benchmark_table(period)
    rows = [{
        "Slot": r["slot"], "Benchmark": r["name"] or "(not configured)", "Period": r["period"] or period, "Status": r["status"],
        f"CET1 amount ({UNITS})": r["cet1_mm"], f"Adjusted total assets ({UNITS})": r["ata_mm"],
        "Ratio (%)": None if r["ratio"] is None else round(r["ratio"] * 100, dec), "Ratio (decimal)": None if r["ratio"] is None else round(r["ratio"], dec + 4),
        "Units": "millions", "Rank": r["rank"], "Percentile": None if r["percentile"] is None else round(r["percentile"]),
        "CET1 provenance": src_line(r["cet1_src"]) if r["cet1_src"] else "", "ATA provenance": src_line(r["ata_src"]) if r["ata_src"] else "",
        "Failed checks": ", ".join(r["failed_checks"])} for r in bt]
    df = pd.DataFrame(rows)
    have = [r for r in bt if r["ratio"] is not None]
    if have:
        top, bot = max(have, key=lambda r: r["ratio"]), min(have, key=lambda r: r["ratio"])
        avg = sum(r["ratio"] for r in have) / len(have)
        text = (f"**{period}.** {len(have)} of 10 benchmarks have data. {top['name']} has the highest CET1-based leverage ratio "
                f"({top['ratio'] * 100:.{dec}f}%) and {bot['name']} the lowest ({bot['ratio'] * 100:.{dec}f}%); the average is {avg * 100:.{dec}f}%. ")
        prim = next((r for r in have if r["provider"] == settings["primary_provider"]), None)
        if prim:
            text += f"{prim['name']} ranks {prim['rank']} of {prim['of']} (percentile {prim['percentile']:.0f}). "
        if len(have) < 10:
            text += f"{10 - len(have)} benchmark slot(s) are not configured or have no data for this period, so rank and percentile cover {len(have)} entities only. "
        text += f"All amounts are in {UNITS}."
        st.info(text)
    st.dataframe(df, hide_index=True, width="stretch")
    st.download_button("Download summary CSV", df.to_csv(index=False).encode("utf8"), file_name=f"mcr_summary_{period}.csv", mime="text/csv")

# ================================================================ Data Sources
elif page == "Data Sources":
    c1, c2, c3, _ = st.columns([1, 1, 1, 2])
    if c1.button("Fetch Freddie Mac (latest)"):
        with st.spinner("Fetching from freddiemac.com…"):
            for o in freddie.fetch_latest():
                (st.success if o.status == "ok" else st.warning if o.status == "checks_failed" else st.error)(f"{o.file}: {o.status} {o.message}")
    if c2.button("Fetch Fannie Mae (new)"):
        with st.spinner("Fetching from fanniemae.com…"):
            outs = fannie.fetch()
            st.info("Nothing new." if not outs else "")
            for o in outs:
                (st.success if o.status == "ok" else st.warning if o.status == "checks_failed" else st.error)(f"{o.file}: {o.status} {o.message}")
    if c3.button("Fetch GNMA annual reports"):
        with st.spinner("Fetching and extracting Ginnie Mae annual reports (first run downloads ~300 MB)…"):
            results = gnma.ingest_all()
        got = sum(1 for r in results if r.figures)
        st.success(f"GNMA: {got} of {len(results)} annual reports yielded figures; the others are listed as gaps on the Summary page.")
    st.subheader("Source files behind every stored value")
    obs = store.get_observations()
    st.dataframe(pd.DataFrame(obs)[["provider", "period", "field", "source_file", "table_name", "field_label", "column_name", "location",
                                    "raw_value", "units_detected", "units_source", "value_mm", "source_url", "ingested_at"]] if obs else pd.DataFrame(),
                 hide_index=True, width="stretch")
    st.subheader("Fetch log")
    st.dataframe(pd.DataFrame(store.rows("SELECT ts,url,status,detail FROM fetch_log ORDER BY id DESC LIMIT 100")), hide_index=True, width="stretch")
    st.subheader("Ingest log")
    st.dataframe(pd.DataFrame(store.rows("SELECT ts,file,provider,period,status,detail FROM ingest_log ORDER BY id DESC LIMIT 100")), hide_index=True, width="stretch")
    with st.expander("Application log (tail)"):
        lp = config.LOG_DIR / "mcr.log"
        st.code("\n".join(lp.read_text(encoding="utf8", errors="replace").splitlines()[-80:]) if lp.exists() else "(empty)")

# ================================================================ Uploads
elif page == "Uploads":
    st.write("Upload one or many files: **.pdf** (Fannie Mae / Freddie Mac disclosures), **.xlsx** / **.csv** "
             f"(`{settings['filename_pattern']}`), or a **.zip** package. Each file is validated, parsed, and stored with its provenance.")
    mappings = load_mappings()
    c1, c2, c3 = st.columns(3)
    prov_override = c1.selectbox("Provider", ["(auto-detect)"] + list(mappings))
    period_override = c2.text_input("Period override (e.g. 2026Q3)", "")
    only_newest = c3.checkbox("Only process the newest file per provider", False)
    ups = st.file_uploader("Disclosure files", type=["pdf", "xlsx", "csv", "zip"], accept_multiple_files=True)
    if ups and st.button("Parse uploaded files", type="primary"):
        for up in ups:
            if up.size > config.MAX_UPLOAD_MB * 1e6:
                st.error(f"{up.name}: larger than {config.MAX_UPLOAD_MB} MB")
                continue
            with tempfile.TemporaryDirectory() as td:
                p = Path(td) / Path(up.name).name
                p.write_bytes(up.getvalue())
                outs = ingest_upload(p, None if prov_override.startswith("(") else prov_override, period_override or None, only_newest)
            for o in outs:
                if o.status == "error":
                    st.error(f"**{o.file}** — {o.message}")
                    continue
                (st.success if o.status == "ok" else st.warning)(f"**{o.file}** → {o.provider} {o.period}"
                                                                 + ("" if o.status == "ok" else f" — checks failed: {o.message}"))
                r = o.result
                cet1, ata = r.observations["CET1_amount"], r.observations["Adjusted_total_assets"]
                a, b, c = st.columns(3)
                a.metric(f"CET1 amount ({UNITS})", fmt_mm(cet1.value_mm))
                b.metric(f"Adjusted total assets ({UNITS})", fmt_mm(ata.value_mm))
                c.metric("CET1-based leverage ratio", fmt_ratio(cet1.value_mm / ata.value_mm, dec))
                st.caption(f"CET1: {cet1.provenance_text()} — printed {cet1.raw_value} ({cet1.units_detected})")
                st.caption(f"Adjusted total assets: {ata.provenance_text()} — printed {ata.raw_value} ({ata.units_detected})")
        st.caption("Go to **Benchmarks** to see the updated entity view.")

# ================================================================ Settings
elif page == "Settings":
    t1, t2, t3 = st.tabs(["General", "Benchmarks", "Mappings"])
    with t1:
        provs = list(load_mappings())
        s = dict(settings)
        s["primary_provider"] = st.selectbox("Primary entity", provs, index=provs.index(s["primary_provider"]) if s["primary_provider"] in provs else 0)
        s["ratio_decimals"] = st.slider("Ratio precision (decimal places of the percentage)", 0, 4, int(s["ratio_decimals"]))
        s["filename_pattern"] = st.text_input("File-name pattern (regex with named groups provider and date)", s["filename_pattern"])
        st.caption("Default matches ProviderName_YYYYMMDD_disclosure.xlsx")
        if st.button("Save general settings"):
            try:
                config.save_settings(s)
                st.success("Saved.")
            except Exception as e:
                st.error(f"Invalid pattern: {e}")
    with t2:
        st.write("Ten benchmark slots. Slots 1–2 are Fannie Mae and Freddie Mac. For the others, set a display name and the **provider key** "
                 "of a mapping (see Mappings tab) whose data you have uploaded.")
        ed = st.data_editor(pd.DataFrame(config.load_peers()), hide_index=True, width="stretch", disabled=["slot"],
                            column_config={"provider": st.column_config.SelectboxColumn("provider", options=[""] + list(load_mappings()))})
        if st.button("Save benchmarks"):
            peers = ed.fillna("").to_dict("records")
            peers[0].update(name="Fannie Mae", provider="Fannie Mae")
            peers[1].update(name="Freddie Mac", provider="Freddie Mac")
            config.save_peers(peers)
            st.success("Saved.")
    with t3:
        m = load_mappings()
        st.write("Map each provider's table/field names to the canonical fields **CET1_amount** and **Adjusted_total_assets**. "
                 "PDF providers (Fannie Mae, Freddie Mac) are edited as JSON; spreadsheet providers can use the form below.")
        with st.form("add_tab"):
            st.markdown("**Add / update a spreadsheet (xlsx/csv) provider**")
            name = st.text_input("Provider name (as in the file name, e.g. BankA)")
            cols = st.columns(2)
            specs = {}
            for col, f in zip(cols, CANONICAL_FIELDS):
                with col:
                    st.markdown(f"*{FIELD_LABELS[f]}*")
                    specs[f] = {"sheet": st.text_input("Sheet (optional)", key=f"sh{f}"), "field": st.text_input("Field / line item label", key=f"fl{f}"),
                                "value_column": st.text_input("Value column header (optional)", key=f"vc{f}"),
                                "units": st.selectbox("Units if the file states none", ["millions", "billions", "thousands"], key=f"un{f}")}
            if st.form_submit_button("Save provider mapping"):
                if not name.strip() or not all(specs[f]["field"].strip() for f in CANONICAL_FIELDS):
                    st.error("Provider name and both field labels are required.")
                else:
                    m[name.strip()] = {"kind": "tabular", "fields": {f: {k: v for k, v in sp.items() if v} for f, sp in specs.items()}}
                    save_mappings(m)
                    st.success(f"Saved mapping for {name.strip()}.")
        st.markdown("**Test a mapping against a sample file**")
        tprov = st.selectbox("Provider", [p for p, c in m.items() if c.get("kind") == "tabular"] or ["(none yet)"], key="tp")
        tf = st.file_uploader("Sample .xlsx / .csv", type=["xlsx", "csv"], key="tfile")
        if tf and tprov in m:
            with tempfile.TemporaryDirectory() as td:
                p = Path(td) / Path(tf.name).name
                p.write_bytes(tf.getvalue())
                try:
                    grid = load_grid(str(p))
                    for f in CANONICAL_FIELDS:
                        o = extract_field(grid, m[tprov]["fields"][f], tf.name, f, "test", tprov)
                        st.success(f"{FIELD_LABELS[f]}: {o.raw_value} ({o.units_detected}, {o.units_source}) → {o.value_mm:,.0f} $ millions at {o.location}")
                except MCRError as e:
                    st.error(str(e))
        with st.expander("Raw mappings JSON (advanced; required for PDF providers)"):
            txt = st.text_area("mappings.json", json.dumps(m, indent=2), height=360)
            if st.button("Save JSON"):
                try:
                    save_mappings(json.loads(txt))
                    st.success("Saved.")
                except Exception as e:
                    st.error(f"Not saved: {e}")
