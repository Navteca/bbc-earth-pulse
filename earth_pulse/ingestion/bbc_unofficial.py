"""
BBC Unofficial Vercel API adapter.
Best-effort secondary source. No SLA. Min poll floor: 30 minutes.
https://bbc-news-api.vercel.app
"""

from __future__ import annotations

import contextlib
from datetime import UTC, datetime

import httpx

from earth_pulse.ingestion.ports import FeedSourcePort
from earth_pulse.models import Article

BBC_UNOFFICIAL_BASE = "https://bbc-news-api.vercel.app"

# Endpoints to fetch (lang=english only for MVP)
_ENDPOINTS: list[tuple[str, str | None]] = [
    ("/news?lang=english", "Global"),
    ("/news?lang=english&region=world", "Global"),
]


class BBCUnofficialAdapter(FeedSourcePort):
    source_name = "bbc_unofficial"

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client

    async def fetch(self) -> list[Article]:
        articles: list[Article] = []
        for path, region in _ENDPOINTS:
            with contextlib.suppress(Exception):
                articles.extend(await self._fetch_endpoint(path, region))
        return articles

    async def _fetch_endpoint(self, path: str, region: str | None) -> list[Article]:
        url = f"{BBC_UNOFFICIAL_BASE}{path}"
        if self._client:
            response = await self._client.get(url, timeout=15.0)
            response.raise_for_status()
            data = response.json()
        else:
            async with httpx.AsyncClient() as client:
                response = await client.get(url, timeout=15.0)
                response.raise_for_status()
                data = response.json()

        # The API returns a dict with category keys each containing list of news items
        articles = []
        if not isinstance(data, dict):
            return articles

        for _category, items in data.items():
            if not isinstance(items, list):
                continue
            for item in items:
                title = item.get("title")
                news_link = item.get("news_link")
                if not title or not news_link:
                    continue
                summary = item.get("summary")
                articles.append(
                    Article.build(
                        title=title,
                        url=news_link,
                        source=self.source_name,
                        published_at=datetime.now(tz=UTC),
                        summary=summary,
                        region=region,
                    )
                )
        return articles
