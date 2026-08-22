"""Tests for circuit breaker, rate limiter, backoff."""
import asyncio
import time

import pytest

from trader_arun.core.circuit_breaker import Backoff, CircuitBreaker, RateLimiter


def test_backoff_increases_then_resets():
    b = Backoff(base=0.1, cap=10.0, factor=2.0)
    delays = [b.next_delay() for _ in range(5)]
    # Delays should not exceed cap.
    assert all(d <= 10.0 for d in delays)
    b.reset()
    assert b.attempts == 0


@pytest.mark.asyncio
async def test_rate_limiter_basic():
    rl = RateLimiter(rate_per_sec=10.0, burst=2)
    # First two should be instant (burst).
    start = time.monotonic()
    await rl.acquire()
    await rl.acquire()
    elapsed = time.monotonic() - start
    assert elapsed < 0.05


@pytest.mark.asyncio
async def test_rate_limiter_throttles():
    rl = RateLimiter(rate_per_sec=5.0, burst=1)
    await rl.acquire()  # consumes the only burst token
    start = time.monotonic()
    await rl.acquire()  # has to wait ~0.2s for next token
    elapsed = time.monotonic() - start
    assert elapsed >= 0.15


@pytest.mark.asyncio
async def test_circuit_breaker_opens_after_threshold():
    cb = CircuitBreaker(name="test", failure_threshold=3, cool_down_sec=1.0)
    # Initially closed.
    assert await cb.allow_request() is True
    # Record 3 failures.
    for _ in range(3):
        await cb.record_failure()
    # Should now be OPEN.
    assert await cb.allow_request() is False


@pytest.mark.asyncio
async def test_circuit_breaker_half_open_recovery():
    cb = CircuitBreaker(name="test", failure_threshold=2, cool_down_sec=0.1)
    await cb.record_failure()
    await cb.record_failure()
    assert await cb.allow_request() is False
    # Wait for cool-down.
    await asyncio.sleep(0.15)
    # Should transition to HALF_OPEN and allow one trial.
    assert await cb.allow_request() is True
    # On success → CLOSED.
    await cb.record_success()
    assert cb.state == "CLOSED"


@pytest.mark.asyncio
async def test_circuit_breaker_half_open_failure_reopens():
    cb = CircuitBreaker(name="test", failure_threshold=2, cool_down_sec=0.05)
    await cb.record_failure()
    await cb.record_failure()
    await asyncio.sleep(0.06)
    assert await cb.allow_request() is True  # HALF_OPEN trial
    await cb.record_failure()  # trial failed
    assert cb.state == "OPEN"
