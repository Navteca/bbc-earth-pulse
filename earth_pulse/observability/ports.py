"""
ObservabilityPort — abstract interface for structured logging.
JSONLoggingAdapter — default implementation using stdlib logging with JSON output.
"""

from __future__ import annotations

import json
import logging
import sys
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from typing import Any


class ObservabilityPort(ABC):
    @abstractmethod
    def info(self, event: str, **kwargs: Any) -> None: ...

    @abstractmethod
    def warning(self, event: str, **kwargs: Any) -> None: ...

    @abstractmethod
    def error(self, event: str, **kwargs: Any) -> None: ...

    @abstractmethod
    def debug(self, event: str, **kwargs: Any) -> None: ...


class JSONLoggingAdapter(ObservabilityPort):
    """Emits structured JSON log lines to stdout."""

    def __init__(self, name: str = "earth_pulse", level: int = logging.INFO) -> None:
        self._logger = logging.getLogger(name)
        if not self._logger.handlers:
            handler = logging.StreamHandler(sys.stdout)
            handler.setFormatter(logging.Formatter("%(message)s"))
            self._logger.addHandler(handler)
        self._logger.setLevel(level)
        self._logger.propagate = False

    def _emit(self, level: str, event: str, **kwargs: Any) -> None:
        record = {
            "ts": datetime.now(tz=UTC).isoformat(),
            "level": level,
            "event": event,
            **kwargs,
        }
        line = json.dumps(record)
        getattr(self._logger, level.lower(), self._logger.info)(line)

    def info(self, event: str, **kwargs: Any) -> None:
        self._emit("INFO", event, **kwargs)

    def warning(self, event: str, **kwargs: Any) -> None:
        self._emit("WARNING", event, **kwargs)

    def error(self, event: str, **kwargs: Any) -> None:
        self._emit("ERROR", event, **kwargs)

    def debug(self, event: str, **kwargs: Any) -> None:
        self._emit("DEBUG", event, **kwargs)
