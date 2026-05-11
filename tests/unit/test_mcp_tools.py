"""Tests for mcp/tools.py — build_mcp_server and tool handlers."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

from mcp.types import CallToolRequest, CallToolRequestParams, ListToolsRequest

from earth_pulse.db import SQLiteAdapter
from earth_pulse.mcp.tools import (
    _query_mood,
    _query_timeline,
    _query_trends,
    build_mcp_server,
)
from earth_pulse.models import Article, Enrichment
from earth_pulse.temporal.synthesis import SynthesisEngine


def _make_synthesis(text: str = "Synthesis.") -> SynthesisEngine:
    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.choices = [MagicMock()]
    mock_resp.choices[0].message.content = text
    mock_client.chat = MagicMock()
    mock_client.chat.completions = MagicMock()
    mock_client.chat.completions.create = AsyncMock(return_value=mock_resp)
    return SynthesisEngine(mock_client, "gpt-test")


def _populate_db(db: SQLiteAdapter, n: int = 2) -> None:
    for i in range(n):
        article = Article.build(
            title=f"Article {i}",
            url=f"https://example.com/mcp/{i}",
            source="bbc_rss",
            published_at=datetime.now(tz=UTC),
            region="Global",
        )
        db.save_article(article)
        enrichment = Enrichment(
            article_id=article.id,
            emotion="anxiety",
            topics=["climate"],
            narratives=["crisis"],
            region="Global",
            urgency_score=0.7,
            anxiety_score=0.6,
            optimism_score=0.3,
            conflict_score=0.4,
            stability_score=0.2,
            enriched_at=datetime.now(tz=UTC),
        )
        db.save_enrichment(enrichment)


def _db() -> SQLiteAdapter:
    db = SQLiteAdapter("sqlite:///:memory:")
    db.migrate()
    _populate_db(db)
    return db


async def _call(server, name: str, arguments: dict):
    handler = server.request_handlers[CallToolRequest]
    req = CallToolRequest(
        method="tools/call",
        params=CallToolRequestParams(name=name, arguments=arguments),
    )
    return await handler(req)


class TestBuildMcpServer:
    async def test_list_tools_returns_three(self):
        db = _db()
        synthesis = _make_synthesis()
        server = build_mcp_server(db, synthesis)
        handler = server.request_handlers[ListToolsRequest]
        result = await handler(ListToolsRequest(method="tools/list"))
        names = [t.name for t in result.root.tools]
        assert "query_mood" in names
        assert "query_trends" in names
        assert "query_timeline" in names

    async def test_call_tool_query_mood(self):
        db = _db()
        synthesis = _make_synthesis("Global mood.")
        server = build_mcp_server(db, synthesis)
        result = await _call(server, "query_mood", {})
        data = json.loads(result.root.content[0].text)
        assert "synthesis" in data

    async def test_call_tool_query_trends(self):
        db = _db()
        synthesis = _make_synthesis("Trends.")
        server = build_mcp_server(db, synthesis)
        result = await _call(server, "query_trends", {"hours": 24, "mode": "pulse"})
        data = json.loads(result.root.content[0].text)
        assert "synthesis" in data

    async def test_call_tool_query_timeline(self):
        db = _db()
        synthesis = _make_synthesis("Timeline.")
        server = build_mcp_server(db, synthesis)
        result = await _call(server, "query_timeline", {"topic": "climate"})
        data = json.loads(result.root.content[0].text)
        assert "synthesis" in data

    async def test_call_tool_unknown_returns_error(self):
        db = _db()
        synthesis = _make_synthesis()
        server = build_mcp_server(db, synthesis)
        result = await _call(server, "unknown_tool", {})
        assert "Unknown tool" in result.root.content[0].text


class TestQueryMood:
    async def test_global(self):
        db = _db()
        synthesis = _make_synthesis("Global.")
        now = datetime.now(tz=UTC)
        result = await _query_mood(db, synthesis, {}, now)
        data = json.loads(result[0].text)
        assert "synthesis" in data

    async def test_region_only(self):
        db = _db()
        synthesis = _make_synthesis("Europe.")
        now = datetime.now(tz=UTC)
        result = await _query_mood(db, synthesis, {"region": "Europe"}, now)
        data = json.loads(result[0].text)
        assert "synthesis" in data

    async def test_compare(self):
        db = _db()
        synthesis = _make_synthesis("Compare.")
        now = datetime.now(tz=UTC)
        result = await _query_mood(
            db, synthesis, {"region": "Europe", "compare_with": "Asia"}, now
        )
        data = json.loads(result[0].text)
        assert "synthesis" in data


class TestQueryTrends:
    async def test_emerging(self):
        db = _db()
        now = datetime.now(tz=UTC)
        result = await _query_trends(
            db, _make_synthesis("Emerging."), {"hours": 24, "mode": "emerging"}, now
        )
        data = json.loads(result[0].text)
        assert "synthesis" in data

    async def test_shifts(self):
        db = _db()
        now = datetime.now(tz=UTC)
        result = await _query_trends(
            db, _make_synthesis("Shifts."), {"hours": 24, "mode": "shifts"}, now
        )
        data = json.loads(result[0].text)
        assert "synthesis" in data

    async def test_pulse(self):
        db = _db()
        now = datetime.now(tz=UTC)
        result = await _query_trends(
            db, _make_synthesis("Pulse."), {"hours": 24, "mode": "pulse"}, now
        )
        data = json.loads(result[0].text)
        assert "synthesis" in data


class TestQueryTimeline:
    async def test_no_since(self):
        db = _db()
        now = datetime.now(tz=UTC)
        result = await _query_timeline(
            db, _make_synthesis("Timeline."), {"topic": "climate"}, now
        )
        data = json.loads(result[0].text)
        assert data["period_hours"] == 0

    async def test_with_since(self):
        db = _db()
        now = datetime.now(tz=UTC)
        result = await _query_timeline(
            db,
            _make_synthesis("Timeline since."),
            {"topic": "climate", "since": "2026-01-01T00:00:00Z"},
            now,
        )
        data = json.loads(result[0].text)
        assert data["period_hours"] > 0

    async def test_with_bad_since(self):
        db = _db()
        now = datetime.now(tz=UTC)
        result = await _query_timeline(
            db,
            _make_synthesis("Bad since."),
            {"topic": "climate", "since": "bad-date"},
            now,
        )
        data = json.loads(result[0].text)
        assert data["period_hours"] == 0
