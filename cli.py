import sys
import json
from pathlib import Path

import click

from config import VECTORSTORE_PATH


@click.group()
def cli():
    """Log Pattern Analyst — ingest logs and run AI-powered analysis."""


# ---------------------------------------------------------------------------
# ingest
# ---------------------------------------------------------------------------

@cli.command()
@click.option("--source", type=click.Choice(["cloudwatch", "elk", "local"]), required=True)
@click.option("--log-group", default=None, help="CloudWatch log group name")
@click.option("--hours", default=2, show_default=True, help="Look-back window in hours")
@click.option("--index", default=None, help="ELK index pattern")
@click.option("--start", default=None, help="Start time ISO-8601 (ELK)")
@click.option("--end", default=None, help="End time ISO-8601 (ELK)")
@click.option("--path", default=None, help="Local file path (.log / .json / .ndjson)")
@click.option("--append", is_flag=True, default=False, help="Add to existing vectorstore")
@click.option("--vectorstore-path", default=VECTORSTORE_PATH, show_default=True)
def ingest(source, log_group, hours, index, start, end, path, append, vectorstore_path):
    """Ingest logs from CloudWatch, ELK, or a local file into the vector store."""
    from processing.vectorstore import build_vectorstore, save_vectorstore, load_vectorstore, add_documents

    click.echo(f"Ingesting from {source}...")

    documents = _load_source(source, log_group, hours, index, start, end, path)
    click.echo(f"Loaded {len(documents)} log events.")

    if append and Path(vectorstore_path).exists():
        vs = load_vectorstore(vectorstore_path)
        if vs is None:
            click.echo("No existing vectorstore found — creating new one.", err=True)
            vs = build_vectorstore(documents)
        else:
            vs = add_documents(vs, documents)
            click.echo("Appended to existing vectorstore.")
    else:
        vs = build_vectorstore(documents)
        click.echo("Built new vectorstore.")

    save_vectorstore(vs, vectorstore_path)
    click.echo(f"Vectorstore saved to {vectorstore_path}")


def _load_source(source, log_group, hours, index, start, end, path):
    if source == "cloudwatch":
        if not log_group:
            raise click.UsageError("--log-group is required for cloudwatch source")
        from ingestion.cloudwatch import fetch_cloudwatch_logs
        return fetch_cloudwatch_logs(log_group=log_group, hours=hours)

    if source == "elk":
        if not index:
            raise click.UsageError("--index is required for elk source")
        from ingestion.elasticsearch import fetch_elk_logs
        return fetch_elk_logs(index=index, start=start, end=end, hours=hours)

    if source == "local":
        if not path:
            raise click.UsageError("--path is required for local source")
        from ingestion.local_files import load_local_logs
        return load_local_logs(path)

    raise click.UsageError(f"Unknown source: {source}")


# ---------------------------------------------------------------------------
# analyze
# ---------------------------------------------------------------------------

@cli.group()
def analyze():
    """Run analysis chains against the loaded vector store."""


@analyze.command()
@click.option("--vectorstore-path", default=VECTORSTORE_PATH, show_default=True)
def anomaly(vectorstore_path):
    """Detect anomalies in the ingested logs."""
    docs = _require_docs(vectorstore_path)
    from analysis.anomaly import analyze_anomalies

    click.echo("Running anomaly detection...\n")
    report = analyze_anomalies(docs)

    click.echo(f"Found {len(report.anomalies)} anomalies\n")
    click.echo(f"Summary: {report.summary}\n")
    for i, a in enumerate(report.anomalies, 1):
        click.echo(f"[{i}] [{a.severity.upper()}] {a.type}")
        click.echo(f"    {a.description}")
        click.echo(f"    Services: {', '.join(a.affected_services)}")
        for ev in a.evidence[:2]:
            click.echo(f"    > {ev}")
        click.echo()


@analyze.command()
@click.option("--services", default=None, help="Comma-separated service names to focus on")
@click.option("--vectorstore-path", default=VECTORSTORE_PATH, show_default=True)
def correlate(services, vectorstore_path):
    """Find causal chains across services."""
    docs = _require_docs(vectorstore_path)
    vs = _load_vs(vectorstore_path)
    service_list = [s.strip() for s in services.split(",")] if services else None
    from analysis.correlation import correlate_services

    click.echo("Running correlation analysis...\n")
    result = correlate_services(docs, services=service_list, vectorstore=vs)
    click.echo(result)


@analyze.command()
@click.option("--start", default=None, help="Start time filter (ISO prefix)")
@click.option("--end", default=None, help="End time filter (ISO prefix)")
@click.option("--vectorstore-path", default=VECTORSTORE_PATH, show_default=True)
def summarize(start, end, vectorstore_path):
    """Summarize the log time window."""
    docs = _require_docs(vectorstore_path)
    from analysis.summarizer import summarize_window

    click.echo("Summarizing log window...\n")
    result = summarize_window(docs, start=start, end=end)
    click.echo(result)


@analyze.command()
@click.option("--services", default=None, help="Comma-separated service names")
@click.option("--output", default=None, help="Output file path for Markdown report")
@click.option("--vectorstore-path", default=VECTORSTORE_PATH, show_default=True)
def postmortem(services, output, vectorstore_path):
    """Generate a structured post-mortem report."""
    docs = _require_docs(vectorstore_path)
    vs = _load_vs(vectorstore_path)
    service_list = [s.strip() for s in services.split(",")] if services else None
    from analysis.postmortem import generate_postmortem, postmortem_to_markdown

    click.echo("Generating post-mortem...\n")
    pm = generate_postmortem(docs, services=service_list, vectorstore=vs)
    md = postmortem_to_markdown(pm)

    if output:
        Path(output).parent.mkdir(parents=True, exist_ok=True)
        Path(output).write_text(md, encoding="utf-8")
        click.echo(f"Post-mortem saved to {output}")
    else:
        click.echo(md)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _require_docs(vectorstore_path: str):
    from processing.vectorstore import load_vectorstore

    vs = load_vectorstore(vectorstore_path)
    if vs is None:
        click.echo(f"No vectorstore found at {vectorstore_path}. Run 'ingest' first.", err=True)
        sys.exit(1)

    try:
        docs = vs.docstore._dict.values()
        return list(docs)
    except Exception:
        click.echo("Could not read documents from vectorstore.", err=True)
        sys.exit(1)


def _load_vs(vectorstore_path: str):
    from processing.vectorstore import load_vectorstore
    return load_vectorstore(vectorstore_path)


if __name__ == "__main__":
    cli()
