"""
BBC RSS Feed adapter.
Fetches from multiple BBC RSS feed URLs, normalizes to Article.
Region is inferred from feed URL path when possible.
"""

from __future__ import annotations

import contextlib
import email.utils
from datetime import UTC, datetime

import feedparser
import httpx

from earth_pulse.ingestion.ports import FeedSourcePort
from earth_pulse.models import Article

# BBC RSS feeds — world + regional + topic
BBC_RSS_FEEDS: list[tuple[str, str | None, str | None]] = [
    # (url, region, category)
    ("https://feeds.bbci.co.uk/news/world/rss.xml", "Global", "world"),
    ("https://feeds.bbci.co.uk/news/world/africa/rss.xml", "Africa", "world"),
    ("https://feeds.bbci.co.uk/news/world/asia/rss.xml", "Asia", "world"),
    ("https://feeds.bbci.co.uk/news/world/europe/rss.xml", "Europe", "world"),
    ("https://feeds.bbci.co.uk/news/world/latin_america/rss.xml", "Latin America", "world"),
    ("https://feeds.bbci.co.uk/news/world/middle_east/rss.xml", "Middle East", "world"),
    ("https://feeds.bbci.co.uk/news/world/us_and_canada/rss.xml", "North America", "world"),
    ("https://feeds.bbci.co.uk/news/technology/rss.xml", None, "technology"),
    ("https://feeds.bbci.co.uk/news/science_and_environment/rss.xml", None, "science"),
    ("https://feeds.bbci.co.uk/news/business/rss.xml", None, "business"),
    ("https://feeds.bbci.co.uk/news/health/rss.xml", None, "health"),
    ("https://feeds.bbci.co.uk/news/politics/rss.xml", "Europe", "politics"),
]


def _parse_date(date_str: str | None) -> datetime:
    if not date_str:
        return datetime.now(tz=UTC)
    try:
        parsed = email.utils.parsedate_to_datetime(date_str)
        return parsed.astimezone(UTC)
    except Exception:
        return datetime.now(tz=UTC)


class BBCRSSAdapter(FeedSourcePort):
    source_name = "bbc_rss"

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client

    async def fetch(self) -> list[Article]:
        articles: list[Article] = []
        for feed_url, region, category in BBC_RSS_FEEDS:
            with contextlib.suppress(Exception):
                articles.extend(await self._fetch_feed(feed_url, region, category))
        return articles

    async def _fetch_feed(
        self, url: str, region: str | None, category: str | None
    ) -> list[Article]:
        if self._client:
            response = await self._client.get(url, timeout=15.0)
            response.raise_for_status()
            content = response.text
        else:
            async with httpx.AsyncClient() as client:
                response = await client.get(url, timeout=15.0)
                response.raise_for_status()
                content = response.text

        feed = feedparser.parse(content)
        articles = []
        for entry in feed.entries:
            title = getattr(entry, "title", None)
            link = getattr(entry, "link", None)
            if not title or not link:
                continue
            summary = getattr(entry, "summary", None)
            published = _parse_date(getattr(entry, "published", None))
            articles.append(
                Article.build(
                    title=title,
                    url=link,
                    source=self.source_name,
                    published_at=published,
                    summary=summary,
                    region=region,
                    category=category,
                )
            )
        return articles
