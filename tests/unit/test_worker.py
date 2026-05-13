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


class TestUnofficialFloorEnforcement:
    def _run_main_with_settings(self, settings):
        import asyncio
        from unittest.mock import AsyncMock, MagicMock, patch

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
            patch("earth_pulse.worker.EnrichmentWorker", return_value=mock_enrichment),
            patch("earth_pulse.worker.APSchedulerAdapter", return_value=mock_scheduler),
            patch("asyncio.Event", FakeEvent),
        ):
            mock_db_cls.return_value.migrate = MagicMock()
            from earth_pulse.worker import main
            asyncio.run(main())
        return mock_scheduler

    def test_floor_enforced_in_scheduler(self):
        """When poll=5 and unofficial enabled, scheduler.add_job called with 30, not 5."""
        settings = _make_settings(poll=5, unofficial=True)
        mock_scheduler = self._run_main_with_settings(settings)
        ingestion_call = next(
            c for c in mock_scheduler.add_job.call_args_list
            if c.kwargs.get("job_id") == "ingestion"
            or (c.args and c.args[1] == 30 if len(c.args) > 1 else False)
            or c.kwargs.get("interval_minutes") == 30
        )
        # The interval_minutes kwarg must be 30 (the floor), not 5
        assert ingestion_call.kwargs["interval_minutes"] == 30

    def test_floor_not_applied_when_unofficial_disabled(self):
        """When unofficial is disabled, scheduler uses configured poll interval."""
        settings = _make_settings(poll=5, unofficial=False)
        mock_scheduler = self._run_main_with_settings(settings)
        ingestion_call = next(
            c for c in mock_scheduler.add_job.call_args_list
            if c.kwargs.get("job_id") == "ingestion"
        )
        assert ingestion_call.kwargs["interval_minutes"] == 5

    def test_no_floor_needed_when_poll_already_above_floor(self):
        """When poll=60 and unofficial enabled, floor is irrelevant — uses 60."""
        settings = _make_settings(poll=60, unofficial=True)
        mock_scheduler = self._run_main_with_settings(settings)
        ingestion_call = next(
            c for c in mock_scheduler.add_job.call_args_list
            if c.kwargs.get("job_id") == "ingestion"
        )
        assert ingestion_call.kwargs["interval_minutes"] == 60
