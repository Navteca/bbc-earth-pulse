"""
SchedulerPort — abstract interface for job scheduling.
APSchedulerAdapter — default implementation. Swappable with CeleryAdapter in Phase 2.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler


class SchedulerPort(ABC):
    @abstractmethod
    def add_job(
        self,
        func: Callable,
        interval_minutes: int,
        job_id: str,
        **kwargs: Any,
    ) -> None: ...

    @abstractmethod
    def start(self) -> None: ...

    @abstractmethod
    def shutdown(self) -> None: ...


class APSchedulerAdapter(SchedulerPort):
    """AsyncIO-based APScheduler. Swappable with CeleryAdapter in Phase 2."""

    def __init__(self) -> None:
        self._scheduler = AsyncIOScheduler()

    def add_job(
        self,
        func: Callable,
        interval_minutes: int,
        job_id: str,
        **kwargs: Any,
    ) -> None:
        self._scheduler.add_job(
            func,
            trigger="interval",
            minutes=interval_minutes,
            id=job_id,
            replace_existing=True,
            **kwargs,
        )

    def start(self) -> None:
        self._scheduler.start()

    def shutdown(self) -> None:
        self._scheduler.shutdown(wait=False)
