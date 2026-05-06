# Log Pattern Analyst

AI-powered log analysis tool that identifies anomalies, correlates errors across services, summarizes time windows, and generates structured post-mortem reports. Uses LangChain with configurable LLM providers (Anthropic Claude or OpenAI). Exposed as both a CLI and a Streamlit UI.

## Architecture

```
Logs (CloudWatch / ELK / Local)
         │
         ▼
  ┌─────────────┐
  │  Ingestion   │  → normalised LangChain Documents
  └──────┬──────┘
         │
         ▼
  ┌─────────────┐
  │  Chunker    │  → timestamp-grouped chunks
  └──────┬──────┘
         │
         ▼
  ┌─────────────┐
  │  FAISS      │  → local vector index (no server needed)
  └──────┬──────┘
         │
    ┌────┴─────────────────────────┐
    │                              │
    ▼                              ▼
┌──────────┐  ┌───────────┐  ┌──────────┐
│ Anomaly  │  │Correlation│  │Summarizer│
│ Chain    │  │ Chain     │  │(MapReduce│
└────┬─────┘  └─────┬─────┘  └────┬─────┘
     └───────────────┴─────────────┘
                     │
                     ▼
            ┌────────────────┐
            │  Post-Mortem   │  → structured Markdown report
            │ (SequentialChain│
            └────────────────┘
```

## Quick Start

### 1. Clone and install

```bash
git clone https://github.com/your-username/log-pattern-analyst
cd log-pattern-analyst
pip install -r requirements.txt
```

### 2. Configure

```bash
cp .env.example .env
# Edit .env — set LLM_PROVIDER and the matching API key
```

### 3. Ingest sample logs

```bash
python cli.py ingest --source local --path sample_logs/app_errors.log
```

### 4. Run analysis

```bash
python cli.py analyze anomaly
python cli.py analyze correlate --services api-gateway,auth-service,db-primary
python cli.py analyze summarize --start "2026-05-06T13:45" --end "2026-05-06T13:47"
python cli.py analyze postmortem --output ./reports/incident.md
```

### 5. Launch the UI

```bash
streamlit run app.py
```

## Configuration

All config is read from environment variables (`.env` is auto-loaded):

| Variable | Default | Description |
|---|---|---|
| `LLM_PROVIDER` | `anthropic` | `anthropic` or `openai` |
| `ANTHROPIC_API_KEY` | — | Required when using Anthropic |
| `ANTHROPIC_MODEL` | `claude-sonnet-4-6` | Anthropic model ID |
| `OPENAI_API_KEY` | — | Required when using OpenAI |
| `OPENAI_MODEL` | `gpt-4o` | OpenAI model ID |
| `EMBEDDINGS_PROVIDER` | `huggingface` | `huggingface` (offline) or `openai` |
| `HUGGINGFACE_MODEL` | `all-MiniLM-L6-v2` | Sentence-transformer model |
| `VECTORSTORE_PATH` | `./vectorstore` | FAISS index directory |
| `AWS_REGION` | `us-east-1` | CloudWatch region |
| `ES_HOST` | `http://localhost:9200` | Elasticsearch/OpenSearch URL |

## CLI Reference

### Ingestion

```bash
# From CloudWatch
python cli.py ingest --source cloudwatch --log-group /app/prod --hours 2

# From ELK / OpenSearch
python cli.py ingest --source elk --index app-logs-* --start "2026-05-06T13:00Z"

# From local file (.log / .json / .ndjson)
python cli.py ingest --source local --path ./sample_logs/app_errors.log

# Append to existing vectorstore
python cli.py ingest --source local --path more_logs.log --append
```

### Analysis

```bash
# Detect anomalies
python cli.py analyze anomaly

# Correlate service failures
python cli.py analyze correlate --services api-gateway,auth-service,db-primary

# Summarize a time window
python cli.py analyze summarize --start "13:45" --end "14:00"

# Full post-mortem (runs all three analyses)
python cli.py analyze postmortem --output ./reports/incident-2026-05-06.md
```

## Supported Log Formats

| Format | Extension | Detection |
|---|---|---|
| Plain text logs | `.log` | Line-by-line, extracts timestamp/level/service via regex |
| CloudWatch export | `.json` | `events[]` array with `timestamp` + `message` |
| ELK/OpenSearch export | `.json` | `hits.hits[]` with `_source` |
| NDJSON | `.ndjson` | One JSON object per line |

## Post-Mortem Schema

```python
class PostMortem(BaseModel):
    title: str
    timeline: List[TimelineEvent]   # timestamp, service, event, severity
    root_cause: str
    impact: str
    remediation_steps: List[str]
    open_questions: List[str]
```

Output is a structured Markdown report saved to the path you specify.

## Running Tests

```bash
pytest tests/ -v
```

Tests use mocked LLM calls and local sample data — no API keys or external services required.

## Sample Output

```
Found 4 anomalies

Summary: A database connection pool exhaustion on db-primary triggered a cascade
failure across auth-service, payment-service, and order-service lasting ~90 seconds.

[1] [CRITICAL] database_connection_exhaustion
    DB primary connection pool exhausted (max 500), causing auth-service circuit
    breaker to open and downstream payment/order failures.
    Services: db-primary, auth-service, payment-service, order-service
    > Max connections reached max_connections=500 current=498
    > Circuit breaker OPEN for db-primary after 5 consecutive failures
```

## Project Structure

```
├── config.py                  # Env-driven configuration
├── cli.py                     # Click CLI entry point
├── app.py                     # Streamlit UI
├── ingestion/
│   ├── cloudwatch.py          # boto3 → CloudWatch log fetch
│   ├── elasticsearch.py       # elasticsearch-py → ELK/OpenSearch
│   └── local_files.py         # .log / .json / .ndjson loader
├── processing/
│   ├── chunker.py             # Timestamp-aware log chunking
│   └── vectorstore.py         # FAISS index build/save/load
├── analysis/
│   ├── anomaly.py             # Anomaly detection chain
│   ├── correlation.py         # Cross-service correlation chain
│   ├── summarizer.py          # Map-reduce time-window summarizer
│   └── postmortem.py          # Sequential post-mortem generator
├── llm/
│   └── providers.py           # get_llm() / get_embeddings() abstraction
├── sample_logs/
│   ├── app_errors.log         # Multi-service plain-text log
│   ├── cloudwatch_sample.json # Mock CloudWatch events
│   └── elk_sample.json        # Mock ELK hit documents
└── tests/                     # pytest suite — all mocked, no API keys needed
```
