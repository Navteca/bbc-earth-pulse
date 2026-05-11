"""Unit tests for circuit breaker."""

from __future__ import annotations

from earth_pulse.circuit_breaker import CircuitState, InMemoryCircuitBreakerAdapter


class TestCircuitBreaker:
    def test_initially_closed(self):
        cb = InMemoryCircuitBreakerAdapter()
        assert not cb.is_open("source_a")

    def test_opens_after_threshold_failures(self):
        cb = InMemoryCircuitBreakerAdapter()
        cb.record_failure("src")
        cb.record_failure("src")
        assert not cb.is_open("src")  # 2 failures, threshold is 3
        cb.record_failure("src")
        assert cb.is_open("src")  # now open

    def test_success_resets_to_closed(self):
        cb = InMemoryCircuitBreakerAdapter()
        for _ in range(3):
            cb.record_failure("src")
        cb.record_success("src")
        assert not cb.is_open("src")
        assert cb.status("src").state == CircuitState.CLOSED

    def test_skips_one_cycle_then_half_open(self):
        cb = InMemoryCircuitBreakerAdapter()
        for _ in range(3):
            cb.record_failure("src")
        assert cb.is_open("src")   # open, skip_cycles = 1 → 0
        assert not cb.is_open("src")  # transitions to HALF_OPEN

    def test_status_reports_failure_count(self):
        cb = InMemoryCircuitBreakerAdapter()
        cb.record_failure("src")
        cb.record_failure("src")
        status = cb.status("src")
        assert status.failure_count == 2
        assert status.source == "src"

    def test_independent_sources(self):
        cb = InMemoryCircuitBreakerAdapter()
        for _ in range(3):
            cb.record_failure("src_a")
        assert cb.is_open("src_a")
        assert not cb.is_open("src_b")
