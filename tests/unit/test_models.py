"""Unit tests for Article model and normalization."""

from __future__ import annotations

from datetime import UTC, datetime

from earth_pulse.models import VALID_EMOTIONS, VALID_REGIONS, Article, Enrichment


def _make_article(**kwargs) -> Article:
    defaults = dict(
        title="Test Article",
        url="https://example.com/test",
        source="bbc_rss",
        published_at=datetime.now(tz=UTC),
    )
    defaults.update(kwargs)
    return Article.build(**defaults)


class TestArticleHashing:
    def test_url_hash_is_sha256(self):
        a = _make_article()
        assert len(a.url_hash) == 64
        assert a.url_hash == Article.make_url_hash("https://example.com/test")

    def test_title_hash_normalizes_case_and_punctuation(self):
        h1 = Article.make_title_hash("Hello, World!")
        h2 = Article.make_title_hash("hello world")
        assert h1 == h2

    def test_title_hash_normalizes_unicode(self):
        h1 = Article.make_title_hash("café")
        h2 = Article.make_title_hash("cafe")
        # Not identical but both are valid SHA256
        assert len(h1) == 64
        assert len(h2) == 64

    def test_id_equals_url_hash(self):
        a = _make_article()
        assert a.id == a.url_hash

    def test_url_is_stripped(self):
        a = _make_article(url="  https://example.com/test  ")
        assert a.url == "https://example.com/test"

    def test_different_urls_give_different_hashes(self):
        h1 = Article.make_url_hash("https://example.com/1")
        h2 = Article.make_url_hash("https://example.com/2")
        assert h1 != h2


class TestArticleBuild:
    def test_default_language_is_en(self):
        a = _make_article()
        assert a.language == "en"

    def test_ingested_at_is_utc(self):
        a = _make_article()
        assert a.ingested_at.tzinfo is not None

    def test_optional_fields_default_none(self):
        a = _make_article()
        assert a.summary is None
        assert a.body_text is None
        assert a.region is None
        assert a.category is None

    def test_fields_stored(self):
        now = datetime.now(tz=UTC)
        a = _make_article(
            summary="A summary",
            body_text="Body text",
            region="Europe",
            category="politics",
            language="fr",
            published_at=now,
        )
        assert a.summary == "A summary"
        assert a.body_text == "Body text"
        assert a.region == "Europe"
        assert a.category == "politics"
        assert a.language == "fr"


class TestTaxonomies:
    def test_valid_regions_contains_eight(self):
        assert len(VALID_REGIONS) == 8

    def test_all_regions_present(self):
        expected = [
            "Africa", "Asia", "Europe", "Latin America",
            "Middle East", "North America", "Oceania", "Global",
        ]
        for region in expected:
            assert region in VALID_REGIONS

    def test_valid_emotions_non_empty(self):
        assert len(VALID_EMOTIONS) > 0
        assert "anxiety" in VALID_EMOTIONS
        assert "optimism" in VALID_EMOTIONS


class TestEnrichmentModel:
    def test_enrichment_defaults(self):
        e = Enrichment(
            article_id="abc",
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
        assert e.enrichment_failed is False
        assert e.failure_reason is None
        assert e.retry_count == 0
