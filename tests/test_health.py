"""Tests for health monitor."""
import time

import pytest

from trader_arun.ops.health import HealthMonitor


def test_event_loop_lag_samples():
    hm = HealthMonitor()
    # First sample is baseline.
    hm.sample_event_loop_lag()
    # Without sleep, lag should be ~0.
    lag = hm.sample_event_loop_lag()
    assert lag < 0.5


def test_rss_mb_positive():
    hm = HealthMonitor()
    rss = hm.get_rss_mb()
    # Should report a positive value (this Python process is using RAM).
    assert rss > 0


def test_snapshot_returns_health_data():
    hm = HealthMonitor()
    snap = hm.snapshot(
        queue_hwm=100, task_count=10,
        cache_sizes={"trades": 200}, reconnect_count=0,
        provider_errors=0, signal_count=5, veto_count=1,
    )
    assert snap.timestamp > 0
    assert snap.rss_mb > 0
    assert snap.queue_hwm == 100
    assert snap.task_count == 10
    assert snap.signal_count == 5


def test_avg_loop_lag():
    hm = HealthMonitor()
    for _ in range(5):
        hm.sample_event_loop_lag()
    avg = hm.avg_loop_lag()
    assert avg >= 0.0
