"""Unit tests for scheduler ports."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from earth_pulse.scheduler import APSchedulerAdapter


class TestAPSchedulerAdapter:
    def test_add_job_and_start_shutdown(self):
        with patch("earth_pulse.scheduler.ports.AsyncIOScheduler") as mock_sched_cls:
            mock_sched = MagicMock()
            mock_sched_cls.return_value = mock_sched
            adapter = APSchedulerAdapter()
            adapter.add_job(lambda: None, interval_minutes=15, job_id="test")
            adapter.start()
            adapter.shutdown()
            mock_sched.add_job.assert_called_once()
            mock_sched.start.assert_called_once()
            mock_sched.shutdown.assert_called_once()

    def test_add_job_uses_interval_trigger(self):
        with patch("earth_pulse.scheduler.ports.AsyncIOScheduler") as mock_sched_cls:
            mock_sched = MagicMock()
            mock_sched_cls.return_value = mock_sched
            adapter = APSchedulerAdapter()
            fn = lambda: None  # noqa: E731
            adapter.add_job(fn, interval_minutes=30, job_id="myjob")
            call_kwargs = mock_sched.add_job.call_args
            assert call_kwargs.kwargs["trigger"] == "interval"
            assert call_kwargs.kwargs["minutes"] == 30
            assert call_kwargs.kwargs["id"] == "myjob"
