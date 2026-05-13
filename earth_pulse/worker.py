"""
Worker entrypoint — ingestion + enrichment scheduler.
Usage: uv run python -m earth_pulse.worker
"""

from __future__ import annotations

import asyncio

from openai import AsyncOpenAI

from earth_pulse.circuit_breaker import InMemoryCircuitBreakerAdapter
from earth_pulse.config import Settings, load_settings
from earth_pulse.db import SQLiteAdapter
from earth_pulse.enrichment import EnrichmentWorker
from earth_pulse.ingestion import (
    BBCRSSAdapter,
    BBCUnofficialAdapter,
    IngestionPipeline,
)
from earth_pulse.ingestion.ports import FeedSourcePort
from earth_pulse.observability import JSONLoggingAdapter
from earth_pulse.scheduler import APSchedulerAdapter

BBC_UNOFFICIAL_MIN_MINUTES = 30


def build_sources(settings: Settings) -> list[FeedSourcePort]:
    sources: list[FeedSourcePort] = []
    if settings.sources.bbc_rss.enabled:
        sources.append(BBCRSSAdapter())
    if settings.sources.bbc_unofficial.enabled:
        sources.append(BBCUnofficialAdapter())
    return sources


async def main() -> None:
    settings = load_settings()
    logger = JSONLoggingAdapter()
    db = SQLiteAdapter(settings.database.url)
    db.migrate()

    circuit_breaker = InMemoryCircuitBreakerAdapter()
    openai_client = AsyncOpenAI(api_key=settings.openai.api_key)

    sources = build_sources(settings)
    pipeline = IngestionPipeline(sources, db, circuit_breaker, logger)
    enrichment_worker = EnrichmentWorker(db, openai_client, settings.openai.chat_model, logger)

    scheduler = APSchedulerAdapter()

    # Ingestion job — respect BBC unofficial 30-min floor.
    # If unofficial source is enabled and configured poll < floor, raise to floor.
    poll_minutes = settings.ingestion.poll_interval_minutes
    effective_minutes = poll_minutes
    if settings.sources.bbc_unofficial.enabled:
        effective_minutes = max(poll_minutes, BBC_UNOFFICIAL_MIN_MINUTES)
        if effective_minutes != poll_minutes:
            logger.info(
                "worker.unofficial.floor",
                configured=poll_minutes,
                effective=effective_minutes,
            )

    async def run_ingestion() -> None:
        await pipeline.run()

    scheduler.add_job(run_ingestion, interval_minutes=effective_minutes, job_id="ingestion")

    # Enrichment job — runs every 5 minutes to process newly ingested articles
    async def run_enrichment() -> None:
        await enrichment_worker.run_batch()

    scheduler.add_job(run_enrichment, interval_minutes=5, job_id="enrichment")

    scheduler.start()
    logger.info("worker.started", poll_minutes=effective_minutes)

    # Run initial cycle immediately
    await run_ingestion()
    await run_enrichment()

    try:
        await asyncio.Event().wait()
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()
        logger.info("worker.stopped")


if __name__ == "__main__":  # pragma: no cover
    asyncio.run(main())
