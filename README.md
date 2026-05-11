# Earth Pulse

**An AI that observes humanity in real time.**

Earth Pulse is not a news reader. It is a planetary intelligence system that continuously ingests BBC News, enriches every article with GPT, and exposes the synthesized understanding of the world through an MCP server that any AI assistant can connect to.

Ask it what humanity is worried about. Ask it how AI coverage evolved over the last year. Ask it to compare the emotional atmosphere of Europe and Asia. It will not give you headlines — it will give you interpretation.

---

## What it does

Every 15 minutes, Earth Pulse:

1. Pulls fresh articles from BBC RSS feeds and the BBC unofficial API
2. Deduplicates across sources so the same story is never counted twice
3. Sends each new article to GPT, which assigns emotion, topics, narratives, and numeric scores (anxiety, urgency, optimism, conflict, stability)
4. Stores everything in a local SQLite database
5. Makes three MCP tools available to any connected AI assistant

When you ask a question through an MCP-compatible client (Claude Desktop, Cursor, etc.), Earth Pulse queries the enriched database, packs the most relevant articles into a token-bounded context window, and asks GPT to synthesize a calm, grounded, philosophical response — not a summary of headlines, but an interpretation of what is happening and why it matters.

---

## The three tools

| Tool | What it answers |
|---|---|
| `query_mood` | The emotional atmosphere of the world or a specific region, optionally compared side-by-side with another region |
| `query_trends` | What is emerging, what narratives are shifting, what changed in the last N hours |
| `query_timeline` | How a specific topic has evolved over time — the narrative arc from first mention to now |

---

## Questions you can ask

These are real prompts you can send once Earth Pulse is connected to your AI assistant.

**Planetary awareness**
- What changed in the world today?
- What is humanity worried about right now?
- What stories are dominating global attention?
- What tensions are increasing?

**Emotional intelligence**
- What is the emotional mood of Europe?
- Is global anxiety increasing?
- How does Asia compare emotionally to North America?
- What emotions dominate technology news?

**Narrative evolution**
- How did AI coverage evolve over the last year?
- When did inflation become a dominant narrative?
- How has climate anxiety changed since 2023?
- How has the tone around the Ukraine conflict shifted?

**Civilization reflection**
- Is humanity becoming more hopeful?
- What fears dominate modern society?
- What signs of optimism appeared this week?
- What is humanity collectively obsessed with right now?

---

## What it is not

- It does not summarize headlines
- It does not predict outcomes (wars, elections, markets)
- It does not tell you what to think
- It does not retrieve raw articles

It synthesizes patterns and interprets emotional movement. Every response cites the article IDs it drew from so you can verify the grounding.

---

## Data sources

| Source | Coverage | Notes |
|---|---|---|
| BBC RSS feeds | Global, UK, World, Science, Technology, Health, etc. | Free, no key required, polled every 15 min |
| BBC unofficial Vercel API | Additional BBC categories | Community API, no key required, polled every 30 min minimum |

---

## Prerequisites

You need the following before starting:

- **Python 3.12 or later** — check with `python3 --version`
- **uv** — the Python package manager used by this project
- **Docker and Docker Compose** — only needed for the containerized setup
- **An OpenAI API key** — GPT-5.4 is used for enrichment and synthesis

### Installing uv

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

---

## Getting started — local development

### 1. Clone the repository

```bash
git clone <repo-url>
cd bbc-earth-pulse
```

### 2. Install dependencies

```bash
uv sync
```

### 3. Configure

Copy the example config and fill in your keys:

```bash
cp config.toml.example config.toml
```

Edit `config.toml`:

```toml
[openai]
api_key = "sk-your-openai-key"
chat_model = "gpt-5.4"
embedding_model = "text-embedding-3-large"

[server]
api_key = "choose-any-secret-string"   # this is what MCP clients use to authenticate
host = "0.0.0.0"
port = 8000

[ingestion]
poll_interval_minutes = 15

[database]
url = "sqlite:///earth_pulse.db"

[sources.bbc_rss]
enabled = true

[sources.bbc_unofficial]
enabled = true
```

The `server.api_key` is a secret you choose yourself — it can be any string. MCP clients send it as `Authorization: Bearer <key>` on every request.

### 4. Start the ingestion worker

This process polls the news sources and enriches articles with GPT. Run it in one terminal:

```bash
uv run python -m earth_pulse.worker
```

You will see structured JSON log output as articles are fetched and enriched. Let it run for a few minutes before querying — the database needs some content.

### 5. Start the MCP server

In a second terminal:

```bash
uv run python -m earth_pulse.server
```

The server is now running at `http://localhost:8000`. The MCP endpoint is at `http://localhost:8000/mcp`.

### 6. Health check

```bash
curl http://localhost:8000/health
```

Should return `{"status": "ok"}`.

---

## Getting started — Docker Compose

This runs both the MCP server and the ingestion worker in containers with a shared persistent database volume.

### 1. Copy and fill in the environment file

```bash
cp .env.example .env
```

Edit `.env`:

```
OPENAI__API_KEY=sk-your-openai-key
SERVER__API_KEY=choose-any-secret-string
INGESTION__POLL_INTERVAL_MINUTES=15
```

### 2. Build and start

```bash
docker compose up --build
```

Both containers start. The worker begins ingesting immediately. The server is available at `http://localhost:8000/mcp` once healthy.

### 3. Stop

```bash
docker compose down
```

Data persists in the `earth_pulse_data` Docker volume between restarts.

---

## Connecting to an AI assistant

### Claude Desktop

Add this to your Claude Desktop MCP config (`~/Library/Application Support/Claude/claude_desktop_config.json` on macOS):

```json
{
  "mcpServers": {
    "earth-pulse": {
      "url": "http://localhost:8000/mcp",
      "headers": {
        "Authorization": "Bearer your-server-api-key"
      }
    }
  }
}
```

Restart Claude Desktop. Earth Pulse tools will appear in the tool list.

### Cursor

Add a new MCP server in Cursor settings:

- **URL**: `http://localhost:8000/mcp`
- **Header**: `Authorization: Bearer your-server-api-key`

### Any other MCP client

Earth Pulse uses HTTP Streamable transport. Point your client at `http://localhost:8000/mcp` and include `Authorization: Bearer <your-server-api-key>` in every request header.

---

## How it works — technical overview

```
BBC RSS + BBC Unofficial API
            ↓
     Ingestion worker (APScheduler, every 15 min)
            ↓
     Normalization + two-stage deduplication
     (URL hash first, normalized title hash second)
            ↓
     SQLite database (WAL mode)
            ↓
     Enrichment worker (async, separate scheduler job)
     GPT-5.4 → emotion, topics, narratives, 5 numeric scores
            ↓
     MCP server (FastAPI + official MCP SDK, HTTP Streamable)
            ↓
     query_mood / query_trends / query_timeline
     ↓ token-budget article packing (tiktoken)
     ↓ GPT-5.4 synthesis
     ↓ response with cited article IDs
```

### Architecture

The codebase uses a ports-and-adapters (hexagonal) architecture. Every external dependency — database, scheduler, circuit breaker, observability, feed sources — sits behind an interface. Swapping SQLite for PostgreSQL, or APScheduler for Celery, touches only the adapter, not the business logic.

| Port | Current adapter |
|---|---|
| Database | SQLite with WAL |
| Scheduler | APScheduler |
| Circuit breaker | In-memory (per-source, 3-failure threshold) |
| Observability | Structured JSON logging |
| Feed sources | BBC RSS, BBC unofficial |
| Embeddings | No-op (deferred to Phase 2) |

### Security

- All MCP tools are **read-only** — no tool writes, deletes, or triggers side effects
- Article content is passed to GPT in a delimited block (`<article>…</article>`), never interpolated into the system prompt (OWASP LLM01 prompt injection mitigation)
- Synthesis prompts are server-side only and never reconstructable from tool output (LLM07)
- Malformed GPT responses are rejected before storage (LLM05)
- Every synthesis response includes source article IDs — no assertion without a grounded source (LLM09)
- MCP API key required on every request — 401 on missing or invalid key

---

## Project structure

```
earth_pulse/
  ingestion/        # RSS fetch, normalization, deduplication, per-source adapters
  enrichment/       # GPT enrichment pipeline (async worker)
  temporal/         # Trend detection, narrative shift, token-budget synthesis
  mcp/              # MCP server, tool definitions, auth middleware
  db/               # SQLite adapter, DDL, all queries
  config.py         # Typed Settings, tomllib loader, env var overrides
  observability/    # Structured JSON logging adapter
  scheduler/        # APScheduler adapter
  circuit_breaker/  # In-memory circuit breaker adapter
  server.py         # FastAPI app + FastMCP tool registration
  worker.py         # Ingestion + enrichment worker entrypoint
config.toml         # Your local config — not committed
config.toml.example # Template — committed
docker-compose.yml
pyproject.toml
PHASE2.md           # Deferred features with pickup instructions
project.md          # Full PRD, vision, example outputs
```

---

## Running the tests

```bash
uv run pytest
```

The test suite requires 100% coverage and will fail if any line is uncovered. All external HTTP calls and OpenAI calls are mocked — no real network traffic, no real API keys needed for tests.

```bash
# With verbose output
uv run pytest -v

# Coverage report in terminal
uv run pytest --cov-report=term-missing
```

### Lint and typecheck

```bash
uv run ruff check .
uv run pyrefly check
```

Pre-commit order: `ruff → pyrefly → pytest`

---

## Configuration reference

All values in `config.toml` can be overridden by environment variables using double-underscore notation:

| Config key | Environment variable |
|---|---|
| `openai.api_key` | `OPENAI__API_KEY` |
| `server.api_key` | `SERVER__API_KEY` |
| `ingestion.poll_interval_minutes` | `INGESTION__POLL_INTERVAL_MINUTES` |
| `database.url` | `DATABASE__URL` |

The app fails fast at startup if required fields are missing.

---

## Enrichment scores

Every article receives five normalized scores from GPT (0.0 – 1.0):

| Score | Meaning |
|---|---|
| `urgency_score` | How time-sensitive or breaking the story is |
| `anxiety_score` | How much fear or worry the story carries |
| `optimism_score` | How much hope or positive momentum it conveys |
| `conflict_score` | Degree of confrontation, tension, or opposition |
| `stability_score` | Degree of order, resolution, or calm |

These scores power the mood and trend tools.

---

## Regions

The system recognizes eight regions:

`Africa` · `Asia` · `Europe` · `Latin America` · `Middle East` · `North America` · `Oceania` · `Global`

Region is inferred from article metadata where available, and from GPT enrichment when not.

---

## What is coming next (Phase 2)

See `PHASE2.md` for the full deferred backlog. Highlights:

- Semantic search via `text-embedding-3-large` embeddings (table exists, unpopulated)
- PostgreSQL + pgvector upgrade path (Alembic migrations ready)
- Redis-backed circuit breaker
- Sentry / Datadog observability adapter
- Multilingual support
- Additional news sources (Reuters, Al Jazeera, AP)
- Narrative timeline visualization

All Phase 2 interfaces are pre-designed — no core rewrites needed to activate them.

---

## License

Personal / non-commercial project.
