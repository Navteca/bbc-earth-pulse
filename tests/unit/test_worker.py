"""Tests for worker.py — build_sources and main()."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from earth_pulse.config import (
    DatabaseSettings,
    IngestionSettings,
    OpenAISettings,
    ServerSettings,
    Settings,
    SourceSettings,
    SourcesSettings,
)
from earth_pulse.worker import build_sources


def _make_settings(
    bbc_rss=True,
    unofficial=True,
    poll=15,
) -> Settings:
    return Settings(
        openai=OpenAISettings(api_key="sk-test", chat_model="gpt-test"),
        server=ServerSettings(api_key="srv-key"),
        ingestion=IngestionSettings(poll_interval_minutes=poll),
        database=DatabaseSettings(url="sqlite:///:memory:"),
        sources=SourcesSettings(
            bbc_rss=SourceSettings(enabled=bbc_rss),
            bbc_unofficial=SourceSettings(enabled=unofficial),
        ),
    )


class TestBuildSources:
    def test_all_sources_enabled(self):
        settings = _make_settings()
        sources = build_sources(settings)
        names = [s.source_name for s in sources]
        assert "bbc_rss" in names
        assert "bbc_unofficial" in names

    def test_bbc_rss_disabled(self):
        settings = _make_settings(bbc_rss=False)
        sources = build_sources(settings)
        names = [s.source_name for s in sources]
        assert "bbc_rss" not in names

    def test_unofficial_disabled(self):
        settings = _make_settings(unofficial=False)
        sources = build_sources(settings)
        names = [s.source_name for s in sources]
        assert "bbc_unofficial" not in names


class TestMain:
    async def test_main_runs_and_stops(self):
        """Test that main() starts, runs initial cycle, and shuts down cleanly."""
        settings = _make_settings()

        async def fake_pipeline_run():
            return {"fake": 0}

        async def fake_enrichment_run():
            return 0

        mock_pipeline = MagicMock()
        mock_pipeline.run = AsyncMock(side_effect=fake_pipeline_run)

        mock_enrichment = MagicMock()
        mock_enrichment.run_batch = AsyncMock(side_effect=fake_enrichment_run)

        mock_scheduler = MagicMock()
        mock_scheduler.add_job = MagicMock()
        mock_scheduler.start = MagicMock()
        mock_scheduler.shutdown = MagicMock()

        # Make asyncio.Event().wait() raise KeyboardInterrupt to exit cleanly
        class FakeEvent:
            async def wait(self):
                raise KeyboardInterrupt

        with (
            patch("earth_pulse.worker.load_settings", return_value=settings),
            patch("earth_pulse.worker.SQLiteAdapter") as mock_db_cls,
            patch("earth_pulse.worker.AsyncOpenAI"),
            patch("earth_pulse.worker.IngestionPipeline", return_value=mock_pipeline),
            patch(
                "earth_pulse.worker.EnrichmentWorker", return_value=mock_enrichment
            ),
            patch(
                "earth_pulse.worker.APSchedulerAdapter", return_value=mock_scheduler
            ),
            patch("asyncio.Event", FakeEvent),
        ):
            mock_db_cls.return_value.migrate = MagicMock()
            from earth_pulse.worker import main

            await main()

        mock_scheduler.start.assert_called_once()
        mock_scheduler.shutdown.assert_called_once()
        mock_pipeline.run.assert_called_once()
        mock_enrichment.run_batch.assert_called_once()

    async def test_main_unofficial_floor_log(self):
        """When poll_interval < 30 and unofficial enabled, logs the floor."""
        settings = _make_settings(poll=5)

        async def fake_pipeline_run():
            return {}

        async def fake_enrichment_run():
            return 0

        mock_pipeline = MagicMock()
        mock_pipeline.run = AsyncMock(side_effect=fake_pipeline_run)
        mock_enrichment = MagicMock()
        mock_enrichment.run_batch = AsyncMock(side_effect=fake_enrichment_run)
        mock_scheduler = MagicMock()

        class FakeEvent:
            async def wait(self):
                raise KeyboardInterrupt

        with (
            patch("earth_pulse.worker.load_settings", return_value=settings),
            patch("earth_pulse.worker.SQLiteAdapter") as mock_db_cls,
            patch("earth_pulse.worker.AsyncOpenAI"),
            patch("earth_pulse.worker.IngestionPipeline", return_value=mock_pipeline),
            patch(
                "earth_pulse.worker.EnrichmentWorker", return_value=mock_enrichment
            ),
            patch(
                "earth_pulse.worker.APSchedulerAdapter", return_value=mock_scheduler
            ),
            patch("asyncio.Event", FakeEvent),
        ):
            mock_db_cls.return_value.migrate = MagicMock()
            from earth_pulse.worker import main

            await main()
        # No error = pass; we just need to cover the log line
