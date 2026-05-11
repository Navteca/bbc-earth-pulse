"""Unit tests for enrichment worker."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
import tiktoken

from earth_pulse.enrichment.worker import (
    EnrichmentWorker,
    _build_article_block,
    _validate_enrichment_response,
)
from earth_pulse.models import Article


def _article(url: str = "https://example.com/1") -> Article:
    return Article.build(
        title="Oil prices surge after attacks",
        url=url,
        source="bbc_rss",
        published_at=datetime.now(tz=UTC),
        summary="Oil prices rose sharply.",
        body_text="Full article body text here.",
    )


_VALID_RESPONSE = {
    "emotion": "anxiety",
    "topics": ["energy", "conflict"],
    "narratives": ["escalation"],
    "region": "Middle East",
    "urgency_score": 0.82,
    "anxiety_score": 0.79,
    "optimism_score": 0.11,
    "conflict_score": 0.91,
    "stability_score": 0.12,
}


class TestValidateEnrichmentResponse:
    def test_valid_response_passes(self):
        _validate_enrichment_response(_VALID_RESPONSE)

    def test_missing_field_raises(self):
        bad = {k: v for k, v in _VALID_RESPONSE.items() if k != "emotion"}
        with pytest.raises(ValueError, match="emotion"):
            _validate_enrichment_response(bad)

    def test_score_out_of_range_raises(self):
        bad = {**_VALID_RESPONSE, "urgency_score": 1.5}
        with pytest.raises(ValueError, match="urgency_score"):
            _validate_enrichment_response(bad)

    def test_score_zero_is_valid(self):
        ok = {**_VALID_RESPONSE, "urgency_score": 0.0}
        _validate_enrichment_response(ok)

    def test_score_one_is_valid(self):
        ok = {**_VALID_RESPONSE, "urgency_score": 1.0}
        _validate_enrichment_response(ok)


class TestBuildArticleBlock:
    def test_includes_title(self):
        a = _article()
        enc = tiktoken.get_encoding("cl100k_base")
        block = _build_article_block(a, enc)
        assert "Oil prices surge" in block
        assert "<article>" in block
        assert "</article>" in block

    def test_includes_summary(self):
        a = _article()
        enc = tiktoken.get_encoding("cl100k_base")
        block = _build_article_block(a, enc)
        assert "Oil prices rose sharply" in block

    def test_article_without_body(self):
        a = _article()
        a.body_text = None
        enc = tiktoken.get_encoding("cl100k_base")
        block = _build_article_block(a, enc)
        assert "Body:" not in block

    def test_long_body_is_truncated(self):
        a = _article()
        a.body_text = "word " * 2000
        enc = tiktoken.get_encoding("cl100k_base")
        block = _build_article_block(a, enc)
        # Should not exceed reasonable size
        assert len(block) < len("word " * 2000)


class TestEnrichmentWorker:
    def _make_worker(self, db, mock_client, logger):
        return EnrichmentWorker(
            db=db,
            openai_client=mock_client,
            model="gpt-test",
            logger=logger,
        )

    def _mock_openai(self, content: str):
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = content
        mock_client.chat = MagicMock()
        mock_client.chat.completions = MagicMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
        return mock_client

    async def test_enriches_article_successfully(self, db, logger):
        a = _article()
        db.save_article(a)
        mock_client = self._mock_openai(json.dumps(_VALID_RESPONSE))
        worker = self._make_worker(db, mock_client, logger)
        count = await worker.run_batch()
        assert count == 1

    async def test_dead_letters_after_max_retries(self, db, logger):
        a = _article()
        db.save_article(a)
        mock_client = self._mock_openai("not valid json {{{")
        worker = self._make_worker(db, mock_client, logger)
        count = await worker.run_batch()
        assert count == 0
        # Article should be dead-lettered
        unenriched = db.get_unenriched_articles()
        assert not any(u.id == a.id for u in unenriched)

    async def test_empty_db_returns_zero(self, db, logger):
        mock_client = self._mock_openai(json.dumps(_VALID_RESPONSE))
        worker = self._make_worker(db, mock_client, logger)
        count = await worker.run_batch()
        assert count == 0

    async def test_empty_gpt_response_dead_letters(self, db, logger):
        a = _article()
        db.save_article(a)
        mock_client = self._mock_openai("")
        worker = self._make_worker(db, mock_client, logger)
        count = await worker.run_batch()
        assert count == 0
