"""Unit tests for earth_pulse/temporal/analytics.py."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from earth_pulse.models import Article, Enrichment
from earth_pulse.temporal.analytics import (
    AnalyticsContext,
    EmotionDistribution,
    NarrativePhase,
    RegionalBreakdown,
    ScoreStats,
    TopicFrequency,
    _compute_emotion_distribution,
    _compute_narrative_phases,
    _compute_regional_breakdown,
    _compute_score_stats,
    _compute_signals,
    _compute_topic_frequency,
    _percentile,
    _trend_direction,
    compute_analytics,
)

# --------------------------------------------------------------------------- #
#  Fixtures                                                                    #
# --------------------------------------------------------------------------- #


def _make_pair(
    url: str = "https://example.com/1",
    title: str = "Test",
    emotion: str = "anxiety",
    topics: list[str] | None = None,
    narratives: list[str] | None = None,
    region: str | None = "Global",
    anxiety_score: float = 0.7,
    optimism_score: float = 0.2,
    conflict_score: float = 0.5,
    stability_score: float = 0.3,
    urgency_score: float = 0.8,
    published_at: datetime | None = None,
) -> tuple[Article, Enrichment]:
    if topics is None:
        topics = ["AI"]
    if narratives is None:
        narratives = ["disruption"]
    pub = published_at or datetime.now(tz=UTC)
    article = Article.build(
        title=title,
        url=url,
        source="bbc_rss",
        published_at=pub,
        region=region,
    )
    enrichment = Enrichment(
        article_id=article.id,
        emotion=emotion,
        topics=topics,
        narratives=narratives,
        region=region,
        urgency_score=urgency_score,
        anxiety_score=anxiety_score,
        optimism_score=optimism_score,
        conflict_score=conflict_score,
        stability_score=stability_score,
        enriched_at=datetime.now(tz=UTC),
    )
    return article, enrichment


def _make_pairs(n: int, **kwargs) -> list[tuple[Article, Enrichment]]:
    return [
        _make_pair(url=f"https://example.com/{i}", title=f"Title {i}", **kwargs)
        for i in range(n)
    ]


# --------------------------------------------------------------------------- #
#  _percentile                                                                 #
# --------------------------------------------------------------------------- #


class TestPercentile:
    def test_empty_returns_zero(self):
        assert _percentile([], 75) == 0.0

    def test_single_value(self):
        assert _percentile([0.5], 90) == pytest.approx(0.5)

    def test_p50_is_median(self):
        result = _percentile([1.0, 2.0, 3.0, 4.0, 5.0], 50)
        assert result == pytest.approx(3.0)

    def test_p75(self):
        result = _percentile([0.0, 0.5, 1.0], 75)
        assert result == pytest.approx(0.75)

    def test_p100_is_max(self):
        values = [0.1, 0.5, 0.9]
        assert _percentile(values, 100) == pytest.approx(0.9)

    def test_p0_is_min(self):
        values = [0.1, 0.5, 0.9]
        assert _percentile(values, 0) == pytest.approx(0.1)


# --------------------------------------------------------------------------- #
#  _trend_direction                                                            #
# --------------------------------------------------------------------------- #


class TestTrendDirection:
    def test_fewer_than_4_returns_unknown(self):
        assert _trend_direction([0.1, 0.2, 0.3]) == "unknown"

    def test_empty_returns_unknown(self):
        assert _trend_direction([]) == "unknown"

    def test_rising(self):
        # early mean ≈ 0.1, recent mean ≈ 0.8 → rising
        assert _trend_direction([0.1, 0.1, 0.8, 0.8]) == "rising"

    def test_falling(self):
        # early mean ≈ 0.8, recent mean ≈ 0.1 → falling
        assert _trend_direction([0.8, 0.8, 0.1, 0.1]) == "falling"

    def test_stable(self):
        # both halves ≈ 0.5
        assert _trend_direction([0.5, 0.5, 0.5, 0.5]) == "stable"

    def test_boundary_just_above_rising(self):
        # delta = 0.06 > 0.05 → rising
        assert _trend_direction([0.4, 0.4, 0.46, 0.46]) == "rising"

    def test_boundary_just_below_falling(self):
        # delta = -0.06 < -0.05 → falling
        assert _trend_direction([0.46, 0.46, 0.4, 0.4]) == "falling"


# --------------------------------------------------------------------------- #
#  _compute_score_stats                                                        #
# --------------------------------------------------------------------------- #


class TestComputeScoreStats:
    def test_returns_all_five_dimensions(self):
        pairs = _make_pairs(4)
        stats = _compute_score_stats(pairs, pairs)
        dims = {s.dimension for s in stats}
        assert dims == {"anxiety", "optimism", "conflict", "stability", "urgency"}

    def test_empty_pairs_returns_zeroes(self):
        stats = _compute_score_stats([], [])
        for s in stats:
            assert s.mean == 0.0
            assert s.trend_direction == "unknown"

    def test_mean_is_correct(self):
        pairs = [
            _make_pair(url=f"https://example.com/{i}", anxiety_score=0.6)
            for i in range(4)
        ]
        stats = _compute_score_stats(pairs, pairs)
        anxiety_stat = next(s for s in stats if s.dimension == "anxiety")
        assert anxiety_stat.mean == pytest.approx(0.6)

    def test_trend_direction_propagated(self):
        # chrono: early 0.1, recent 0.9 → rising anxiety
        base = datetime(2026, 1, 1, tzinfo=UTC)
        pairs = [
            _make_pair(
                url=f"https://x.com/{i}",
                anxiety_score=0.1 if i < 2 else 0.9,
                published_at=base + timedelta(hours=i),
            )
            for i in range(4)
        ]
        chrono = sorted(pairs, key=lambda p: p[0].published_at)
        stats = _compute_score_stats(pairs, chrono)
        anxiety_stat = next(s for s in stats if s.dimension == "anxiety")
        assert anxiety_stat.trend_direction == "rising"


# --------------------------------------------------------------------------- #
#  _compute_emotion_distribution                                               #
# --------------------------------------------------------------------------- #


class TestComputeEmotionDistribution:
    def test_counts_are_correct(self):
        pairs = [
            _make_pair(url="https://x.com/1", emotion="anxiety"),
            _make_pair(url="https://x.com/2", emotion="anxiety"),
            _make_pair(url="https://x.com/3", emotion="hope"),
        ]
        dist = _compute_emotion_distribution(pairs)
        assert dist.counts["anxiety"] == 2
        assert dist.counts["hope"] == 1

    def test_sorted_by_count_descending(self):
        pairs = [
            _make_pair(url="https://x.com/1", emotion="hope"),
            _make_pair(url="https://x.com/2", emotion="anxiety"),
            _make_pair(url="https://x.com/3", emotion="anxiety"),
        ]
        dist = _compute_emotion_distribution(pairs)
        top = next(iter(dist.counts))
        assert top == "anxiety"

    def test_empty_pairs(self):
        dist = _compute_emotion_distribution([])
        assert dist.counts == {}

    def test_empty_emotion_skipped(self):
        pairs = [_make_pair(emotion="")]
        dist = _compute_emotion_distribution(pairs)
        assert dist.counts == {}


# --------------------------------------------------------------------------- #
#  _compute_topic_frequency                                                    #
# --------------------------------------------------------------------------- #


class TestComputeTopicFrequency:
    def test_counts_topics(self):
        pairs = [
            _make_pair(url="https://x.com/1", topics=["AI", "climate"]),
            _make_pair(url="https://x.com/2", topics=["AI"]),
        ]
        freq = _compute_topic_frequency(pairs)
        assert freq.counts["AI"] == 2
        assert freq.counts["climate"] == 1

    def test_limited_to_15(self):
        topics_per_article = [f"topic_{j}" for j in range(20)]
        pairs = [_make_pair(url="https://x.com/1", topics=topics_per_article)]
        freq = _compute_topic_frequency(pairs)
        assert len(freq.counts) == 15

    def test_empty_topics_skipped(self):
        pairs = [_make_pair(url="https://x.com/1", topics=["", "AI"])]
        freq = _compute_topic_frequency(pairs)
        assert "" not in freq.counts
        assert "AI" in freq.counts

    def test_empty_pairs(self):
        freq = _compute_topic_frequency([])
        assert freq.counts == {}


# --------------------------------------------------------------------------- #
#  _compute_regional_breakdown                                                 #
# --------------------------------------------------------------------------- #


class TestComputeRegionalBreakdown:
    def test_groups_by_region(self):
        pairs = [
            _make_pair(url="https://x.com/1", region="Europe", anxiety_score=0.6),
            _make_pair(url="https://x.com/2", region="Asia", anxiety_score=0.4),
        ]
        breakdown = _compute_regional_breakdown(pairs)
        assert "Europe" in breakdown.regions
        assert "Asia" in breakdown.regions
        assert breakdown.regions["Europe"]["count"] == 1

    def test_mean_scores_are_correct(self):
        pairs = [
            _make_pair(url="https://x.com/1", region="Europe", anxiety_score=0.6),
            _make_pair(url="https://x.com/2", region="Europe", anxiety_score=0.4),
        ]
        breakdown = _compute_regional_breakdown(pairs)
        assert breakdown.regions["Europe"]["mean_anxiety"] == pytest.approx(0.5)

    def test_falls_back_to_article_region(self):
        article = Article.build(
            title="Test",
            url="https://x.com/fallback",
            source="bbc_rss",
            published_at=datetime.now(tz=UTC),
            region="Oceania",
        )
        enrichment = Enrichment(
            article_id=article.id,
            emotion="calm",
            topics=[],
            narratives=[],
            region=None,  # no enrichment region
            urgency_score=0.1,
            anxiety_score=0.1,
            optimism_score=0.8,
            conflict_score=0.1,
            stability_score=0.9,
            enriched_at=datetime.now(tz=UTC),
        )
        breakdown = _compute_regional_breakdown([(article, enrichment)])
        assert "Oceania" in breakdown.regions

    def test_unknown_fallback_when_no_region(self):
        article = Article.build(
            title="No region",
            url="https://x.com/noregion",
            source="bbc_rss",
            published_at=datetime.now(tz=UTC),
            region=None,
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
        breakdown = _compute_regional_breakdown([(article, enrichment)])
        assert "Unknown" in breakdown.regions

    def test_empty_pairs(self):
        breakdown = _compute_regional_breakdown([])
        assert breakdown.regions == {}


# --------------------------------------------------------------------------- #
#  _compute_narrative_phases                                                   #
# --------------------------------------------------------------------------- #


class TestComputeNarrativePhases:
    def test_empty_pairs(self):
        np_ = _compute_narrative_phases([])
        assert np_.emerging == []
        assert np_.fading == []

    def test_single_pair(self):
        pair = _make_pair(narratives=["conflict"])
        np_ = _compute_narrative_phases([pair])
        assert "conflict" in np_.early
        assert np_.emerging == []
        assert np_.fading == []

    def test_emerging_detected(self):
        base = datetime(2026, 1, 1, tzinfo=UTC)
        early_pair = _make_pair(
            url="https://x.com/1",
            narratives=["old"],
            published_at=base,
        )
        recent_pair = _make_pair(
            url="https://x.com/2",
            narratives=["new"],
            published_at=base + timedelta(hours=10),
        )
        np_ = _compute_narrative_phases([early_pair, recent_pair])
        assert "new" in np_.emerging
        assert "old" in np_.fading

    def test_stable_narratives_not_emerging_or_fading(self):
        base = datetime(2026, 1, 1, tzinfo=UTC)
        pairs = [
            _make_pair(
                url=f"https://x.com/{i}",
                narratives=["stable"],
                published_at=base + timedelta(hours=i),
            )
            for i in range(4)
        ]
        np_ = _compute_narrative_phases(pairs)
        assert "stable" not in np_.emerging
        assert "stable" not in np_.fading


# --------------------------------------------------------------------------- #
#  _compute_signals                                                            #
# --------------------------------------------------------------------------- #


class TestComputeSignals:
    def _make_stats(
        self,
        anxiety_mean: float = 0.5,
        anxiety_trend: str = "stable",
        optimism_mean: float = 0.4,
        optimism_trend: str = "stable",
        conflict_mean: float = 0.3,
    ) -> list[ScoreStats]:
        def _s(dim: str, mean: float, trend: str) -> ScoreStats:
            return ScoreStats(dim, mean, mean, mean, mean, trend)

        return [
            _s("anxiety", anxiety_mean, anxiety_trend),
            _s("optimism", optimism_mean, optimism_trend),
            _s("conflict", conflict_mean, "stable"),
            _s("stability", 0.5, "stable"),
            _s("urgency", 0.5, "stable"),
        ]

    def test_elevated_anxiety(self):
        stats = self._make_stats(anxiety_mean=0.7)
        signals = _compute_signals(stats, EmotionDistribution({"anxiety": 5}))
        assert signals["anxiety_level"] == "elevated"

    def test_low_anxiety(self):
        stats = self._make_stats(anxiety_mean=0.2)
        signals = _compute_signals(stats, EmotionDistribution({}))
        assert signals["anxiety_level"] == "low"

    def test_moderate_anxiety(self):
        stats = self._make_stats(anxiety_mean=0.5)
        signals = _compute_signals(stats, EmotionDistribution({}))
        assert signals["anxiety_level"] == "moderate"

    def test_anxiety_trend_included_when_known(self):
        stats = self._make_stats(anxiety_trend="rising")
        signals = _compute_signals(stats, EmotionDistribution({}))
        assert signals["anxiety_trend"] == "rising"

    def test_anxiety_trend_excluded_when_unknown(self):
        stats = self._make_stats(anxiety_trend="unknown")
        signals = _compute_signals(stats, EmotionDistribution({}))
        assert "anxiety_trend" not in signals

    def test_high_optimism(self):
        stats = self._make_stats(optimism_mean=0.6)
        signals = _compute_signals(stats, EmotionDistribution({}))
        assert signals["optimism_level"] == "high"

    def test_low_optimism(self):
        stats = self._make_stats(optimism_mean=0.2)
        signals = _compute_signals(stats, EmotionDistribution({}))
        assert signals["optimism_level"] == "low"

    def test_moderate_optimism(self):
        stats = self._make_stats(optimism_mean=0.45)
        signals = _compute_signals(stats, EmotionDistribution({}))
        assert signals["optimism_level"] == "moderate"

    def test_optimism_trend_included_when_known(self):
        stats = self._make_stats(optimism_trend="falling")
        signals = _compute_signals(stats, EmotionDistribution({}))
        assert signals["optimism_trend"] == "falling"

    def test_optimism_trend_excluded_when_unknown(self):
        stats = self._make_stats(optimism_trend="unknown")
        signals = _compute_signals(stats, EmotionDistribution({}))
        assert "optimism_trend" not in signals

    def test_conflict_elevated_signal(self):
        stats = self._make_stats(conflict_mean=0.7)
        signals = _compute_signals(stats, EmotionDistribution({}))
        assert signals["conflict_elevated"] == "true"

    def test_conflict_not_elevated_below_threshold(self):
        stats = self._make_stats(conflict_mean=0.5)
        signals = _compute_signals(stats, EmotionDistribution({}))
        assert "conflict_elevated" not in signals

    def test_dominant_emotion_included(self):
        stats = self._make_stats()
        signals = _compute_signals(stats, EmotionDistribution({"fear": 3, "hope": 1}))
        assert signals["dominant_emotion"] == "fear"

    def test_no_dominant_emotion_when_empty(self):
        stats = self._make_stats()
        signals = _compute_signals(stats, EmotionDistribution({}))
        assert "dominant_emotion" not in signals


# --------------------------------------------------------------------------- #
#  compute_analytics (public API)                                              #
# --------------------------------------------------------------------------- #


class TestComputeAnalytics:
    def test_empty_pairs_returns_empty_context(self):
        ctx = compute_analytics([], period_hours=24)
        assert ctx.article_count == 0
        assert ctx.score_stats == []

    def test_single_pair_below_min_threshold(self):
        pairs = _make_pairs(1)
        ctx = compute_analytics(pairs, period_hours=24)
        assert ctx.article_count == 1
        assert ctx.score_stats == []

    def test_sufficient_pairs_return_full_context(self):
        pairs = _make_pairs(4)
        ctx = compute_analytics(pairs, period_hours=48)
        assert ctx.article_count == 4
        assert ctx.period_hours == 48
        assert len(ctx.score_stats) == 5
        assert ctx.emotion_distribution.counts != {}
        assert ctx.topic_frequency.counts != {}

    def test_signals_present(self):
        pairs = _make_pairs(4, anxiety_score=0.8)
        ctx = compute_analytics(pairs)
        assert "anxiety_level" in ctx.signals
        assert ctx.signals["anxiety_level"] == "elevated"

    def test_default_period_hours(self):
        pairs = _make_pairs(4)
        ctx = compute_analytics(pairs)
        assert ctx.period_hours == 24

    def test_score_stats_to_dict(self):
        s = ScoreStats("anxiety", 0.7, 0.65, 0.8, 0.9, "rising")
        d = s.to_dict()
        assert d["dimension"] == "anxiety"
        assert d["trend_direction"] == "rising"
        assert "mean" in d

    def test_emotion_distribution_to_dict(self):
        ed = EmotionDistribution({"anxiety": 3})
        assert ed.to_dict() == {"counts": {"anxiety": 3}}

    def test_topic_frequency_to_dict(self):
        tf = TopicFrequency({"AI": 2})
        assert tf.to_dict() == {"counts": {"AI": 2}}

    def test_regional_breakdown_to_dict(self):
        rb = RegionalBreakdown({
            "Europe": {
                "count": 1,
                "mean_anxiety": 0.5,
                "mean_optimism": 0.3,
                "mean_conflict": 0.4,
                "mean_stability": 0.6,
            }
        })
        d = rb.to_dict()
        assert "Europe" in d["regions"]

    def test_narrative_phase_to_dict(self):
        np_ = NarrativePhase(["old"], ["new"], ["new"], ["old"])
        d = np_.to_dict()
        assert d["emerging"] == ["new"]
        assert d["fading"] == ["old"]


# --------------------------------------------------------------------------- #
#  AnalyticsContext.to_xml_block                                              #
# --------------------------------------------------------------------------- #


class TestAnalyticsContextToXmlBlock:
    def test_empty_context_produces_valid_xml(self):
        ctx = AnalyticsContext(article_count=0, period_hours=24)
        xml = ctx.to_xml_block()
        assert "<analytics>" in xml
        assert "</analytics>" in xml
        assert "<article_count>0</article_count>" in xml

    def test_full_context_includes_all_sections(self):
        pairs = _make_pairs(4)
        ctx = compute_analytics(pairs, period_hours=48)
        xml = ctx.to_xml_block()
        assert "<score_stats>" in xml
        assert "<dominant_emotions>" in xml
        assert "<top_topics>" in xml
        assert "<regional_breakdown>" in xml
        assert "<narrative_phases" in xml
        assert "<signals>" in xml

    def test_no_signals_block_when_signals_empty(self):
        ctx = AnalyticsContext(article_count=0, period_hours=0, signals={})
        xml = ctx.to_xml_block()
        assert "<signals>" not in xml

    def test_score_stats_rendered(self):
        pairs = _make_pairs(4, anxiety_score=0.7)
        ctx = compute_analytics(pairs)
        xml = ctx.to_xml_block()
        assert "dimension='anxiety'" in xml

    def test_regional_line_rendered(self):
        pairs = [
            _make_pair(url=f"https://x.com/{i}", region="Europe")
            for i in range(4)
        ]
        ctx = compute_analytics(pairs)
        xml = ctx.to_xml_block()
        assert "name='Europe'" in xml
