"""Tests for server_entry.py — main() entrypoint."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from earth_pulse.config import (
    DatabaseSettings,
    IngestionSettings,
    OpenAISettings,
    ServerSettings,
    Settings,
    SourceSettings,
    SourcesSettings,
)


def _make_settings() -> Settings:
    return Settings(
        openai=OpenAISettings(api_key="sk-test", chat_model="gpt-test"),
        server=ServerSettings(api_key="srv-key", host="127.0.0.1", port=9999),
        ingestion=IngestionSettings(poll_interval_minutes=15),
        database=DatabaseSettings(url="sqlite:///:memory:"),
        sources=SourcesSettings(
            bbc_rss=SourceSettings(enabled=True),
            bbc_unofficial=SourceSettings(enabled=True),
        ),
    )


class TestServerEntryMain:
    def test_main_calls_uvicorn_run(self):
        settings = _make_settings()

        with (
            patch("earth_pulse.server_entry.load_settings", return_value=settings),
            patch("earth_pulse.server_entry.SQLiteAdapter") as mock_db_cls,
            patch("earth_pulse.server_entry.AsyncOpenAI"),
            patch("earth_pulse.server_entry.create_app", return_value=MagicMock()),
            patch("earth_pulse.server_entry.SynthesisEngine"),
            patch("earth_pulse.server_entry.uvicorn.run") as mock_run,
        ):
            mock_db_cls.return_value.migrate = MagicMock()
            from earth_pulse.server_entry import main

            main()

        mock_run.assert_called_once()
        call_kwargs = mock_run.call_args
        assert call_kwargs.kwargs.get("host") == "127.0.0.1" or (
            len(call_kwargs.args) > 1 and call_kwargs.args[1] == "127.0.0.1"
        )
