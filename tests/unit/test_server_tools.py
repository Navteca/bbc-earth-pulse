"""Tests for server.py tool registration and MCP tool logic."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

from earth_pulse.db import SQLiteAdapter
from earth_pulse.models import Article, Enrichment
from earth_pulse.server import (
    _extract_types_from_union,
    _transform_object,
    _transform_property,
    _transform_schema,
)
from earth_pulse.temporal.synthesis import SynthesisEngine


def _make_synthesis(text: str = "Synthesis result.") -> SynthesisEngine:
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
            url=f"https://example.com/{i}",
            source="bbc_rss",
            published_at=datetime.now(tz=UTC),
            region="Global",
        )
        db.save_article(article)
        enrichment = Enrichment(
            article_id=article.id,
            emotion="anxiety",
            topics=["AI"],
            narratives=["disruption"],
            region="Global",
            urgency_score=0.8,
            anxiety_score=0.7,
            optimism_score=0.2,
            conflict_score=0.5,
            stability_score=0.3,
            enriched_at=datetime.now(tz=UTC),
        )
        db.save_enrichment(enrichment)


def _make_mcp(db: SQLiteAdapter, synthesis: SynthesisEngine):
    from mcp.server.fastmcp import FastMCP

    from earth_pulse.server import _register_tools

    mcp = FastMCP(f"test-{id(db)}")
    _register_tools(mcp, db, synthesis)
    return mcp


class TestQueryMoodTool:
    async def test_global_mood(self):
        db = SQLiteAdapter("sqlite:///:memory:")
        db.migrate()
        _populate_db(db)
        mcp = _make_mcp(db, _make_synthesis("Global anxiety rising."))
        result = await mcp.call_tool("query_mood", {})
        text = result[0][0].text
        data = json.loads(text)
        assert "synthesis" in data
        assert "sources" in data

    async def test_regional_mood(self):
        db = SQLiteAdapter("sqlite:///:memory:")
        db.migrate()
        _populate_db(db)
        mcp = _make_mcp(db, _make_synthesis("Europe is tense."))
        result = await mcp.call_tool("query_mood", {"region": "Europe"})
        text = result[0][0].text
        data = json.loads(text)
        assert "synthesis" in data

    async def test_compare_mood(self):
        db = SQLiteAdapter("sqlite:///:memory:")
        db.migrate()
        _populate_db(db)
        mcp = _make_mcp(db, _make_synthesis("Europe vs Asia."))
        result = await mcp.call_tool(
            "query_mood", {"region": "Europe", "compare_with": "Asia"}
        )
        text = result[0][0].text
        data = json.loads(text)
        assert "synthesis" in data


class TestQueryTrendsTool:
    async def test_pulse_mode(self):
        db = SQLiteAdapter("sqlite:///:memory:")
        db.migrate()
        _populate_db(db)
        mcp = _make_mcp(db, _make_synthesis("AI dominates."))
        result = await mcp.call_tool("query_trends", {"hours": 24, "mode": "pulse"})
        text = result[0][0].text
        data = json.loads(text)
        assert data["period_hours"] == 24

    async def test_emerging_mode(self):
        db = SQLiteAdapter("sqlite:///:memory:")
        db.migrate()
        _populate_db(db)
        mcp = _make_mcp(db, _make_synthesis("Emerging topics."))
        result = await mcp.call_tool("query_trends", {"hours": 12, "mode": "emerging"})
        text = result[0][0].text
        data = json.loads(text)
        assert "synthesis" in data

    async def test_shifts_mode(self):
        db = SQLiteAdapter("sqlite:///:memory:")
        db.migrate()
        _populate_db(db)
        mcp = _make_mcp(db, _make_synthesis("Narrative shifts."))
        result = await mcp.call_tool("query_trends", {"hours": 48, "mode": "shifts"})
        text = result[0][0].text
        data = json.loads(text)
        assert "synthesis" in data


class TestQueryTimelineTool:
    async def test_timeline_no_since(self):
        db = SQLiteAdapter("sqlite:///:memory:")
        db.migrate()
        _populate_db(db)
        mcp = _make_mcp(db, _make_synthesis("AI evolved."))
        result = await mcp.call_tool("query_timeline", {"topic": "AI"})
        text = result[0][0].text
        data = json.loads(text)
        assert "synthesis" in data
        assert data["period_hours"] == 0

    async def test_timeline_with_valid_since(self):
        db = SQLiteAdapter("sqlite:///:memory:")
        db.migrate()
        _populate_db(db)
        mcp = _make_mcp(db, _make_synthesis("AI over time."))
        result = await mcp.call_tool(
            "query_timeline", {"topic": "AI", "since": "2026-01-01T00:00:00Z"}
        )
        text = result[0][0].text
        data = json.loads(text)
        assert data["period_hours"] > 0

    async def test_timeline_with_invalid_since(self):
        db = SQLiteAdapter("sqlite:///:memory:")
        db.migrate()
        _populate_db(db)
        mcp = _make_mcp(db, _make_synthesis("AI story."))
        result = await mcp.call_tool(
            "query_timeline", {"topic": "AI", "since": "not-a-valid-date"}
        )
        text = result[0][0].text
        data = json.loads(text)
        assert data["period_hours"] == 0


class TestSchemaTransform:
    def test_anyof_nullable_collapsed(self):
        prop = {"anyOf": [{"type": "string"}, {"type": "null"}]}
        _transform_property(prop)
        assert prop["type"] == ["string", "null"]
        assert "anyOf" not in prop

    def test_oneof_nullable_collapsed(self):
        prop = {"oneOf": [{"type": "integer"}, {"type": "null"}]}
        _transform_property(prop)
        assert prop["type"] == ["integer", "null"]
        assert "oneOf" not in prop

    def test_nested_object_recursed(self):
        prop = {
            "type": "object",
            "properties": {
                "inner": {"anyOf": [{"type": "string"}, {"type": "null"}]}
            },
        }
        _transform_property(prop)
        assert prop["additionalProperties"] is False
        assert prop["required"] == ["inner"]
        assert prop["properties"]["inner"]["type"] == ["string", "null"]

    def test_array_items_recursed(self):
        prop = {
            "type": "array",
            "items": {"anyOf": [{"type": "string"}, {"type": "null"}]},
        }
        _transform_property(prop)
        assert prop["items"]["type"] == ["string", "null"]

    def test_extract_types_fallback(self):
        result = _extract_types_from_union([{"description": "no type here"}])
        assert result == ["string", "null"]

    def test_transform_object_sets_required_and_no_additional(self):
        obj = {"properties": {"a": {"type": "string"}, "b": {"type": "integer"}}}
        _transform_object(obj)
        assert set(obj["required"]) == {"a", "b"}
        assert obj["additionalProperties"] is False

    def test_transform_schema_full_object(self):
        schema = {
            "type": "object",
            "properties": {
                "region": {"anyOf": [{"type": "string"}, {"type": "null"}]},
                "hours": {"type": "integer"},
            },
        }
        result = _transform_schema(schema)
        assert result["additionalProperties"] is False
        assert set(result["required"]) == {"region", "hours"}
        assert result["properties"]["region"]["type"] == ["string", "null"]

    def test_single_type_anyof_not_wrapped_in_list(self):
        prop = {"anyOf": [{"type": "string"}]}
        _transform_property(prop)
        assert prop["type"] == "string"


class TestGetSourcesTool:
    async def test_returns_matching_articles(self):
        db = SQLiteAdapter("sqlite:///:memory:")
        db.migrate()
        _populate_db(db, n=2)
        pairs = db.get_enriched_articles(hours=24)
        ids = [a.id for a, _ in pairs]
        mcp = _make_mcp(db, _make_synthesis())
        result = await mcp.call_tool("get_sources", {"ids": ids})
        data = json.loads(result[0][0].text)
        assert isinstance(data, list)
        assert len(data) == 2
        assert all("id" in item and "title" in item and "url" in item for item in data)

    async def test_unknown_ids_omitted(self):
        db = SQLiteAdapter("sqlite:///:memory:")
        db.migrate()
        _populate_db(db, n=1)
        pairs = db.get_enriched_articles(hours=24)
        real_id = pairs[0][0].id
        mcp = _make_mcp(db, _make_synthesis())
        result = await mcp.call_tool("get_sources", {"ids": [real_id, "fake-id-xyz"]})
        data = json.loads(result[0][0].text)
        assert len(data) == 1
        assert data[0]["id"] == real_id

    async def test_empty_ids_returns_empty_list(self):
        db = SQLiteAdapter("sqlite:///:memory:")
        db.migrate()
        mcp = _make_mcp(db, _make_synthesis())
        result = await mcp.call_tool("get_sources", {"ids": []})
        data = json.loads(result[0][0].text)
        assert data == []


class TestQueryMoodDiffTool:
    async def test_returns_expected_fields(self):
        db = SQLiteAdapter("sqlite:///:memory:")
        db.migrate()
        _populate_db(db, n=3)
        mcp = _make_mcp(db, _make_synthesis("Mood has shifted."))
        result = await mcp.call_tool(
            "query_mood_diff", {"region": None, "hours": 48, "compare_days_ago": 7}
        )
        data = json.loads(result[0][0].text)
        assert "synthesis" in data
        assert "sources" in data
        assert "generated_at" in data
        assert data["period_hours"] == 48
        assert data["compare_days_ago"] == 7

    async def test_defaults(self):
        db = SQLiteAdapter("sqlite:///:memory:")
        db.migrate()
        _populate_db(db, n=2)
        mcp = _make_mcp(db, _make_synthesis("Default diff."))
        result = await mcp.call_tool("query_mood_diff", {})
        data = json.loads(result[0][0].text)
        assert data["period_hours"] == 24
        assert data["compare_days_ago"] == 7

    async def test_regional_diff(self):
        db = SQLiteAdapter("sqlite:///:memory:")
        db.migrate()
        _populate_db(db, n=2)
        mcp = _make_mcp(db, _make_synthesis("Europe diff."))
        result = await mcp.call_tool(
            "query_mood_diff", {"region": "Europe", "hours": 24, "compare_days_ago": 3}
        )
        data = json.loads(result[0][0].text)
        assert "synthesis" in data
