"""Shared fixtures for all tests."""

from __future__ import annotations

import pytest

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
from earth_pulse.observability import JSONLoggingAdapter


@pytest.fixture
def settings() -> Settings:
    return Settings(
        openai=OpenAISettings(api_key="test-key", chat_model="gpt-test"),
        server=ServerSettings(api_key="test-server-key"),
        ingestion=IngestionSettings(poll_interval_minutes=15),
        database=DatabaseSettings(url="sqlite:///:memory:"),
        sources=SourcesSettings(
            bbc_rss=SourceSettings(enabled=True),
            bbc_unofficial=SourceSettings(enabled=True),
        ),
    )


@pytest.fixture
def db() -> SQLiteAdapter:
    adapter = SQLiteAdapter("sqlite:///:memory:")
    adapter.migrate()
    return adapter


@pytest.fixture
def circuit_breaker() -> InMemoryCircuitBreakerAdapter:
    return InMemoryCircuitBreakerAdapter()


@pytest.fixture
def logger() -> JSONLoggingAdapter:
    return JSONLoggingAdapter()
