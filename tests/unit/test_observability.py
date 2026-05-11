"""Unit tests for observability / JSON logging adapter."""

from __future__ import annotations

import json
import logging

from earth_pulse.observability import JSONLoggingAdapter


class TestJSONLoggingAdapter:
    def test_info_logs_json(self, capsys):
        logger = JSONLoggingAdapter(name="test_info_v2", level=logging.DEBUG)
        logger.info("test.event", key="value")
        out = capsys.readouterr().out.strip()
        data = json.loads(out)
        assert data["event"] == "test.event"
        assert data["key"] == "value"
        assert data["level"] == "INFO"
        assert "ts" in data

    def test_warning_logs_json(self, capsys):
        logger = JSONLoggingAdapter(name="test_warn_v2", level=logging.DEBUG)
        logger.warning("warn.event")
        out = capsys.readouterr().out.strip()
        data = json.loads(out)
        assert data["level"] == "WARNING"

    def test_error_logs_json(self, capsys):
        logger = JSONLoggingAdapter(name="test_err_v2", level=logging.DEBUG)
        logger.error("err.event", error="something bad")
        out = capsys.readouterr().out.strip()
        data = json.loads(out)
        assert data["level"] == "ERROR"
        assert data["error"] == "something bad"

    def test_debug_logs_json(self, capsys):
        logger = JSONLoggingAdapter(name="test_debug_v2", level=logging.DEBUG)
        logger.debug("debug.event")
        out = capsys.readouterr().out.strip()
        data = json.loads(out)
        assert data["level"] == "DEBUG"
