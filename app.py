import streamlit as st
from pathlib import Path
from typing import List

from langchain_core.documents import Document

# ── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Log Pattern Analyst",
    page_icon="🔍",
    layout="wide",
)

# ── Session state defaults ────────────────────────────────────────────────────
if "vectorstore" not in st.session_state:
    st.session_state.vectorstore = None
if "documents" not in st.session_state:
    st.session_state.documents = []


# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("🔍 Log Pattern Analyst")
    st.divider()

    source = st.selectbox("Log Source", ["local", "cloudwatch", "elk"])

    if source == "local":
        log_path = st.text_input("File path", value="./sample_logs/app_errors.log")

    elif source == "cloudwatch":
        log_group = st.text_input("Log Group", value="/app/prod")
        hours = st.number_input("Look-back (hours)", min_value=1, max_value=168, value=2)

    elif source == "elk":
        elk_index = st.text_input("Index pattern", value="app-logs-*")
        start_time = st.text_input("Start (ISO-8601)", placeholder="2026-05-06T13:00:00Z")
        end_time = st.text_input("End (ISO-8601)", placeholder="2026-05-06T14:00:00Z")

    services_filter = st.text_input(
        "Services (comma-separated, optional)",
        placeholder="api-gateway,auth-service",
    )

    st.divider()
    ingest_btn = st.button("⬆️ Ingest Logs", use_container_width=True)

    if st.session_state.documents:
        st.success(f"✅ {len(st.session_state.documents)} events loaded")
    else:
        st.info("No logs loaded yet")

    st.divider()
    st.caption("LLM provider and API keys are set via `.env` or environment variables.")


# ── Ingest handler ────────────────────────────────────────────────────────────
if ingest_btn:
    with st.spinner("Ingesting logs…"):
        try:
            docs = _ingest(source, locals())
            from processing.vectorstore import build_vectorstore
            st.session_state.documents = docs
            st.session_state.vectorstore = build_vectorstore(docs)
            st.sidebar.success(f"✅ Ingested {len(docs)} events")
        except Exception as e:
            st.sidebar.error(f"Ingestion failed: {e}")


def _ingest(source: str, ctx: dict) -> List[Document]:
    if source == "local":
        from ingestion.local_files import load_local_logs
        return load_local_logs(ctx["log_path"])
    elif source == "cloudwatch":
        from ingestion.cloudwatch import fetch_cloudwatch_logs
        return fetch_cloudwatch_logs(log_group=ctx["log_group"], hours=int(ctx["hours"]))
    elif source == "elk":
        from ingestion.elasticsearch import fetch_elk_logs
        return fetch_elk_logs(
            index=ctx["elk_index"],
            start=ctx.get("start_time") or None,
            end=ctx.get("end_time") or None,
        )
    raise ValueError(f"Unknown source: {source}")


# ── Main tabs ─────────────────────────────────────────────────────────────────
tab_anomaly, tab_corr, tab_summary, tab_pm = st.tabs([
    "🚨 Anomalies", "🔗 Correlations", "📋 Summary", "📄 Post-mortem"
])


def _require_docs() -> bool:
    if not st.session_state.documents:
        st.warning("No logs loaded. Use the sidebar to ingest logs first.")
        return False
    return True


def _service_list():
    raw = services_filter.strip()
    return [s.strip() for s in raw.split(",")] if raw else None


# ── Anomalies tab ─────────────────────────────────────────────────────────────
with tab_anomaly:
    st.header("Anomaly Detection")
    if st.button("Run Anomaly Detection", key="btn_anomaly"):
        if _require_docs():
            with st.spinner("Analyzing anomalies…"):
                from analysis.anomaly import analyze_anomalies
                try:
                    report = analyze_anomalies(st.session_state.documents)
                    st.subheader(f"Found {len(report.anomalies)} anomalies")
                    st.write(report.summary)
                    for a in report.anomalies:
                        color = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"}.get(a.severity, "⚪")
                        with st.expander(f"{color} [{a.severity.upper()}] {a.type}"):
                            st.write(f"**Description:** {a.description}")
                            st.write(f"**Affected services:** {', '.join(a.affected_services)}")
                            st.write("**Evidence:**")
                            for ev in a.evidence:
                                st.code(ev)
                except Exception as e:
                    st.error(f"Analysis failed: {e}")


# ── Correlations tab ──────────────────────────────────────────────────────────
with tab_corr:
    st.header("Cross-Service Correlation")
    if st.button("Run Correlation Analysis", key="btn_corr"):
        if _require_docs():
            with st.spinner("Correlating services…"):
                from analysis.correlation import correlate_services
                try:
                    result = correlate_services(
                        st.session_state.documents,
                        services=_service_list(),
                        vectorstore=st.session_state.vectorstore,
                    )
                    st.markdown(result)
                except Exception as e:
                    st.error(f"Correlation failed: {e}")


# ── Summary tab ───────────────────────────────────────────────────────────────
with tab_summary:
    st.header("Time-Window Summary")
    col1, col2 = st.columns(2)
    with col1:
        sum_start = st.text_input("Start filter (optional)", key="sum_start", placeholder="2026-05-06T13:45")
    with col2:
        sum_end = st.text_input("End filter (optional)", key="sum_end", placeholder="2026-05-06T13:50")

    if st.button("Summarize Window", key="btn_summary"):
        if _require_docs():
            with st.spinner("Summarizing…"):
                from analysis.summarizer import summarize_window
                try:
                    result = summarize_window(
                        st.session_state.documents,
                        start=sum_start or None,
                        end=sum_end or None,
                    )
                    st.markdown(result)
                except Exception as e:
                    st.error(f"Summarization failed: {e}")


# ── Post-mortem tab ───────────────────────────────────────────────────────────
with tab_pm:
    st.header("Post-Mortem Report")
    output_path = st.text_input("Save to file (optional)", placeholder="./reports/incident.md")

    if st.button("Generate Post-Mortem", key="btn_pm"):
        if _require_docs():
            with st.spinner("Generating post-mortem (this may take ~30s)…"):
                from analysis.postmortem import generate_postmortem, postmortem_to_markdown
                try:
                    pm = generate_postmortem(
                        st.session_state.documents,
                        services=_service_list(),
                        vectorstore=st.session_state.vectorstore,
                    )
                    md = postmortem_to_markdown(pm)

                    st.markdown(md)

                    if output_path.strip():
                        p = Path(output_path.strip())
                        p.parent.mkdir(parents=True, exist_ok=True)
                        p.write_text(md, encoding="utf-8")
                        st.success(f"Saved to {output_path}")

                    st.download_button(
                        "⬇️ Download Markdown",
                        data=md,
                        file_name="postmortem.md",
                        mime="text/markdown",
                    )
                except Exception as e:
                    st.error(f"Post-mortem generation failed: {e}")
