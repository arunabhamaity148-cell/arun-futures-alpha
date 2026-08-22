"""Fault-injection tests — DNS failure, 429, 500, malformed data, provider outage."""
import asyncio
import dataclasses
import os
import json
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest

from trader_arun.core.circuit_breaker import CircuitBreaker
from trader_arun.core.exceptions import ProviderError, ProviderUnavailable, SchemaError
from trader_arun.data.base import Provider
from trader_arun.data.coindcx import CoinDCXProvider
from trader_arun.data.manager import DataManager
from trader_arun.core.config import Config, PairConfig
import time


@pytest.mark.asyncio
async def test_provider_429_triggers_circuit_breaker():
    # Mock session that always returns 429.
    mock_resp = AsyncMock()
    mock_resp.status = 429
    mock_resp.json = AsyncMock(return_value={})
    mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_resp.__aexit__ = AsyncMock(return_value=None)

    mock_session = MagicMock()
    mock_session.request = MagicMock(return_value=mock_resp)
    mock_session.closed = False

    p = CoinDCXProvider(rest_url="https://api.coindcx.com", session=mock_session)
    for _ in range(5):
        with pytest.raises(ProviderUnavailable):
            await p._request("GET", "https://api.coindcx.com/exchange/ticker")
    # After 5 failures, breaker should be OPEN.
    assert p.breaker.state == "OPEN"
    await p.close()


@pytest.mark.asyncio
async def test_provider_500_triggers_circuit_breaker():
    mock_resp = AsyncMock()
    mock_resp.status = 500
    mock_resp.json = AsyncMock(return_value={})
    mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_resp.__aexit__ = AsyncMock(return_value=None)

    mock_session = MagicMock()
    mock_session.request = MagicMock(return_value=mock_resp)
    mock_session.closed = False

    p = CoinDCXProvider(rest_url="https://api.coindcx.com", session=mock_session)
    for _ in range(5):
        with pytest.raises(ProviderError):
            await p._request("GET", "https://api.coindcx.com/exchange/ticker")
    assert p.breaker.state == "OPEN"
    await p.close()


@pytest.mark.asyncio
async def test_provider_timeout_records_failure():
    # Mock session whose request raises TimeoutError.
    mock_session = MagicMock()
    mock_session.request = MagicMock(side_effect=asyncio.TimeoutError())
    mock_session.closed = False

    p = CoinDCXProvider(rest_url="https://api.coindcx.com", session=mock_session)
    for _ in range(5):
        with pytest.raises(ProviderUnavailable):
            await p._request("GET", "https://api.coindcx.com/exchange/ticker")
    assert p.breaker.state == "OPEN"
    await p.close()


@pytest.mark.asyncio
async def test_schema_validation_catches_malformed_payload():
    mock_resp = AsyncMock()
    mock_resp.status = 200
    mock_resp.json = AsyncMock(return_value={"unexpected": "shape"})
    mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_resp.__aexit__ = AsyncMock(return_value=None)

    mock_session = MagicMock()
    mock_session.request = MagicMock(return_value=mock_resp)
    mock_session.closed = False

    p = CoinDCXProvider(rest_url="https://api.coindcx.com", session=mock_session)
    # /exchange/ticker expects a list, but we return a dict.
    with pytest.raises(SchemaError):
        await p.get_all_tickers()
    await p.close()


@pytest.mark.asyncio
async def test_network_error_does_not_crash_data_manager():
    """If every provider fails, fetch_pair_snapshot returns a snapshot with None fields."""
    cfg = Config()
    # Use dataclasses.replace to create a new frozen config with bad URLs.
    cfg = dataclasses.replace(
        cfg,
        coindcx_rest_url="http://127.0.0.1:1",  # port 1 = connection refused
        hyperliquid_rest_url="http://127.0.0.1:1",
        kraken_rest_url="http://127.0.0.1:1",
        binance_fapi_rest_url="http://127.0.0.1:1",
        bybit_rest_url="http://127.0.0.1:1",
        coinglass_url="http://127.0.0.1:1",
        request_timeout_sec=0.5,
    )
    async with DataManager(cfg) as dm:
        pair = cfg.pairs[0]
        # Should not raise; should return snapshot with all None.
        snap = await dm.fetch_pair_snapshot(pair)
        assert snap.coindcx_ticker is None
        assert len(snap.external_tickers) == 0


@pytest.mark.asyncio
async def test_circuit_breaker_half_open_recovers_on_success():
    cb = CircuitBreaker(name="test", failure_threshold=2, cool_down_sec=0.05)
    await cb.record_failure()
    await cb.record_failure()
    assert cb.state == "OPEN"
    assert await cb.allow_request() is False
    await asyncio.sleep(0.06)
    # Should allow one trial.
    assert await cb.allow_request() is True
    # Trial succeeds → CLOSED.
    await cb.record_success()
    assert cb.state == "CLOSED"


@pytest.mark.asyncio
async def test_data_manager_validates_ticker():
    cfg = Config()
    async with DataManager(cfg) as dm:
        from trader_arun.core.types import Ticker
        # Fresh ticker passes (use wallclock time, not loop time).
        fresh = Ticker(
            venue="coindcx", symbol="B-BTC_USDT", base="BTC", quote="USDT",
            bid=100, ask=101, last=100.5, mid=100.5, spread_bps=10.0,
            timestamp=time.time(),
            received_at=time.time(),
        )
        assert dm.validate_ticker(fresh, "coindcx") is True
        # Stale ticker fails.
        stale = Ticker(
            venue="coindcx", symbol="B-BTC_USDT", base="BTC", quote="USDT",
            bid=100, ask=101, last=100.5, mid=100.5, spread_bps=10.0,
            timestamp=1.0,  # very old
            received_at=1.0,
        )
        assert dm.validate_ticker(stale, "coindcx") is False
        # Zero bid/ask fails.
        zero = Ticker(
            venue="coindcx", symbol="B-BTC_USDT", base="BTC", quote="USDT",
            bid=0, ask=0, last=0, mid=0, spread_bps=0,
            timestamp=time.time(),
            received_at=time.time(),
        )
        assert dm.validate_ticker(zero, "coindcx") is False
