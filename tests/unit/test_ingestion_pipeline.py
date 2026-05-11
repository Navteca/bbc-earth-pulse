"""Unit tests for ingestion pipeline."""

from __future__ import annotations

from datetime import UTC, datetime

from earth_pulse.ingestion.pipeline import IngestionPipeline
from earth_pulse.ingestion.ports import FeedSourcePort
from earth_pulse.models import Article


def _make_article(url: str, title: str = "Title") -> Article:
    return Article.build(
        title=title,
        url=url,
        source="bbc_rss",
        published_at=datetime.now(tz=UTC),
    )


class FakeSource(FeedSourcePort):
    source_name = "fake"

    def __init__(self, articles=None, raises=False):
        self._articles = articles or []
        self._raises = raises

    async def fetch(self):
        if self._raises:
            raise ConnectionError("Network down")
        return self._articles


class TestIngestionPipeline:
    async def test_saves_new_articles(self, db, circuit_breaker, logger):
        articles = [
            _make_article("https://a.com/1", title="Article One"),
            _make_article("https://a.com/2", title="Article Two"),
        ]
        source = FakeSource(articles=articles)
        pipeline = IngestionPipeline([source], db, circuit_breaker, logger)
        result = await pipeline.run()
        assert result["fake"] == 2

    async def test_deduplicates_articles(self, db, circuit_breaker, logger):
        a = _make_article("https://a.com/1")
        db.save_article(a)
        source = FakeSource(articles=[a])
        pipeline = IngestionPipeline([source], db, circuit_breaker, logger)
        result = await pipeline.run()
        assert result["fake"] == 0

    async def test_skips_non_english_articles(self, db, circuit_breaker, logger):
        a = _make_article("https://a.com/1")
        a.language = "fr"
        source = FakeSource(articles=[a])
        pipeline = IngestionPipeline([source], db, circuit_breaker, logger)
        result = await pipeline.run()
        assert result["fake"] == 0

    async def test_records_failure_on_source_error(self, db, circuit_breaker, logger):
        source = FakeSource(raises=True)
        pipeline = IngestionPipeline([source], db, circuit_breaker, logger)
        result = await pipeline.run()
        assert result["fake"] == 0
        assert circuit_breaker.status("fake").failure_count == 1

    async def test_skips_open_circuit(self, db, circuit_breaker, logger):
        for _ in range(3):
            circuit_breaker.record_failure("fake")
        source = FakeSource(articles=[_make_article("https://a.com/99")])
        pipeline = IngestionPipeline([source], db, circuit_breaker, logger)
        result = await pipeline.run()
        assert result["fake"] == 0

    async def test_records_success_on_no_error(self, db, circuit_breaker, logger):
        source = FakeSource(articles=[])
        pipeline = IngestionPipeline([source], db, circuit_breaker, logger)
        await pipeline.run()
        assert circuit_breaker.status("fake").failure_count == 0
