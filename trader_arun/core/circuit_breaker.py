"""Circuit breaker, rate limiter, exponential backoff with jitter.

All fail-closed: if the breaker is open, the caller must treat the provider as
unavailable and propagate NO-TRADE upstream.
"""
from __future__ import annotations

import asyncio
import random
import time
from collections import deque
from typing import Deque
from .logger import get_logger

log = get_logger("circuit")


class Backoff:
    """Exponential backoff with full jitter, capped."""

    __slots__ = ("_base", "_cap", "_factor", "_attempts")

    def __init__(self, base: float = 0.5, cap: float = 30.0, factor: float = 2.0) -> None:
        if base <= 0 or cap <= 0 or factor < 1.0:
            raise ValueError("invalid backoff parameters")
        self._base = float(base)
        self._cap = float(cap)
        self._factor = float(factor)
        self._attempts = 0

    def next_delay(self) -> float:
        delay = min(self._cap, self._base * (self._factor ** self._attempts))
        self._attempts += 1
        # Full jitter
        return random.uniform(0.0, delay)

    def reset(self) -> None:
        self._attempts = 0

    @property
    def attempts(self) -> int:
        return self._attempts


class RateLimiter:
    """Token-bucket rate limiter, async-safe."""

    __slots__ = ("_rate", "_burst", "_tokens", "_last_refill", "_lock")

    def __init__(self, rate_per_sec: float, burst: int | None = None) -> None:
        if rate_per_sec <= 0:
            raise ValueError("rate must be positive")
        self._rate = float(rate_per_sec)
        self._burst = int(burst) if burst else int(rate_per_sec)
        self._tokens = float(self._burst)
        self._last_refill = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self, n: int = 1) -> None:
        async with self._lock:
            while True:
                now = time.monotonic()
                elapsed = now - self._last_refill
                self._tokens = min(self._burst, self._tokens + elapsed * self._rate)
                self._last_refill = now
                if self._tokens >= n:
                    self._tokens -= n
                    return
                # Sleep until we have enough tokens.
                deficit = n - self._tokens
                sleep_for = deficit / self._rate
                await asyncio.sleep(min(sleep_for, 1.0))


class CircuitBreaker:
    """Time-decaying failure-count circuit breaker.

    State machine:
      - CLOSED   → calls flow normally
      - OPEN     → calls fail-closed immediately for `cool_down_sec`
      - HALF_OPEN → one trial call allowed; if it succeeds → CLOSED, else → OPEN
    """

    __slots__ = (
        "_name", "_failure_threshold", "_cool_down_sec",
        "_failure_times", "_lock", "_state", "_opened_at", "_half_open_trial_in_flight",
    )

    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        cool_down_sec: float = 30.0,
        failure_window_sec: float = 60.0,
    ) -> None:
        if failure_threshold <= 0:
            raise ValueError("failure_threshold must be positive")
        self._name = name
        self._failure_threshold = int(failure_threshold)
        self._cool_down_sec = float(cool_down_sec)
        self._failure_times: Deque[float] = deque()
        self._lock = asyncio.Lock()
        self._state = "CLOSED"
        self._opened_at = 0.0
        self._half_open_trial_in_flight = False

    @property
    def state(self) -> str:
        return self._state

    async def allow_request(self) -> bool:
        async with self._lock:
            if self._state == "CLOSED":
                return True
            if self._state == "OPEN":
                if time.monotonic() - self._opened_at >= self._cool_down_sec:
                    self._state = "HALF_OPEN"
                    self._half_open_trial_in_flight = True
                    return True
                return False
            # HALF_OPEN
            if self._half_open_trial_in_flight:
                return False
            self._half_open_trial_in_flight = True
            return True

    async def record_success(self) -> None:
        async with self._lock:
            if self._state == "HALF_OPEN":
                self._state = "CLOSED"
                self._half_open_trial_in_flight = False
                self._failure_times.clear()
                log.x_info("circuit recovered", extras={"breaker": self._name})

    async def record_failure(self) -> None:
        async with self._lock:
            now = time.monotonic()
            # Prune old failures.
            while self._failure_times and now - self._failure_times[0] > 60.0:
                self._failure_times.popleft()
            self._failure_times.append(now)
            if self._state == "HALF_OPEN":
                self._state = "OPEN"
                self._opened_at = now
                self._half_open_trial_in_flight = False
                log.x_warn("circuit re-opened after half-open failure",
                           extras={"breaker": self._name})
                return
            if len(self._failure_times) >= self._failure_threshold:
                self._state = "OPEN"
                self._opened_at = now
                log.x_warn("circuit opened",
                           extras={"breaker": self._name, "failures": len(self._failure_times)})

    def reset(self) -> None:
        self._state = "CLOSED"
        self._opened_at = 0.0
        self._failure_times.clear()
        self._half_open_trial_in_flight = False
