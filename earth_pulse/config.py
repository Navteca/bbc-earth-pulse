"""
Typed settings loaded from config.toml via tomllib.
Environment variables override config values using double-underscore notation:
  OPENAI__API_KEY, SERVER__API_KEY, etc.
App fails fast at startup if required fields are missing.
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class OpenAISettings:
    api_key: str
    chat_model: str = "gpt-5.4"
    embedding_model: str = "text-embedding-3-large"


@dataclass
class ServerSettings:
    api_key: str
    host: str = "0.0.0.0"
    port: int = 8000


@dataclass
class IngestionSettings:
    poll_interval_minutes: int = 15


@dataclass
class DatabaseSettings:
    url: str = "sqlite:///earth_pulse.db"


@dataclass
class SourceSettings:
    enabled: bool = True
    api_key: str = ""


@dataclass
class SourcesSettings:
    bbc_rss: SourceSettings = field(default_factory=SourceSettings)
    bbc_unofficial: SourceSettings = field(default_factory=SourceSettings)


@dataclass
class Settings:
    openai: OpenAISettings
    server: ServerSettings
    ingestion: IngestionSettings
    database: DatabaseSettings
    sources: SourcesSettings


def _env(key: str, default: str | None = None) -> str | None:
    """Read env var using double-underscore notation.

    Example: OPENAI__API_KEY → openai.api_key
    """
    return os.environ.get(key, default)


def load_settings(config_path: Path | None = None) -> Settings:
    """Load settings from config.toml, overridden by environment variables."""
    if config_path is None:
        config_path = Path("config.toml")

    raw: dict = {}
    if config_path.exists():
        with open(config_path, "rb") as f:
            raw = tomllib.load(f)

    # --- openai ---
    openai_raw = raw.get("openai", {})
    openai_api_key = _env("OPENAI__API_KEY") or openai_raw.get("api_key", "")
    if not openai_api_key:
        raise ValueError(
            "openai.api_key is required. "
            "Set it in config.toml or OPENAI__API_KEY env var."
        )
    openai_settings = OpenAISettings(
        api_key=openai_api_key,
        chat_model=(
            _env("OPENAI__CHAT_MODEL") or openai_raw.get("chat_model", "gpt-5.4")
        ),
        embedding_model=(
            _env("OPENAI__EMBEDDING_MODEL")
            or openai_raw.get("embedding_model", "text-embedding-3-large")
        ),
    )

    # --- server ---
    server_raw = raw.get("server", {})
    server_api_key = _env("SERVER__API_KEY") or server_raw.get("api_key", "")
    server_settings = ServerSettings(
        api_key=server_api_key,
        host=_env("SERVER__HOST") or server_raw.get("host", "0.0.0.0"),
        port=int(_env("SERVER__PORT") or server_raw.get("port", 8000)),
    )

    # --- ingestion ---
    ingestion_raw = raw.get("ingestion", {})
    ingestion_settings = IngestionSettings(
        poll_interval_minutes=int(
            _env("INGESTION__POLL_INTERVAL_MINUTES")
            or ingestion_raw.get("poll_interval_minutes", 15)
        ),
    )

    # --- database ---
    database_raw = raw.get("database", {})
    database_settings = DatabaseSettings(
        url=(
            _env("DATABASE__URL")
            or database_raw.get("url", "sqlite:///earth_pulse.db")
        ),
    )

    # --- sources ---
    sources_raw = raw.get("sources", {})

    def _source(name: str) -> SourceSettings:
        s = sources_raw.get(name, {})
        enabled_env = _env(f"SOURCES__{name.upper()}__ENABLED")
        enabled = (
            (enabled_env.lower() == "true")
            if enabled_env is not None
            else s.get("enabled", True)
        )
        api_key = _env(f"SOURCES__{name.upper()}__API_KEY") or s.get("api_key", "")
        return SourceSettings(enabled=enabled, api_key=api_key)

    sources_settings = SourcesSettings(
        bbc_rss=_source("bbc_rss"),
        bbc_unofficial=_source("bbc_unofficial"),
    )

    return Settings(
        openai=openai_settings,
        server=server_settings,
        ingestion=ingestion_settings,
        database=database_settings,
        sources=sources_settings,
    )
