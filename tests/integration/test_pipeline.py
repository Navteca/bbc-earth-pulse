"""Integration test: full pipeline fake feed → DB → enrichment → MCP tool response."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from earth_pulse.circuit_breaker import InMemoryCircuitBreakerAdapter
from earth_pulse.config import (
    DatabaseSettings,
    IngestionSettings,
    OpenAISettings,
    ServerSettings,
    Settings,
    SourceSettings,
    SourcesSettings,
)
from earth_pulse.db import SQLiteAdapter
from earth_pulse.enrichment.worker import EnrichmentWorker
from earth_pulse.ingestion.pipeline import IngestionPipeline
from earth_pulse.ingestion.ports import FeedSourcePort
from earth_pulse.models import Article
from earth_pulse.observability import JSONLoggingAdapter
from earth_pulse.server import create_app
from earth_pulse.temporal.synthesis import SynthesisEngine

_VALID_ENRICHMENT = {
    "emotion": "anxiety",
    "topics": ["AI", "labor"],
    "narratives": ["disruption"],
    "region": "Global",
    "urgency_score": 0.8,
    "anxiety_score": 0.7,
    "optimism_score": 0.2,
    "conflict_score": 0.5,
    "stability_score": 0.3,
}


class FakeSource(FeedSourcePort):
    source_name = "fake"

    def __init__(self, articles):
        self._articles = articles

    async def fetch(self):
        return self._articles


def _make_article(i: int) -> Article:
    return Article.build(
        title=f"AI is transforming labor markets {i}",
        url=f"https://example.com/article-{i}",
        source="bbc_rss",
        published_at=datetime.now(tz=UTC),
        summary="AI disruption summary.",
        region="Global",
    )


@pytest.fixture
def full_db():
    db = SQLiteAdapter("sqlite:///:memory:")
    db.migrate()
    return db


@pytest.fixture
def full_settings():
    return Settings(
        openai=OpenAISettings(api_key="sk-test", chat_model="gpt-test"),
        server=ServerSettings(api_key="integration-key"),
        ingestion=IngestionSettings(poll_interval_minutes=15),
        database=DatabaseSettings(url="sqlite:///:memory:"),
        sources=SourcesSettings(
            bbc_rss=SourceSettings(enabled=True),
            bbc_unofficial=SourceSettings(enabled=True),
        ),
    )


class TestFullPipeline:
    async def test_ingest_enrich_query_mood(self, full_db, full_settings):
        # Step 1: Ingest
        articles = [_make_article(i) for i in range(3)]
        source = FakeSource(articles)
        logger = JSONLoggingAdapter()
        cb = InMemoryCircuitBreakerAdapter()
        pipeline = IngestionPipeline([source], full_db, cb, logger)
        result = await pipeline.run()
        assert result["fake"] == 3

        # Step 2: Enrich
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.choices = [MagicMock()]
        mock_resp.choices[0].message.content = json.dumps(_VALID_ENRICHMENT)
        mock_client.chat = MagicMock()
        mock_client.chat.completions = MagicMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_resp)

        worker = EnrichmentWorker(full_db, mock_client, "gpt-test", logger)
        enriched = await worker.run_batch()
        assert enriched == 3

        # Step 3: MCP tool via FastAPI
        mock_synthesis_client = MagicMock()
        mock_synth_resp = MagicMock()
        mock_synth_resp.choices = [MagicMock()]
        mock_synth_resp.choices[0].message.content = (
            "Global anxiety is rising due to AI disruption."
        )
        mock_synthesis_client.chat = MagicMock()
        mock_synthesis_client.chat.completions = MagicMock()
        mock_synthesis_client.chat.completions.create = AsyncMock(return_value=mock_synth_resp)

        synthesis = SynthesisEngine(mock_synthesis_client, "gpt-test")
        app = create_app(full_settings, full_db, synthesis)

        with TestClient(app, raise_server_exceptions=True) as client:
            response = client.get("/health")
            assert response.status_code == 200

    async def test_dedup_prevents_double_ingest(self, full_db, full_settings):
        article = _make_article(99)
        source = FakeSource([article, article])
        logger = JSONLoggingAdapter()
        cb = InMemoryCircuitBreakerAdapter()
        pipeline = IngestionPipeline([source], full_db, cb, logger)
        result = await pipeline.run()
        assert result["fake"] == 1  # Only one stored despite two identical
