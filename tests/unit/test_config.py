"""Unit tests for config loading."""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from earth_pulse.config import load_settings


class TestLoadSettings:
    def test_fails_without_openai_key(self, tmp_path):
        with pytest.raises(ValueError, match="openai.api_key"):
            load_settings(config_path=tmp_path / "missing.toml")

    def test_loads_without_server_key(self, tmp_path):
        # server.api_key is optional in load_settings; validation happens in create_app
        cfg = tmp_path / "config.toml"
        cfg.write_text('[openai]\napi_key = "sk-test"\n')
        settings = load_settings(config_path=cfg)
        assert settings.server.api_key == ""

    def test_loads_from_toml(self, tmp_path):
        cfg = tmp_path / "config.toml"
        cfg.write_text(
            '[openai]\napi_key = "sk-test"\nchat_model = "gpt-4"\n'
            '[server]\napi_key = "srv-key"\n'
        )
        settings = load_settings(config_path=cfg)
        assert settings.openai.api_key == "sk-test"
        assert settings.openai.chat_model == "gpt-4"
        assert settings.server.api_key == "srv-key"

    def test_env_var_overrides_toml(self, tmp_path):
        cfg = tmp_path / "config.toml"
        cfg.write_text('[openai]\napi_key = "sk-toml"\n[server]\napi_key = "srv-toml"\n')
        with patch.dict(os.environ, {"OPENAI__API_KEY": "sk-env"}):
            settings = load_settings(config_path=cfg)
        assert settings.openai.api_key == "sk-env"

    def test_env_var_provides_openai_key_without_toml(self, tmp_path):
        with patch.dict(os.environ, {"OPENAI__API_KEY": "sk-env", "SERVER__API_KEY": "srv-env"}):
            settings = load_settings(config_path=tmp_path / "missing.toml")
        assert settings.openai.api_key == "sk-env"
        assert settings.server.api_key == "srv-env"

    def test_defaults_applied(self, tmp_path):
        cfg = tmp_path / "config.toml"
        cfg.write_text('[openai]\napi_key = "sk-test"\n[server]\napi_key = "srv-key"\n')
        settings = load_settings(config_path=cfg)
        assert settings.ingestion.poll_interval_minutes == 15
        assert settings.database.url == "sqlite:///earth_pulse.db"
        assert settings.sources.bbc_rss.enabled is True

    def test_source_disabled_via_toml(self, tmp_path):
        cfg = tmp_path / "config.toml"
        cfg.write_text(
            '[openai]\napi_key = "sk-test"\n[server]\napi_key = "srv-key"\n'
            '[sources.bbc_unofficial]\nenabled = false\n'
        )
        settings = load_settings(config_path=cfg)
        assert settings.sources.bbc_unofficial.enabled is False

    def test_server_port_default(self, tmp_path):
        cfg = tmp_path / "config.toml"
        cfg.write_text('[openai]\napi_key = "sk-test"\n[server]\napi_key = "srv-key"\n')
        settings = load_settings(config_path=cfg)
        assert settings.server.port == 8000

    def test_default_config_path_used_when_none(self, tmp_path, monkeypatch):
        """Covers the config_path is None branch (default path = config.toml)."""

        monkeypatch.chdir(tmp_path)
        cfg = tmp_path / "config.toml"
        cfg.write_text('[openai]\napi_key = "sk-test"\n[server]\napi_key = "srv-key"\n')
        settings = load_settings()
        assert settings.openai.api_key == "sk-test"

    def test_source_enabled_via_env(self, tmp_path):
        """Covers the SOURCES__X__ENABLED env var path."""
        cfg = tmp_path / "config.toml"
        cfg.write_text('[openai]\napi_key = "sk-test"\n[server]\napi_key = "srv-key"\n')
        with patch.dict(os.environ, {"SOURCES__BBC_RSS__ENABLED": "false"}):
            settings = load_settings(config_path=cfg)
        assert settings.sources.bbc_rss.enabled is False
