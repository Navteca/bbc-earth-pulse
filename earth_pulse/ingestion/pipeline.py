"""
Ingestion pipeline — orchestrates fetch → dedup → store for all enabled sources.
"""

from __future__ import annotations

from earth_pulse.circuit_breaker import CircuitBreakerPort
from earth_pulse.db import DatabasePort
from earth_pulse.ingestion.ports import FeedSourcePort
from earth_pulse.observability import ObservabilityPort


class IngestionPipeline:
    def __init__(
        self,
        sources: list[FeedSourcePort],
        db: DatabasePort,
        circuit_breaker: CircuitBreakerPort,
        logger: ObservabilityPort,
    ) -> None:
        self._sources = sources
        self._db = db
        self._cb = circuit_breaker
        self._logger = logger

    async def run(self) -> dict[str, int]:
        """Run one ingestion cycle. Returns per-source counts of new articles stored."""
        results: dict[str, int] = {}
        for source in self._sources:
            name = source.source_name
            if self._cb.is_open(name):
                self._logger.warning(
                    "ingestion.source.skipped",
                    source=name,
                    reason="circuit_open",
                )
                results[name] = 0
                continue

            try:
                articles = await source.fetch()
                new_count = 0
                for article in articles:
                    if article.language != "en":
                        continue
                    if self._db.article_exists(article.url_hash, article.title_hash):
                        continue
                    self._db.save_article(article)
                    new_count += 1

                self._cb.record_success(name)
                self._logger.info(
                    "ingestion.source.done",
                    source=name,
                    fetched=len(articles),
                    new=new_count,
                )
                results[name] = new_count

            except Exception as exc:
                self._cb.record_failure(name)
                self._logger.error(
                    "ingestion.source.error",
                    source=name,
                    error=str(exc),
                )
                results[name] = 0

        return results
