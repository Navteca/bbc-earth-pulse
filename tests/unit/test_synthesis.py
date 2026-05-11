"""Unit tests for SynthesisEngine and helpers."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

from earth_pulse.models import Article, Enrichment
from earth_pulse.temporal.analytics import AnalyticsContext, compute_analytics
from earth_pulse.temporal.synthesis import (
    SynthesisEngine,
    _article_to_compact,
    _pack_articles,
)


def _make_pair(url: str = "https://example.com/1", title: str = "Test") -> tuple:
    article = Article.build(
        title=title,
        url=url,
        source="bbc_rss",
        published_at=datetime.now(tz=UTC),
    )
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
    return article, enrichment


class TestArticleToCompact:
    def test_returns_expected_keys(self):
        article, enrichment = _make_pair()
        compact = _article_to_compact(article, enrichment)
        assert compact["id"] == article.id
        assert compact["title"] == article.title
        assert compact["emotion"] == "anxiety"
        assert compact["urgency_score"] == 0.8

    def test_uses_enrichment_region_over_article_region(self):
        article, enrichment = _make_pair()
        enrichment.region = "Europe"
        compact = _article_to_compact(article, enrichment)
        assert compact["region"] == "Europe"

    def test_falls_back_to_article_region_when_enrichment_region_none(self):
        article = Article.build(
            title="Test",
            url="https://example.com/1",
            source="bbc_rss",
            published_at=datetime.now(tz=UTC),
            region="Asia",
        )
        enrichment = Enrichment(
            article_id=article.id,
            emotion="calm",
            topics=[],
            narratives=[],
            region=None,
            urgency_score=0.1,
            anxiety_score=0.1,
            optimism_score=0.8,
            conflict_score=0.1,
            stability_score=0.9,
            enriched_at=datetime.now(tz=UTC),
        )
        compact = _article_to_compact(article, enrichment)
        assert compact["region"] == "Asia"


class TestPackArticles:
    def test_packs_articles_within_budget(self):
        pairs = [_make_pair(f"https://example.com/{i}", f"Title {i}") for i in range(5)]
        packed, source_ids = _pack_articles(pairs)
        assert len(packed) == 5
        assert len(source_ids) == 5

    def test_stops_at_token_budget(self):
        # Use very small budget to force early stop
        pairs = [_make_pair(f"https://example.com/{i}", f"Title {i}") for i in range(10)]
        packed, source_ids = _pack_articles(pairs, max_tokens=10)
        assert len(packed) < 10

    def test_empty_pairs(self):
        packed, source_ids = _pack_articles([])
        assert packed == []
        assert source_ids == []


class TestSynthesisEngine:
    async def test_returns_insufficient_data_when_no_pairs(self):
        mock_client = MagicMock()
        engine = SynthesisEngine(mock_client, "gpt-test")
        text, ids = await engine.synthesize([], "some instruction")
        assert "Insufficient" in text
        assert ids == []

    async def test_synthesizes_with_valid_pairs(self):
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.choices = [MagicMock()]
        mock_resp.choices[0].message.content = "Humanity is anxious."
        mock_client.chat = MagicMock()
        mock_client.chat.completions = MagicMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_resp)

        engine = SynthesisEngine(mock_client, "gpt-test")
        pairs = [_make_pair(f"https://example.com/{i}", f"Title {i}") for i in range(3)]
        text, ids = await engine.synthesize(pairs, "What is the mood?")
        assert text == "Humanity is anxious."
        assert len(ids) == 3

    async def test_returns_empty_string_when_gpt_returns_none(self):
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.choices = [MagicMock()]
        mock_resp.choices[0].message.content = None
        mock_client.chat = MagicMock()
        mock_client.chat.completions = MagicMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_resp)

        engine = SynthesisEngine(mock_client, "gpt-test")
        pairs = [_make_pair()]
        text, _ = await engine.synthesize(pairs, "instruction")
        assert text == ""

    async def test_analytics_context_injected_into_prompt(self):
        """When analytics is supplied the prompt should contain <analytics>."""
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.choices = [MagicMock()]
        mock_resp.choices[0].message.content = "Synthesis with analytics."
        mock_client.chat = MagicMock()
        mock_client.chat.completions = MagicMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_resp)

        engine = SynthesisEngine(mock_client, "gpt-test")
        pairs = [_make_pair(f"https://example.com/{i}", f"Title {i}") for i in range(3)]
        analytics = compute_analytics(pairs, period_hours=24)
        text, ids = await engine.synthesize(pairs, "instruction", analytics=analytics)
        assert text == "Synthesis with analytics."

        # Verify <analytics> block was injected into the prompt sent to GPT
        call_args = mock_client.chat.completions.create.call_args
        user_content = call_args.kwargs["messages"][1]["content"]
        assert "<analytics>" in user_content

    async def test_no_analytics_context_no_analytics_block(self):
        """When analytics is None the prompt should NOT contain <analytics>."""
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.choices = [MagicMock()]
        mock_resp.choices[0].message.content = "Synthesis without analytics."
        mock_client.chat = MagicMock()
        mock_client.chat.completions = MagicMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_resp)

        engine = SynthesisEngine(mock_client, "gpt-test")
        pairs = [_make_pair()]
        text, _ = await engine.synthesize(pairs, "instruction", analytics=None)
        assert text == "Synthesis without analytics."

        call_args = mock_client.chat.completions.create.call_args
        user_content = call_args.kwargs["messages"][1]["content"]
        assert "<analytics>" not in user_content

    async def test_empty_context_analytics_no_error(self):
        """An AnalyticsContext with article_count=0 (below threshold) should not error."""
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.choices = [MagicMock()]
        mock_resp.choices[0].message.content = "OK."
        mock_client.chat = MagicMock()
        mock_client.chat.completions = MagicMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_resp)

        engine = SynthesisEngine(mock_client, "gpt-test")
        pairs = [_make_pair()]
        empty_ctx = AnalyticsContext(article_count=0, period_hours=0)
        text, _ = await engine.synthesize(pairs, "instruction", analytics=empty_ctx)
        assert text == "OK."
