# Phase 2 — Earth Pulse Intelligence Expansion

This document is the authoritative backlog for Phase 2 features. All items here were deliberately deferred from MVP. The codebase is structured (ports-and-adapters) so each item below slots in via a new adapter or extension — no core rewrites required.

---

## 1. Embeddings + Semantic Search

**What:** Generate `text-embedding-3-large` (or `text-embedding-3-small`) vectors for every enriched article and store them in the `embeddings` table.

**Why deferred:** Not needed for MVP SQL-aggregation-based tools. Adds cost and complexity with no user-visible benefit until semantic queries are required.

**How to pick up:**
- `embeddings` table already exists in schema (unpopulated)
- Add `EmbeddingPort` interface in `earth_pulse/enrichment/ports.py`
- Implement `OpenAIEmbeddingAdapter`
- Add embedding generation as a third pipeline stage after enrichment
- Wire into `query_timeline` for semantic similarity ranking

**Config addition needed:**
```toml
[openai]
embedding_model = "text-embedding-3-large"
```

---

## 2. PostgreSQL + pgvector

**What:** Replace SQLite with PostgreSQL as the production database, with pgvector extension for native vector similarity search.

**Why deferred:** SQLite + WAL is sufficient for MVP single-node deployment.

**How to pick up:**
- `DatabasePort` interface already abstracts all DB access
- Write `PostgreSQLAdapter` satisfying `DatabasePort`
- Add Alembic migration scripts in `earth_pulse/db/migrations/`
- Add `db` service to `docker-compose.yml` (already stubbed as production profile)
- Switch `DATABASE_URL` in config — zero business logic changes

**Dependencies:** Requires embeddings (item 1) to be meaningful with pgvector.

---

## 3. Celery + Redis Scheduler

**What:** Replace APScheduler with Celery + Redis for distributed task scheduling, better observability, and horizontal scaling.

**Why deferred:** APScheduler is sufficient for single-node MVP.

**How to pick up:**
- `SchedulerPort` interface already abstracts all scheduling
- Write `CeleryAdapter` satisfying `SchedulerPort`
- Add `redis` and update `worker` service in `docker-compose.yml`
- No changes to ingestion or enrichment logic

---

## 4. External Monitoring (Sentry / Datadog)

**What:** Replace stdlib JSON logging with a production observability platform.

**Why deferred:** Structured JSON logs are sufficient for MVP.

**How to pick up:**
- `ObservabilityPort` interface already abstracts logging and alerting
- Write `SentryAdapter` or `DatadogAdapter` satisfying the port
- Add DSN/API key to `config.toml`
- No changes to business logic

---

## 5. Redis-backed Circuit Breaker

**What:** Replace in-memory circuit breaker with a Redis-backed one so state persists across worker restarts.

**Why deferred:** In-memory is sufficient for MVP single-process worker.

**How to pick up:**
- `CircuitBreakerPort` interface already abstracts circuit breaker state
- Write `RedisCircuitBreakerAdapter`
- Requires Redis (add to Docker Compose alongside Celery if picked up together)

---

## 6. Narrative Timeline Semantic Enhancement

**What:** Enhance `query_timeline` with embedding-based similarity to surface semantically related articles beyond keyword matching.

**Why deferred:** Requires embeddings (item 1) and pgvector (item 2).

**How to pick up:**
- `query_timeline` tool already exists with SQL-based implementation
- Add semantic re-ranking layer once embeddings are populated
- No interface changes — same tool signature, richer results

---

## 7. Frontend — Civilization Dashboard

**What:** Next.js + Tailwind + D3.js dashboard with:
- Live global mood indicator
- Emotional heatmap by region
- Narrative acceleration chart
- Topic trend sparklines

**How to pick up:**
- MCP tools already return structured JSON suitable for direct UI consumption
- Add a `frontend/` directory at repo root
- Dashboard calls the 3 MCP tools via HTTP Streamable

---

## 8. Emotional Globe Visualization

**What:** Interactive 3D globe (Three.js or D3 geo) showing:
- Emotional hotspots by region
- Animated intensity over time
- Click-to-drill into regional mood

**Dependency:** Requires frontend (item 7).

---

## 9. Audio Narration

**What:** AI-generated daily audio briefing:
> "Today on Earth…"

**How to pick up:**
- Use OpenAI TTS API (`tts-1` or `tts-1-hd`)
- Add `NarrationPort` interface
- Trigger once per day via scheduler
- Serve audio file via FastAPI static route

**Config addition needed:**
```toml
[narration]
enabled = false
voice = "onyx"
```

---

## 10. Multi-Source Expansion

**What:** Add additional news sources beyond BBC RSS and unofficial BBC API:
- Reuters RSS feeds (free, public)
- Al Jazeera RSS feeds (free, public)
- AP News RSS feeds (free, public)
- Financial Times (requires subscription)
- Scientific journals (arXiv RSS — free)

**How to pick up:**
- Each new source implements `FeedSourcePort`
- Add source config block in `config.toml`
- No changes to normalization, enrichment, or MCP layers

---

## 11. Multilingual Enrichment

**What:** Enrich non-English articles (the unofficial BBC API supports 31 languages). Requires translation step before GPT enrichment, or use of multilingual GPT prompts.

**Why deferred:** MVP is English-only. `language` field already stored on `Article` model.

**How to pick up:**
- Filter enrichment pipeline by `language == "en"` already in place for MVP
- Remove filter and add translation step (OpenAI can translate inline in the enrichment prompt)
- No schema changes needed

---

## 12. Re-enrichment on Model Upgrade

**What:** When `chat_model` changes in config, trigger a re-enrichment pass over existing articles to refresh scores and classifications with the new model.

**How to pick up:**
- Raw articles are preserved in DB (never deleted after enrichment)
- Add a `reenrich` CLI command: `uv run python -m earth_pulse.enrichment.reenrich --since <date>`
- Mark existing enrichments as `stale` before re-running
