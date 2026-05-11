"""
CircuitBreakerPort — abstract interface for per-source circuit breakers.
InMemoryCircuitBreakerAdapter — default in-process implementation.

States: CLOSED (normal) → OPEN (failing, skip) → HALF_OPEN (retry probe)
Transition: 3 consecutive failures → OPEN; after one cycle skip → HALF_OPEN → probe;
success → CLOSED, failure → OPEN again.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum


class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class CircuitStatus:
    state: CircuitState
    failure_count: int
    source: str


class CircuitBreakerPort(ABC):
    @abstractmethod
    def record_success(self, source: str) -> None: ...

    @abstractmethod
    def record_failure(self, source: str) -> None: ...

    @abstractmethod
    def is_open(self, source: str) -> bool: ...

    @abstractmethod
    def status(self, source: str) -> CircuitStatus: ...


@dataclass
class _SourceState:
    state: CircuitState = CircuitState.CLOSED
    failure_count: int = 0
    skip_cycles_remaining: int = 0


class InMemoryCircuitBreakerAdapter(CircuitBreakerPort):
    """In-memory circuit breaker. Swappable with RedisCircuitBreakerAdapter in Phase 2."""

    FAILURE_THRESHOLD = 3
    SKIP_CYCLES = 1

    def __init__(self) -> None:
        self._states: dict[str, _SourceState] = {}

    def _get(self, source: str) -> _SourceState:
        if source not in self._states:
            self._states[source] = _SourceState()
        return self._states[source]

    def record_success(self, source: str) -> None:
        s = self._get(source)
        s.state = CircuitState.CLOSED
        s.failure_count = 0
        s.skip_cycles_remaining = 0

    def record_failure(self, source: str) -> None:
        s = self._get(source)
        s.failure_count += 1
        if s.failure_count >= self.FAILURE_THRESHOLD:
            s.state = CircuitState.OPEN
            s.skip_cycles_remaining = self.SKIP_CYCLES

    def is_open(self, source: str) -> bool:
        s = self._get(source)
        if s.state == CircuitState.OPEN:
            if s.skip_cycles_remaining > 0:
                s.skip_cycles_remaining -= 1
                return True
            # Transition to HALF_OPEN to allow one probe attempt
            s.state = CircuitState.HALF_OPEN
            return False
        return False

    def status(self, source: str) -> CircuitStatus:
        s = self._get(source)
        return CircuitStatus(state=s.state, failure_count=s.failure_count, source=source)
