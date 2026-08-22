"""Provider base classes, registry, schema validator.

Every provider:
- has connection / schema validation / timestamp checks / stale detection
- bounded retry/backoff+jitter
- rate limiting
- circuit breaker
- reconnect (for WS)
- health status
- graceful shutdown
"""
from __future__ import annotations

import abc
import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

import aiohttp

from ..core.circuit_breaker import CircuitBreaker, RateLimiter, Backoff
from ..core.exceptions import (
    ProviderError,
    ProviderUnavailable,
    SchemaError,
    StaleDataError,
)
from ..core.logger import get_logger
from ..core.time_utils import now_mono, now_ts
from ..core.types import ProviderHealth, ProviderState

log = get_logger("provider")


class SchemaValidator:
    """Lightweight schema validator — required keys and types only."""

    @staticmethod
    def validate(payload: Any, schema: dict[str, type]) -> None:
        if not isinstance(payload, dict):
            raise SchemaError(f"expected dict, got {type(payload).__name__}")
        for key, typ in schema.items():
            if key not in payload:
                raise SchemaError(f"missing key {key!r}")
            if not isinstance(payload[key], typ):
                # bool is subclass of int — accept either.
                if typ in (int, float) and isinstance(payload[key], (int, float)):
                    continue
                raise SchemaError(
                    f"key {key!r} expected {typ.__name__}, got {type(payload[key]).__name__}"
                )


@dataclass
class ProviderStats:
    name: str
    requests_total: int = 0
    successes_total: int = 0
    failures_total: int = 0
    last_success: float = 0.0
    last_failure: float = 0.0
    latency_samples: list[float] = field(default_factory=list)
    state: ProviderState = ProviderState.HEALTHY

    def record_success(self, latency_sec: float) -> None:
        self.requests_total += 1
        self.successes_total += 1
        self.last_success = now_ts()
        if len(self.latency_samples) >= 200:
            self.latency_samples = self.latency_samples[100:]
        self.latency_samples.append(latency_sec)
        if self.state == ProviderState.DEGRADED and self.successes_total % 5 == 0:
            self.state = ProviderState.HEALTHY

    def record_failure(self) -> None:
        self.requests_total += 1
        self.failures_total += 1
        self.last_failure = now_ts()
        self.state = ProviderState.DEGRADED

    def p95_latency(self) -> float:
        if not self.latency_samples:
            return 0.0
        s = sorted(self.latency_samples)
        return s[int(0.95 * (len(s) - 1))]

    def health(self) -> ProviderHealth:
        return ProviderHealth(
            name=self.name,
            state=self.state,
            last_success=self.last_success,
            last_failure=self.last_failure,
            failures_in_window=self.failures_total,
            circuit_state="N/A",
            latency_p95_sec=self.p95_latency(),
            timestamp=now_ts(),
        )


class Provider(abc.ABC):
    """Abstract base class for all data providers."""

    name: str = "abstract"

    def __init__(
        self,
        session: aiohttp.ClientSession | None = None,
        request_timeout_sec: float = 8.0,
        rate_per_sec: float = 5.0,
        failure_threshold: int = 5,
        cool_down_sec: float = 30.0,
    ) -> None:
        self._session = session
        self._owns_session = session is None
        self._timeout = aiohttp.ClientTimeout(total=request_timeout_sec)
        self._rate_limiter = RateLimiter(rate_per_sec=rate_per_sec)
        self._breaker = CircuitBreaker(
            name=self.name,
            failure_threshold=failure_threshold,
            cool_down_sec=cool_down_sec,
        )
        self._backoff = Backoff()
        self._stats = ProviderStats(name=self.name)
        self._closed = False
        self._ws_reconnect_attempts = 0
        self._max_ws_reconnect_attempts = 50

    @property
    def stats(self) -> ProviderStats:
        return self._stats

    @property
    def breaker(self) -> CircuitBreaker:
        return self._breaker

    async def __aenter__(self) -> "Provider":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.close()

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._owns_session and self._session is not None:
            await self._session.close()
            self._session = None

    async def _ensure_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(timeout=self._timeout)
        return self._session

    async def _request(
        self,
        method: str,
        url: str,
        *,
        json_body: dict | None = None,
        params: dict | None = None,
        headers: dict | None = None,
    ) -> Any:
        if self._closed:
            raise ProviderUnavailable(f"{self.name} closed")
        if not await self._breaker.allow_request():
            raise ProviderUnavailable(f"{self.name} circuit open")
        await self._rate_limiter.acquire()
        session = await self._ensure_session()
        start = now_mono()
        try:
            async with session.request(
                method, url, json=json_body, params=params, headers=headers
            ) as resp:
                latency = now_mono() - start
                if resp.status == 429:
                    await self._breaker.record_failure()
                    self._stats.record_failure()
                    raise ProviderUnavailable(f"{self.name} 429 rate-limited")
                if resp.status >= 500:
                    await self._breaker.record_failure()
                    self._stats.record_failure()
                    raise ProviderError(f"{self.name} {resp.status} server error")
                if resp.status >= 400:
                    self._stats.record_failure()
                    raise ProviderError(f"{self.name} {resp.status} client error")
                payload = await resp.json(content_type=None)
                await self._breaker.record_success()
                self._stats.record_success(latency)
                self._backoff.reset()
                return payload
        except asyncio.TimeoutError as exc:
            await self._breaker.record_failure()
            self._stats.record_failure()
            raise ProviderUnavailable(f"{self.name} timeout") from exc
        except aiohttp.ClientError as exc:
            await self._breaker.record_failure()
            self._stats.record_failure()
            raise ProviderUnavailable(f"{self.name} network error: {exc}") from exc

    async def _request_with_retry(
        self,
        method: str,
        url: str,
        *,
        json_body: dict | None = None,
        params: dict | None = None,
        headers: dict | None = None,
        max_retries: int = 3,
    ) -> Any:
        last_exc: Exception | None = None
        for attempt in range(max_retries):
            try:
                return await self._request(
                    method, url, json_body=json_body, params=params, headers=headers
                )
            except (ProviderUnavailable, ProviderError) as exc:
                last_exc = exc
                if isinstance(exc, ProviderError) and "client error" in str(exc):
                    raise  # 4xx — do not retry
                delay = self._backoff.next_delay()
                log.x_debug("provider retry", extras={
                    "provider": self.name, "attempt": attempt + 1, "delay": delay, "err": str(exc)
                })
                await asyncio.sleep(delay)
        assert last_exc is not None
        raise last_exc

    async def _ws_connect_with_retry(
        self,
        url: str,
        on_message: Callable[[dict], Awaitable[None]],
        on_connect: Callable[[], Awaitable[None]] | None = None,
        ping_interval_sec: float = 20.0,
    ) -> None:
        """Connect, subscribe, and keep a WebSocket alive.

        Returns only on shutdown or unrecoverable failure.
        Reconnects with backoff up to max attempts.
        """
        session = await self._ensure_session()
        while not self._closed and self._ws_reconnect_attempts < self._max_ws_reconnect_attempts:
            try:
                async with session.ws_connect(
                    url, heartbeat=ping_interval_sec, timeout=self._timeout.total
                ) as ws:
                    if on_connect:
                        await on_connect()
                    self._ws_reconnect_attempts = 0
                    self._backoff.reset()
                    async for msg in ws:
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            try:
                                import json
                                payload = json.loads(msg.data)
                            except (ValueError, TypeError) as exc:
                                log.x_warn("ws bad json", extras={
                                    "provider": self.name, "err": str(exc)
                                })
                                continue
                            try:
                                await on_message(payload)
                            except Exception as exc:  # pragma: no cover - defensive
                                log.x_warn("ws on_message error", extras={
                                    "provider": self.name, "err": str(exc)
                                })
                        elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                            log.x_warn("ws closed", extras={"provider": self.name})
                            break
            except (aiohttp.ClientError, asyncio.TimeoutError, OSError) as exc:
                self._ws_reconnect_attempts += 1
                delay = self._backoff.next_delay()
                log.x_warn("ws reconnect", extras={
                    "provider": self.name,
                    "attempt": self._ws_reconnect_attempts,
                    "delay": delay,
                    "err": str(exc),
                })
                await asyncio.sleep(delay)
        if not self._closed:
            log.x_error("ws reconnects exhausted", extras={"provider": self.name})
            self._stats.state = ProviderState.UNAVAILABLE


class ProviderRegistry:
    """Holds all providers, exposes health snapshot."""

    def __init__(self) -> None:
        self._providers: dict[str, Provider] = {}

    def register(self, provider: Provider) -> None:
        self._providers[provider.name] = provider

    def get(self, name: str) -> Provider | None:
        return self._providers.get(name)

    def all(self) -> dict[str, Provider]:
        return dict(self._providers)

    def health(self) -> list[ProviderHealth]:
        return [p.stats.health() for p in self._providers.values()]

    async def close_all(self) -> None:
        for p in list(self._providers.values()):
            try:
                await p.close()
            except Exception as exc:  # pragma: no cover - defensive
                log.x_warn("provider close error", extras={
                    "provider": p.name, "err": str(exc)
                })
        self._providers.clear()
