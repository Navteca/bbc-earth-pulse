"""
Pre-computed analytics context injected into every GPT synthesis prompt.

compute_analytics() takes the enriched article pairs already fetched for a tool
call and derives rich statistical context — score distributions, trend direction,
emotion distribution, topic frequency, regional breakdown, and narrative phases —
without issuing any additional DB queries.

The resulting AnalyticsContext is serialised into an <analytics> XML block that
is prepended to the <articles> block in every synthesis prompt, giving GPT the
quantitative scaffolding it needs to answer civilizational-level questions
accurately (anxiety rising/falling, dominant fears, optimism signals, narrative
phase shifts, cross-region comparisons).
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field

from earth_pulse.models import Article, Enrichment

# Minimum articles required before we attempt analytics (avoids division-by-zero
# and misleading signals on tiny datasets).
_MIN_ARTICLES = 2


# --------------------------------------------------------------------------- #
#  Score statistics per dimension                                              #
# --------------------------------------------------------------------------- #


@dataclass
class ScoreStats:
    """Descriptive statistics for one emotional score dimension."""

    dimension: str
    mean: float
    median: float
    p75: float
    p90: float
    # trend_direction: "rising" | "falling" | "stable"
    # Computed by comparing first-half vs second-half mean of chronologically
    # sorted articles.  Requires ≥ 4 articles; otherwise "unknown".
    trend_direction: str

    def to_dict(self) -> dict[str, object]:
        return {
            "dimension": self.dimension,
            "mean": round(self.mean, 3),
            "median": round(self.median, 3),
            "p75": round(self.p75, 3),
            "p90": round(self.p90, 3),
            "trend_direction": self.trend_direction,
        }


# --------------------------------------------------------------------------- #
#  Supporting distribution types                                               #
# --------------------------------------------------------------------------- #


@dataclass
class EmotionDistribution:
    """Ranked emotion label counts."""

    counts: dict[str, int]  # emotion → count, sorted by count desc

    def to_dict(self) -> dict[str, object]:
        return {"counts": self.counts}


@dataclass
class TopicFrequency:
    """Top topics by article count, limited to 15 entries."""

    counts: dict[str, int]

    def to_dict(self) -> dict[str, object]:
        return {"counts": self.counts}


@dataclass
class RegionalBreakdown:
    """Per-region score means and article count."""

    regions: dict[str, dict[str, object]]  # region → {count, mean_anxiety, mean_optimism, …}

    def to_dict(self) -> dict[str, object]:
        return {"regions": self.regions}


@dataclass
class NarrativePhase:
    """Narrative labels split into early / recent halves for arc detection."""

    early: list[str]
    recent: list[str]
    # Narratives that appear in recent but not early (emerging).
    emerging: list[str]
    # Narratives that appeared in early but not recent (fading).
    fading: list[str]

    def to_dict(self) -> dict[str, object]:
        return {
            "early": self.early,
            "recent": self.recent,
            "emerging": self.emerging,
            "fading": self.fading,
        }


@dataclass
class AnalyticsContext:
    """Full pre-computed analytics object passed into synthesis."""

    article_count: int
    period_hours: int
    score_stats: list[ScoreStats] = field(default_factory=list)
    emotion_distribution: EmotionDistribution = field(
        default_factory=lambda: EmotionDistribution({})
    )
    topic_frequency: TopicFrequency = field(default_factory=lambda: TopicFrequency({}))
    regional_breakdown: RegionalBreakdown = field(
        default_factory=lambda: RegionalBreakdown({})
    )
    narrative_phases: NarrativePhase = field(
        default_factory=lambda: NarrativePhase([], [], [], [])
    )
    # High-level signals derived from the above.
    signals: dict[str, str] = field(default_factory=dict)

    def to_xml_block(self) -> str:
        """Serialise to an <analytics> XML block for injection into GPT prompts."""
        lines: list[str] = ["<analytics>"]
        lines.append(f"  <article_count>{self.article_count}</article_count>")
        lines.append(f"  <period_hours>{self.period_hours}</period_hours>")

        lines.append("  <score_stats>")
        for s in self.score_stats:
            lines.append(
                f"    <score dimension='{s.dimension}' mean='{s.mean:.3f}'"
                f" median='{s.median:.3f}' p75='{s.p75:.3f}' p90='{s.p90:.3f}'"
                f" trend='{s.trend_direction}'/>"
            )
        lines.append("  </score_stats>")

        # Emotion distribution — top 5
        top_emotions = list(self.emotion_distribution.counts.items())[:5]
        emo_str = " | ".join(f"{k}:{v}" for k, v in top_emotions)
        lines.append(f"  <dominant_emotions>{emo_str}</dominant_emotions>")

        # Topic frequency — top 10
        top_topics = list(self.topic_frequency.counts.items())[:10]
        topic_str = " | ".join(f"{k}:{v}" for k, v in top_topics)
        lines.append(f"  <top_topics>{topic_str}</top_topics>")

        # Regional breakdown
        lines.append("  <regional_breakdown>")
        for region, stats in self.regional_breakdown.regions.items():
            lines.append(
                f"    <region name='{region}' count='{stats['count']}'"
                f" mean_anxiety='{stats['mean_anxiety']:.3f}'"
                f" mean_optimism='{stats['mean_optimism']:.3f}'"
                f" mean_conflict='{stats['mean_conflict']:.3f}'"
                f" mean_stability='{stats['mean_stability']:.3f}'/>"
            )
        lines.append("  </regional_breakdown>")

        # Narrative phases
        np_ = self.narrative_phases
        lines.append(
            f"  <narrative_phases"
            f" emerging='{', '.join(np_.emerging)}'"
            f" fading='{', '.join(np_.fading)}'/>"
        )

        # Signals
        if self.signals:
            lines.append("  <signals>")
            for k, v in self.signals.items():
                lines.append(f"    <signal key='{k}'>{v}</signal>")
            lines.append("  </signals>")

        lines.append("</analytics>")
        return "\n".join(lines)


# --------------------------------------------------------------------------- #
#  Internal helpers                                                            #
# --------------------------------------------------------------------------- #


def _percentile(values: list[float], p: float) -> float:
    """Return the p-th percentile (0–100) of a sorted list."""
    if not values:
        return 0.0
    sorted_vals = sorted(values)
    idx = (p / 100) * (len(sorted_vals) - 1)
    lo = int(idx)
    hi = min(lo + 1, len(sorted_vals) - 1)
    frac = idx - lo
    return sorted_vals[lo] + frac * (sorted_vals[hi] - sorted_vals[lo])


def _trend_direction(chronological_scores: list[float]) -> str:
    """Compare first-half vs second-half mean to determine trend direction."""
    n = len(chronological_scores)
    if n < 4:
        return "unknown"
    mid = n // 2
    early_mean = statistics.mean(chronological_scores[:mid])
    recent_mean = statistics.mean(chronological_scores[mid:])
    delta = recent_mean - early_mean
    if delta > 0.05:
        return "rising"
    if delta < -0.05:
        return "falling"
    return "stable"


def _compute_score_stats(
    pairs: list[tuple[Article, Enrichment]],
    chronological_pairs: list[tuple[Article, Enrichment]],
) -> list[ScoreStats]:
    dimensions = [
        ("anxiety", "anxiety_score"),
        ("optimism", "optimism_score"),
        ("conflict", "conflict_score"),
        ("stability", "stability_score"),
        ("urgency", "urgency_score"),
    ]
    results = []
    for label, attr in dimensions:
        values = [getattr(e, attr) for _, e in pairs]
        chrono_values = [getattr(e, attr) for _, e in chronological_pairs]
        if not values:
            results.append(
                ScoreStats(label, 0.0, 0.0, 0.0, 0.0, "unknown")
            )
            continue
        results.append(
            ScoreStats(
                dimension=label,
                mean=statistics.mean(values),
                median=statistics.median(values),
                p75=_percentile(values, 75),
                p90=_percentile(values, 90),
                trend_direction=_trend_direction(chrono_values),
            )
        )
    return results


def _compute_emotion_distribution(
    pairs: list[tuple[Article, Enrichment]],
) -> EmotionDistribution:
    counts: dict[str, int] = {}
    for _, e in pairs:
        if e.emotion:
            counts[e.emotion] = counts.get(e.emotion, 0) + 1
    sorted_counts = dict(sorted(counts.items(), key=lambda x: x[1], reverse=True))
    return EmotionDistribution(sorted_counts)


def _compute_topic_frequency(
    pairs: list[tuple[Article, Enrichment]],
) -> TopicFrequency:
    counts: dict[str, int] = {}
    for _, e in pairs:
        for topic in e.topics:
            if topic:
                counts[topic] = counts.get(topic, 0) + 1
    top = dict(sorted(counts.items(), key=lambda x: x[1], reverse=True)[:15])
    return TopicFrequency(top)


def _compute_regional_breakdown(
    pairs: list[tuple[Article, Enrichment]],
) -> RegionalBreakdown:
    buckets: dict[str, list[Enrichment]] = {}
    for a, e in pairs:
        region = e.region or a.region or "Unknown"
        buckets.setdefault(region, []).append(e)

    regions: dict[str, dict[str, object]] = {}
    for region, enrichments in sorted(buckets.items()):
        n = len(enrichments)
        regions[region] = {
            "count": n,
            "mean_anxiety": statistics.mean(e.anxiety_score for e in enrichments),
            "mean_optimism": statistics.mean(e.optimism_score for e in enrichments),
            "mean_conflict": statistics.mean(e.conflict_score for e in enrichments),
            "mean_stability": statistics.mean(e.stability_score for e in enrichments),
        }
    return RegionalBreakdown(regions)


def _compute_narrative_phases(
    chronological_pairs: list[tuple[Article, Enrichment]],
) -> NarrativePhase:
    n = len(chronological_pairs)
    if n < 2:
        all_narratives: list[str] = []
        for _, e in chronological_pairs:
            all_narratives.extend(e.narratives)
        return NarrativePhase(all_narratives, all_narratives, [], [])

    mid = n // 2
    early_pairs = chronological_pairs[:mid]
    recent_pairs = chronological_pairs[mid:]

    early_set: set[str] = set()
    for _, e in early_pairs:
        early_set.update(e.narratives)

    recent_set: set[str] = set()
    for _, e in recent_pairs:
        recent_set.update(e.narratives)

    return NarrativePhase(
        early=sorted(early_set),
        recent=sorted(recent_set),
        emerging=sorted(recent_set - early_set),
        fading=sorted(early_set - recent_set),
    )


def _compute_signals(
    score_stats: list[ScoreStats],
    emotion_dist: EmotionDistribution,
) -> dict[str, str]:
    signals: dict[str, str] = {}
    stats_by_dim = {s.dimension: s for s in score_stats}

    anxiety = stats_by_dim.get("anxiety")
    if anxiety:
        if anxiety.mean > 0.65:
            signals["anxiety_level"] = "elevated"
        elif anxiety.mean < 0.35:
            signals["anxiety_level"] = "low"
        else:
            signals["anxiety_level"] = "moderate"
        if anxiety.trend_direction != "unknown":
            signals["anxiety_trend"] = anxiety.trend_direction

    optimism = stats_by_dim.get("optimism")
    if optimism:
        if optimism.mean > 0.55:
            signals["optimism_level"] = "high"
        elif optimism.mean < 0.3:
            signals["optimism_level"] = "low"
        else:
            signals["optimism_level"] = "moderate"
        if optimism.trend_direction != "unknown":
            signals["optimism_trend"] = optimism.trend_direction

    conflict = stats_by_dim.get("conflict")
    if conflict and conflict.mean > 0.6:
        signals["conflict_elevated"] = "true"

    # Dominant emotion
    if emotion_dist.counts:
        dominant = next(iter(emotion_dist.counts))
        signals["dominant_emotion"] = dominant

    return signals


# --------------------------------------------------------------------------- #
#  Public API                                                                  #
# --------------------------------------------------------------------------- #


def compute_analytics(
    pairs: list[tuple[Article, Enrichment]],
    period_hours: int = 24,
) -> AnalyticsContext:
    """
    Derive an AnalyticsContext from enriched article pairs with no extra DB queries.

    pairs: as returned by db.get_enriched_articles() or db.get_timeline_articles().
    period_hours: the time window the pairs represent (informational, passed through).
    """
    n = len(pairs)

    if n < _MIN_ARTICLES:
        return AnalyticsContext(article_count=n, period_hours=period_hours)

    # Chronological order for trend detection and narrative phasing.
    chronological = sorted(pairs, key=lambda p: p[0].published_at)

    score_stats = _compute_score_stats(pairs, chronological)
    emotion_dist = _compute_emotion_distribution(pairs)
    topic_freq = _compute_topic_frequency(pairs)
    regional = _compute_regional_breakdown(pairs)
    narrative_phases = _compute_narrative_phases(chronological)
    signals = _compute_signals(score_stats, emotion_dist)

    return AnalyticsContext(
        article_count=n,
        period_hours=period_hours,
        score_stats=score_stats,
        emotion_distribution=emotion_dist,
        topic_frequency=topic_freq,
        regional_breakdown=regional,
        narrative_phases=narrative_phases,
        signals=signals,
    )
