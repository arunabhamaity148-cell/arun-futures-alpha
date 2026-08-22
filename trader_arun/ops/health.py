"""Health monitor — RSS, CPU, event-loop lag, queue HWM, tasks, cache size."""
from __future__ import annotations

import asyncio
import os
import resource
import time
from dataclasses import dataclass, field
from typing import Any

from ..core.logger import get_logger

log = get_logger("health")


@dataclass
class HealthSnapshot:
    timestamp: float
    rss_mb: float
    cpu_percent: float = 0.0
    event_loop_lag_sec: float = 0.0
    queue_hwm: int = 0
    task_count: int = 0
    cache_sizes: dict[str, int] = field(default_factory=dict)
    reconnect_count: int = 0
    provider_errors: int = 0
    signal_count: int = 0
    veto_count: int = 0
    extra: dict[str, Any] = field(default_factory=dict)


class HealthMonitor:
    """Lightweight async health monitor."""

    def __init__(
        self,
        rss_warning_mb: int = 350,
        rss_critical_mb: int = 600,
        event_loop_lag_warning_sec: float = 0.5,
        event_loop_lag_critical_sec: float = 2.0,
    ) -> None:
        self._rss_warn = int(rss_warning_mb)
        self._rss_crit = int(rss_critical_mb)
        self._loop_warn = float(event_loop_lag_warning_sec)
        self._loop_crit = float(event_loop_lag_critical_sec)
        self._last_loop_time = time.monotonic()
        self._loop_lag_samples: list[float] = []
        self._max_loop_samples = 60

    def sample_event_loop_lag(self) -> float:
        now = time.monotonic()
        lag = max(0.0, now - self._last_loop_time - 0.1)  # subtract expected 100ms
        self._last_loop_time = now
        self._loop_lag_samples.append(lag)
        if len(self._loop_lag_samples) > self._max_loop_samples:
            self._loop_lag_samples = self._loop_lag_samples[-self._max_loop_samples:]
        return lag

    def get_rss_mb(self) -> float:
        try:
            usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            # On Linux ru_maxrss is in KB; on macOS it's in bytes.
            if usage > 10_000_000:  # heuristic: bytes
                return usage / 1024 / 1024
            return usage / 1024
        except (AttributeError, OSError):
            return 0.0

    def snapshot(
        self,
        queue_hwm: int = 0,
        task_count: int = 0,
        cache_sizes: dict[str, int] | None = None,
        reconnect_count: int = 0,
        provider_errors: int = 0,
        signal_count: int = 0,
        veto_count: int = 0,
        extra: dict[str, Any] | None = None,
    ) -> HealthSnapshot:
        lag = self.sample_event_loop_lag()
        rss = self.get_rss_mb()
        snap = HealthSnapshot(
            timestamp=time.time(),
            rss_mb=rss,
            event_loop_lag_sec=lag,
            queue_hwm=queue_hwm,
            task_count=task_count,
            cache_sizes=cache_sizes or {},
            reconnect_count=reconnect_count,
            provider_errors=provider_errors,
            signal_count=signal_count,
            veto_count=veto_count,
            extra=extra or {},
        )
        if rss > self._rss_crit:
            log.x_error("RSS CRITICAL", extras={"rss_mb": rss, "critical": self._rss_crit})
        elif rss > self._rss_warn:
            log.x_warn("RSS high", extras={"rss_mb": rss, "warning": self._rss_warn})
        if lag > self._loop_crit:
            log.x_error("event loop lag CRITICAL", extras={"lag_sec": lag})
        elif lag > self._loop_warn:
            log.x_warn("event loop lag high", extras={"lag_sec": lag})
        return snap

    def avg_loop_lag(self) -> float:
        if not self._loop_lag_samples:
            return 0.0
        return sum(self._loop_lag_samples) / len(self._loop_lag_samples)
