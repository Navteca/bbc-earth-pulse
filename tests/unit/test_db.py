"""Unit tests for SQLiteAdapter (DatabasePort)."""

from __future__ import annotations

from datetime import UTC, datetime

from earth_pulse.models import Article, Enrichment


def _article(url: str = "https://example.com/1", title: str = "Test") -> Article:
    return Article.build(
        title=title,
        url=url,
        source="bbc_rss",
        published_at=datetime.now(tz=UTC),
        summary="A summary",
    )


def _enrichment(article_id: str) -> Enrichment:
    return Enrichment(
        article_id=article_id,
        emotion="anxiety",
        topics=["AI", "labor"],
        narratives=["disruption"],
        region="Global",
        urgency_score=0.8,
        anxiety_score=0.7,
        optimism_score=0.2,
        conflict_score=0.5,
        stability_score=0.3,
        enriched_at=datetime.now(tz=UTC),
    )


class TestSQLiteAdapter:
    def test_migrate_creates_tables(self, db):
        # If migrate ran without error, tables exist (already called in fixture)
        assert not db.article_exists("nonexistent", "nonexistent")

    def test_save_and_exists_by_url_hash(self, db):
        a = _article()
        assert not db.article_exists(a.url_hash, a.title_hash)
        db.save_article(a)
        assert db.article_exists(a.url_hash, a.title_hash)

    def test_exists_by_title_hash(self, db):
        a = _article()
        db.save_article(a)
        # Different URL but same title
        a2 = _article(url="https://other.com/1", title="Test")
        assert db.article_exists(a2.url_hash, a2.title_hash)

    def test_save_article_idempotent(self, db):
        a = _article()
        db.save_article(a)
        db.save_article(a)  # Should not raise
        assert db.article_exists(a.url_hash, a.title_hash)

    def test_get_unenriched_returns_articles(self, db):
        a = _article()
        db.save_article(a)
        unenriched = db.get_unenriched_articles()
        assert any(u.id == a.id for u in unenriched)

    def test_save_enrichment_removes_from_unenriched(self, db):
        a = _article()
        db.save_article(a)
        e = _enrichment(a.id)
        db.save_enrichment(e)
        unenriched = db.get_unenriched_articles()
        assert not any(u.id == a.id for u in unenriched)

    def test_get_enriched_articles(self, db):
        a = _article()
        db.save_article(a)
        e = _enrichment(a.id)
        db.save_enrichment(e)
        pairs = db.get_enriched_articles(hours=24)
        assert len(pairs) == 1
        assert pairs[0][0].id == a.id
        assert pairs[0][1].emotion == "anxiety"

    def test_get_enriched_articles_filters_by_region(self, db):
        a1 = _article(url="https://example.com/1")
        a2 = _article(url="https://example.com/2", title="Other")
        db.save_article(a1)
        db.save_article(a2)
        e1 = _enrichment(a1.id)
        e1.region = "Europe"
        e2 = _enrichment(a2.id)
        e2.region = "Asia"
        db.save_enrichment(e1)
        db.save_enrichment(e2)
        pairs = db.get_enriched_articles(region="Europe", hours=24)
        ids = [p[0].id for p in pairs]
        assert a1.id in ids
        assert a2.id not in ids

    def test_mark_enrichment_failed(self, db):
        a = _article()
        db.save_article(a)
        db.mark_enrichment_failed(a.id, "timeout", 3)
        unenriched = db.get_unenriched_articles()
        assert not any(u.id == a.id for u in unenriched)

    def test_get_timeline_articles(self, db):
        a = _article(title="AI fears are growing worldwide")
        db.save_article(a)
        e = _enrichment(a.id)
        e.topics = ["AI", "labor"]
        db.save_enrichment(e)
        pairs = db.get_timeline_articles(topic="AI")
        assert len(pairs) >= 1
        assert pairs[0][0].id == a.id

    def test_get_timeline_articles_no_false_positives(self, db):
        """'AI' must not match articles whose topics only contain substrings like
        'Iran', 'air strikes', 'Airbnb' — the classic LIKE '%AI%' false-positive set."""
        # This article's topics contain "AI" as a substring in other words — never standalone.
        a_false = _article(url="https://example.com/iran", title="Iran nuclear talks resume")
        db.save_article(a_false)
        e_false = _enrichment(a_false.id)
        e_false.topics = ["Iran", "air strikes", "Airbnb", "training facilities"]
        db.save_enrichment(e_false)

        # This article genuinely covers AI.
        a_true = _article(
            url="https://example.com/ai",
            title="New AI governance framework proposed",
        )
        db.save_article(a_true)
        e_true = _enrichment(a_true.id)
        e_true.topics = ["AI governance", "regulation", "technology policy"]
        db.save_enrichment(e_true)

        pairs = db.get_timeline_articles(topic="AI")
        ids = [p[0].id for p in pairs]

        assert a_true.id in ids, "genuine AI article must be returned"
        assert a_false.id not in ids, (
            "article with topics ['Iran','air strikes','Airbnb','training facilities'] "
            "must NOT match topic='AI'"
        )

    def test_get_timeline_articles_matches_multi_word_topic_element(self, db):
        """'AI' should match a topic element like 'AI governance' (partial within element)."""
        a = _article(url="https://example.com/ai2", title="Regulators eye AI models")
        db.save_article(a)
        e = _enrichment(a.id)
        e.topics = ["AI governance", "tech regulation"]
        db.save_enrichment(e)
        pairs = db.get_timeline_articles(topic="AI")
        ids = [p[0].id for p in pairs]
        assert a.id in ids

    def test_get_timeline_articles_matches_narrative(self, db):
        """Topic search should also match terms in the narratives array."""
        a = _article(url="https://example.com/climate1", title="Unrelated headline")
        db.save_article(a)
        e = _enrichment(a.id)
        e.topics = ["environment"]
        e.narratives = ["Climate anxiety is driving policy shifts across Europe"]
        db.save_enrichment(e)
        pairs = db.get_timeline_articles(topic="climate")
        ids = [p[0].id for p in pairs]
        assert a.id in ids

    def test_get_timeline_articles_since_filter(self, db):
        from datetime import timedelta
        a = _article()
        db.save_article(a)
        e = _enrichment(a.id)
        db.save_enrichment(e)
        future = datetime.now(tz=UTC) + timedelta(days=1)
        pairs = db.get_timeline_articles(topic="Test", since=future)
        assert pairs == []

    def test_file_based_sqlite(self, tmp_path):
        """Covers the non-memory SQLite path (lines 126-128 of adapter.py)."""
        from earth_pulse.db import SQLiteAdapter

        url = f"sqlite:///{tmp_path}/test.db"
        adapter = SQLiteAdapter(url)
        adapter.migrate()
        assert not adapter.article_exists("x", "y")

    def test_get_articles_by_ids_returns_matching(self, db):
        a1 = _article(url="https://example.com/ids1", title="IDs test one")
        a2 = _article(url="https://example.com/ids2", title="IDs test two")
        db.save_article(a1)
        db.save_article(a2)
        results = db.get_articles_by_ids([a1.id, a2.id])
        ids = [r.id for r in results]
        assert a1.id in ids
        assert a2.id in ids

    def test_get_articles_by_ids_preserves_order(self, db):
        a1 = _article(url="https://example.com/order1", title="Order one")
        a2 = _article(url="https://example.com/order2", title="Order two")
        db.save_article(a1)
        db.save_article(a2)
        results = db.get_articles_by_ids([a2.id, a1.id])
        assert results[0].id == a2.id
        assert results[1].id == a1.id

    def test_get_articles_by_ids_unknown_ids_omitted(self, db):
        a = _article(url="https://example.com/known", title="Known article")
        db.save_article(a)
        results = db.get_articles_by_ids([a.id, "nonexistent-id-xyz"])
        assert len(results) == 1
        assert results[0].id == a.id

    def test_get_articles_by_ids_empty_list(self, db):
        results = db.get_articles_by_ids([])
        assert results == []
