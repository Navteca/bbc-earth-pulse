"""
Canonical Article dataclass — the normalized model all sources produce.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass
from datetime import UTC, datetime

VALID_REGIONS = frozenset(
    [
        "Africa",
        "Asia",
        "Europe",
        "Latin America",
        "Middle East",
        "North America",
        "Oceania",
        "Global",
    ]
)

VALID_EMOTIONS = frozenset(
    [
        "anxiety",
        "optimism",
        "fear",
        "uncertainty",
        "resilience",
        "hope",
        "instability",
        "caution",
        "confidence",
        "tension",
        "inspiration",
        "exhaustion",
        "polarization",
    ]
)


@dataclass
class Article:
    id: str
    title: str
    summary: str | None
    body_text: str | None
    url: str
    url_hash: str
    title_hash: str
    source: str
    region: str | None
    category: str | None
    language: str
    published_at: datetime
    ingested_at: datetime

    @classmethod
    def make_url_hash(cls, url: str) -> str:
        return hashlib.sha256(url.strip().encode()).hexdigest()

    @classmethod
    def make_title_hash(cls, title: str) -> str:
        normalized = unicodedata.normalize("NFKD", title.lower())
        normalized = re.sub(r"[^\w\s]", "", normalized)
        normalized = re.sub(r"\s+", " ", normalized).strip()
        return hashlib.sha256(normalized.encode()).hexdigest()

    @classmethod
    def make_id(cls, url: str) -> str:
        return cls.make_url_hash(url)

    @classmethod
    def build(
        cls,
        title: str,
        url: str,
        source: str,
        published_at: datetime,
        summary: str | None = None,
        body_text: str | None = None,
        region: str | None = None,
        category: str | None = None,
        language: str = "en",
    ) -> Article:
        url = url.strip()
        now = datetime.now(tz=UTC)
        return cls(
            id=cls.make_id(url),
            title=title,
            summary=summary,
            body_text=body_text,
            url=url,
            url_hash=cls.make_url_hash(url),
            title_hash=cls.make_title_hash(title),
            source=source,
            region=region,
            category=category,
            language=language,
            published_at=published_at,
            ingested_at=now,
        )


@dataclass
class Enrichment:
    article_id: str
    emotion: str
    topics: list[str]
    narratives: list[str]
    region: str | None
    urgency_score: float
    anxiety_score: float
    optimism_score: float
    conflict_score: float
    stability_score: float
    enriched_at: datetime
    enrichment_failed: bool = False
    failure_reason: str | None = None
    retry_count: int = 0
