# AGENTS.md — Earth Pulse MCP

## What This Project Is

An MCP server that ingests BBC News, enriches articles with GPT, and exposes civilization-level intelligence tools (mood, trends, narrative evolution, regional emotion). **Not** a news summarizer — the goal is synthesis and interpretation of humanity's state.

See `project.md` for the full vision, DB schema, example outputs, user stories, and build phases.
See `PHASE2.md` for the deferred backlog — all interfaces are pre-designed to accept Phase 2 adapters with zero core rewrites.

---

## Tech Stack (Locked)

- **Language**: Python 3.12+
- **Package manager**: `uv` — always use `uv`, never `pip` or `poetry`
- **API framework**: FastAPI
- **MCP SDK**: official Python MCP SDK, HTTP Streamable transport only (no SSE, no stdio)
- **MCP auth**: API key via `Authorization: Bearer <key>` header; 401 on missing/invalid key
- **MCP mount point**: `/mcp` inside FastAPI
- **AI**: OpenAI GPT-5.4 (single model for both synthesis and enrichment, configured in `config.toml`)
- **Embeddings**: `text-embedding-3-large` — deferred to Phase 2, table exists but unpopulated
- **DB (MVP)**: SQLite with WAL mode (`PRAGMA journal_mode=WAL`)
- **Scheduler**: APScheduler behind `SchedulerPort` interface
- **Infra**: Docker Compose

---

## Key Commands

```bash
# Install deps
uv sync

# Run MCP server (dev)
uv run python -m earth_pulse.server

# Run ingestion worker
uv run python -m earth_pulse.ingestion

# Run tests (100% coverage required — fail if below)
uv run pytest --cov=earth_pulse --cov-fail-under=100

# Lint + typecheck
uv run ruff check .
uv run pyrefly check
```

Pre-commit order: `ruff → pyrefly → pytest`

**Typecheck**: use **pyrefly** only. Do not add mypy.

---

## Project Structure (target)

```
earth_pulse/
  ingestion/        # RSS fetch, normalization, deduplication, per-source adapters
  enrichment/       # GPT enrichment pipeline (async, separate worker)
  temporal/         # Trend detection, narrative shift, acceleration
  mcp/              # MCP server, 3 tool definitions, auth middleware
  db/               # DB models, migrations (Alembic for Postgres upgrade path)
  config.py         # Typed Settings dataclass, tomllib loader, env var overrides
  observability/    # ObservabilityPort + default JSON logging adapter
  scheduler/        # SchedulerPort + APSchedulerAdapter
  circuit_breaker/  # CircuitBreakerPort + in-memory adapter
config.toml         # User-editable, in .gitignore
config.toml.example # Committed placeholder
docker-compose.yml
pyproject.toml      # uv-managed
PHASE2.md           # Deferred features backlog
```

---

## Architecture — Ports and Adapters (SOLID)

Every external dependency is behind an interface. Swapping implementations never touches business logic.

| Port | MVP Adapter | Phase 2 Swap |
|---|---|---|
| `SchedulerPort` | `APSchedulerAdapter` | `CeleryAdapter` |
| `DatabasePort` | `SQLiteAdapter` | `PostgreSQLAdapter` |
| `EmbeddingPort` | `NoOpEmbeddingAdapter` | `OpenAIEmbeddingAdapter` |
| `ObservabilityPort` | `JSONLoggingAdapter` | `SentryAdapter` / `DatadogAdapter` |
| `CircuitBreakerPort` | `InMemoryCircuitBreakerAdapter` | `RedisCircuitBreakerAdapter` |
| `FeedSourcePort` | `BBCRSSAdapter`, `BBCUnofficialAdapter` | any new source |

---

## Configuration

`config.toml` loaded via `tomllib` (Python 3.11+ stdlib) into a typed `Settings` dataclass. Env vars override config values. App fails fast at startup if required fields are missing.

```toml
[openai]
api_key = "sk-..."
chat_model = "gpt-5.4"
embedding_model = "text-embedding-3-large"

[server]
api_key = "your-mcp-api-key"

[ingestion]
poll_interval_minutes = 15

[database]
url = "sqlite:///earth_pulse.db"

[sources.bbc_rss]
enabled = true

[sources.bbc_unofficial]
enabled = true
# minimum floor: 30 minutes regardless of poll_interval_minutes
```

- `config.toml` is in `.gitignore`. Only `config.toml.example` is committed.
- Env var override pattern: `OPENAI__API_KEY`, `SERVER__API_KEY`, etc.

---

## Data Sources

| Source | Auth | Reliability | Min Poll |
|---|---|---|---|
| BBC RSS feeds | None | Primary — stable, no SLA needed | 15 min |
| BBC unofficial Vercel API | None | Secondary — best-effort, no SLA | 30 min (hardcoded floor) |

BBC NEWSHUB API: stubbed as `NewsHubAdapter` (not implemented) — add if BBC partnership obtained. See `PHASE2.md`.

---

## Canonical Article Model

```python
@dataclass
class Article:
    id: str              # SHA256 of URL
    title: str
    summary: str | None
    body_text: str | None  # body text when available; RSS provides partial text
    url: str
    url_hash: str          # primary dedup key
    title_hash: str        # normalized title hash, secondary dedup key
    source: str            # "bbc_rss" | "bbc_unofficial"
    region: str | None     # 8-region vocab (see below); GPT-inferred if not in metadata
    category: str | None
    language: str          # default "en"; stored for Phase 2 multilingual support
    published_at: datetime # UTC
    ingested_at: datetime  # UTC
```

**Region vocabulary:** `Africa | Asia | Europe | Latin America | Middle East | North America | Oceania | Global`

**Deduplication:** URL hash first (exact), then normalized title hash (cross-source). Two-stage.

---

## Ingestion Pipeline

```
FeedSourcePort.fetch()
  → normalize to Article
  → two-stage dedup check (URL hash, then title hash)
  → store raw Article (DB)
  → [enrichment worker picks up separately]
```

Enrichment is **asynchronous** — a separate APScheduler job polls for unenriched articles and processes them in batches. Raw articles are never deleted — re-enrichment on model upgrade is possible (see `PHASE2.md`).

---

## GPT Enrichment

- Uses `chat_model` from config (same model for enrichment and synthesis)
- OpenAI **structured output** (`response_format=json_schema`) — strict schema, never free-form
- Article content passed in a delimited block, never interpolated into system prompt (LLM01 mitigation)
- System prompt is static and server-side only (LLM07 mitigation)
- Malformed responses rejected before storage (LLM05 mitigation)
- Failed enrichments after 3 retries → marked `enrichment_failed` in DB (dead-letter)

**Enrichment output schema:**
```json
{
  "emotion": "anxiety",
  "topics": ["energy", "conflict"],
  "narratives": ["escalation"],
  "region": "Middle East",
  "urgency_score": 0.82,
  "anxiety_score": 0.79,
  "optimism_score": 0.11,
  "conflict_score": 0.91,
  "stability_score": 0.12
}
```

---

## MCP Tools — 3 Tools

All tools are **read-only**. All responses include `sources` (article IDs) for auditability (LLM09 mitigation).

```python
query_mood(region: str | None = None, compare_with: str | None = None)
# None → global mood
# region only → single region
# both → side-by-side comparison

query_trends(hours: int = 24, mode: Literal["emerging", "shifts", "pulse"] = "pulse")
# emerging → accelerating topics
# shifts   → framing/narrative changes
# pulse    → what changed in N hours / humanity's focus

query_timeline(topic: str, since: str | None = None)
# narrative evolution for a topic over time
```

**Response structure (all tools):**
```json
{
  "synthesis": "...",
  "sources": ["article_id_1", "article_id_2"],
  "generated_at": "2026-05-11T14:00:00Z",
  "period_hours": 24
}
```

---

## Database Schema

Three tables: `articles`, `enrichments`, `embeddings`.
`embeddings` table exists but is unpopulated in MVP.
See `project.md` §18 for DDL.
Alembic migration path ready for PostgreSQL upgrade (see `PHASE2.md`).

SQLite WAL mode enabled on connection: `PRAGMA journal_mode=WAL`

---

## Error Handling & Observability

- **Structured JSON logging** via `ObservabilityPort` (swappable — see `PHASE2.md`)
- **Per-source circuit breaker** via `CircuitBreakerPort`: 3 consecutive failures → OPEN, skip one full cycle, then retry
- **Enrichment dead-letter**: articles failing enrichment after 3 retries marked `enrichment_failed` with error reason stored

---

## Security — OWASP LLM Top 10 (2025)

| Risk | Mitigation |
|---|---|
| **LLM01 Prompt Injection** | Article content in delimited block; never interpolated into system prompt; static system prompt only |
| **LLM02 Sensitive Info Disclosure** | Never return raw DB rows; synthesis only in tool responses |
| **LLM03 Supply Chain** | `uv lock`; check PyPI recency before adding packages; no packages with anomalous recent activity |
| **LLM05 Improper Output Handling** | Structured output enforced; malformed GPT responses rejected before storage |
| **LLM06 Excessive Agency** | All MCP tools read-only; no tool writes, deletes, or triggers side effects |
| **LLM07 System Prompt Leakage** | Synthesis prompts server-side only; never reconstructable from tool outputs |
| **LLM08 Vector/Embedding Weaknesses** | Embedding dimensions validated before storage (Phase 2) |
| **LLM09 Misinformation** | All synthesis cites article IDs; assertions without source articles rejected |
| **LLM10 Unbounded Consumption** | Rate-limit GPT calls per cycle; cap enrichment batch size; enforce token limits per tool call |

---

## Security — OWASP MCP / Agentic

Source: [OWASP Agentic Security Initiative](https://genai.owasp.org/initiatives/agentic-security-initiative/) + [Secure MCP Server Guide](https://genai.owasp.org/resource/a-practical-guide-for-secure-mcp-server-development/)

| Risk | Mitigation |
|---|---|
| **Tool poisoning** | MCP tool descriptions are static and code-defined — never generated from external input |
| **Manifest tampering** | MCP manifest served from versioned endpoint; any change is logged |
| **Excessive tool permissions** | Each tool has narrow declared scope; no file system, env var, or network access beyond declared data source |
| **Confused deputy** | Caller context validated on every MCP tool invocation |
| **Data exfiltration via output** | Synthesized text only; never raw DB dumps, embeddings, or API keys |
| **Prompt injection via tool results** | Article content sanitized before flowing into any synthesis prompt |

---

## Testing Requirements

- **100% coverage** enforced via `--cov-fail-under=100`
- No real network calls in any test — all external HTTP mocked (`respx`)
- No real OpenAI calls — mock with recorded fixtures

```
tests/
  unit/           # business logic, dedup, normalization, config validation, circuit breaker
  integration/    # full pipeline: fake feed → DB → enrichment → MCP tool response
  security/       # prompt injection attempts, malformed GPT responses, missing API key → 401, rate limiting
  conftest.py     # shared fixtures: in-memory SQLite, mock HTTP clients, mock OpenAI
```

---

## Docker Compose

```
app     — FastAPI + MCP server (port 8000)
worker  — APScheduler ingestion + enrichment worker
```

PostgreSQL + Redis added in Phase 2 (see `PHASE2.md`).

```bash
docker compose up --build
```

---

## Critical Constraints

- **No predictions**: discuss momentum/trends only, never predict outcomes
- **No sensationalism**: tone is calm, philosophical, analytical
- **No hallucinations**: all synthesis must derive from ingested articles with citable IDs
- **No summarizing headlines**: synthesize patterns, interpret emotional movement
- **Deduplication required** in ingestion (URL hash + title hash)
- **Retry handling required** for all feed fetches
- **Raw articles never deleted** — enables re-enrichment on model upgrade

---

## Package Version Policy

Always use the **latest stable version** of every dependency. Before adding any package: check PyPI publish recency, number of maintainers, anomalous recent release activity. This is LLM03 (supply chain) mitigation. Run `uv lock` after every dependency change.

---

## PRD Reference

Full PRD, user stories, example prompts/outputs, emotional taxonomy, topic taxonomy, and build phases: `project.md`.
Deferred Phase 2 features with pickup instructions: `PHASE2.md`.
