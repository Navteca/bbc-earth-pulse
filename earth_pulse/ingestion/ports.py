"""
FeedSourcePort — abstract interface all feed source adapters implement.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from earth_pulse.models import Article


class FeedSourcePort(ABC):
    source_name: str

    @abstractmethod
    async def fetch(self) -> list[Article]:
        """Fetch and normalize articles from this source. Returns empty list on failure."""
        ...  # pragma: no cover
