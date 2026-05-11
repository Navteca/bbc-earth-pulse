"""Unit tests for BBC RSS and BBC Unofficial adapters."""

from __future__ import annotations

import httpx
import respx
from httpx import Response

from earth_pulse.ingestion.bbc_rss import BBC_RSS_FEEDS, BBCRSSAdapter
from earth_pulse.ingestion.bbc_unofficial import BBCUnofficialAdapter

BBC_RSS_SAMPLE = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>BBC News - World</title>
    <item>
      <title>Global tensions rise</title>
      <link>https://www.bbc.co.uk/news/world-1</link>
      <description>Summary of world tensions</description>
      <pubDate>Mon, 11 May 2026 10:00:00 GMT</pubDate>
    </item>
    <item>
      <title>Climate report released</title>
      <link>https://www.bbc.co.uk/news/science-2</link>
      <description>New climate findings</description>
      <pubDate>Mon, 11 May 2026 09:00:00 GMT</pubDate>
    </item>
  </channel>
</rss>"""

BBC_UNOFFICIAL_SAMPLE = {
    "Top Stories": [
        {
            "title": "Breaking: major event",
            "news_link": "https://www.bbc.co.uk/news/breaking-99",
            "summary": "Event summary",
        }
    ]
}


class TestBBCRSSAdapter:
    @respx.mock
    async def test_fetch_returns_articles(self):
        # Mock all BBC RSS feed URLs
        for url, _, _ in BBC_RSS_FEEDS:
            respx.get(url).mock(return_value=Response(200, text=BBC_RSS_SAMPLE))
        async with httpx.AsyncClient() as client:
            adapter = BBCRSSAdapter(client=client)
            articles = await adapter.fetch()
        assert len(articles) > 0
        titles = [a.title for a in articles]
        assert "Global tensions rise" in titles

    @respx.mock
    async def test_fetch_skips_items_without_title(self):
        bad_rss = """<?xml version="1.0"?><rss version="2.0"><channel>
            <item><link>https://x.com/1</link></item>
        </channel></rss>"""
        for url, _, _ in BBC_RSS_FEEDS:
            respx.get(url).mock(return_value=Response(200, text=bad_rss))
        async with httpx.AsyncClient() as client:
            adapter = BBCRSSAdapter(client=client)
            articles = await adapter.fetch()
        assert articles == []

    @respx.mock
    async def test_fetch_handles_http_error_gracefully(self):
        for url, _, _ in BBC_RSS_FEEDS:
            respx.get(url).mock(return_value=Response(500))
        async with httpx.AsyncClient() as client:
            adapter = BBCRSSAdapter(client=client)
            articles = await adapter.fetch()
        assert articles == []

    def test_source_name(self):
        assert BBCRSSAdapter.source_name == "bbc_rss"


class TestBBCUnofficialAdapter:
    @respx.mock
    async def test_fetch_returns_articles(self):
        respx.get("https://bbc-news-api.vercel.app/news").mock(
            return_value=Response(200, json=BBC_UNOFFICIAL_SAMPLE)
        )
        async with httpx.AsyncClient() as client:
            adapter = BBCUnofficialAdapter(client=client)
            articles = await adapter.fetch()
        assert len(articles) > 0
        assert articles[0].title == "Breaking: major event"

    @respx.mock
    async def test_fetch_handles_non_dict_response(self):
        respx.get("https://bbc-news-api.vercel.app/news").mock(
            return_value=Response(200, json=[])
        )
        async with httpx.AsyncClient() as client:
            adapter = BBCUnofficialAdapter(client=client)
            articles = await adapter.fetch()
        assert articles == []

    @respx.mock
    async def test_fetch_skips_items_without_title_or_link(self):
        # Cover lines 58 (items not a list) and 63 (missing title/news_link)
        data = {
            "Top Stories": [
                {"title": "Only title no link"},  # missing news_link
                {"news_link": "https://bbc.co.uk/news/1"},  # missing title
            ],
            "Bad Category": "not a list",  # items not a list → line 58
        }
        respx.get("https://bbc-news-api.vercel.app/news").mock(
            return_value=Response(200, json=data)
        )
        async with httpx.AsyncClient() as client:
            adapter = BBCUnofficialAdapter(client=client)
            articles = await adapter.fetch()
        assert articles == []

    @respx.mock
    async def test_fetch_handles_http_error(self):
        respx.get("https://bbc-news-api.vercel.app/news").mock(
            return_value=Response(503)
        )
        async with httpx.AsyncClient() as client:
            adapter = BBCUnofficialAdapter(client=client)
            articles = await adapter.fetch()
        assert articles == []

    def test_source_name(self):
        assert BBCUnofficialAdapter.source_name == "bbc_unofficial"


# --- _parse_date coverage ---

class TestBBCRSSParseDate:
    def test_no_date_returns_now(self):
        from earth_pulse.ingestion.bbc_rss import _parse_date

        result = _parse_date(None)
        from datetime import datetime
        assert isinstance(result, datetime)
        assert result.tzinfo is not None

    def test_bad_date_returns_now(self):
        from earth_pulse.ingestion.bbc_rss import _parse_date

        result = _parse_date("not-a-date-at-all!!!")
        from datetime import datetime
        assert isinstance(result, datetime)


# --- no-client path coverage (creates own AsyncClient) ---

class TestAdaptersWithoutClient:
    @respx.mock
    async def test_bbc_rss_no_client_path(self):
        from earth_pulse.ingestion.bbc_rss import BBC_RSS_FEEDS, BBCRSSAdapter

        for url, _, _ in BBC_RSS_FEEDS:
            respx.get(url).mock(return_value=Response(200, text=BBC_RSS_SAMPLE))
        adapter = BBCRSSAdapter()  # no client
        articles = await adapter.fetch()
        assert len(articles) > 0

    @respx.mock
    async def test_bbc_unofficial_no_client_path(self):
        respx.get("https://bbc-news-api.vercel.app/news").mock(
            return_value=Response(200, json=BBC_UNOFFICIAL_SAMPLE)
        )
        adapter = BBCUnofficialAdapter()  # no client
        articles = await adapter.fetch()
        assert len(articles) > 0
