"""Binance Futures provider — REST — fallback for SOL/SUI where HL is thin.

Endpoints (research FACT):
- GET /fapi/v1/ticker/bookTicker  symbol=BTCUSDT
- GET /fapi/v1/ticker/24hr        symbol=BTCUSDT
- GET /fapi/v1/depth              symbol=BTCUSDT&limit=50
- GET /fapi/v1/klines             symbol=BTCUSDT&interval=1m&limit=200
- GET /fapi/v1/premiumIndex       symbol=BTCUSDT   (funding)
- GET /fapi/v1/openInterest       symbol=BTCUSDT

NOTE: Some regions geo-block Binance. If geo-blocked, this provider will fail-
closed and the bot will fall back to Hyperliquid/Bybit where available.
"""
from __future__ import annotations

from typing import Any

from ..core.exceptions import SchemaError
from ..core.time_utils import now_ts
from ..core.types import Candle, FundingRate, OpenInterest, OrderBookSnapshot, Ticker
from .base import Provider, SchemaValidator


class BinanceFuturesProvider(Provider):
    name = "binance_futures"

    def __init__(self, rest_url: str, ws_url: str, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._rest_url = rest_url.rstrip("/")
        self._ws_url = ws_url

    async def get_ticker(self, symbol: str) -> Ticker:
        payload = await self._request_with_retry(
            "GET", f"{self._rest_url}/fapi/v1/ticker/bookTicker",
            params={"symbol": symbol},
        )
        SchemaValidator.validate(payload, {"symbol": str, "bidPrice": str, "askPrice": str})
        bid = float(payload["bidPrice"])
        ask = float(payload["askPrice"])
        mid = (bid + ask) / 2.0 if bid > 0 and ask > 0 else 0.0
        spread_bps = (ask - bid) / mid * 1e4 if mid > 0 else 0.0
        ts = float(payload.get("time", 0) or 0)
        if ts > 1e12:
            ts /= 1000.0
        if ts == 0:
            ts = now_ts()
        base = symbol[:-4] if symbol.endswith("USDT") else symbol
        return Ticker(
            venue=self.name,
            symbol=symbol,
            base=base,
            quote="USDT",
            bid=bid,
            ask=ask,
            last=mid,
            mid=mid,
            spread_bps=spread_bps,
            timestamp=ts,
            received_at=now_ts(),
        )

    async def get_orderbook(self, symbol: str, depth: int = 50) -> OrderBookSnapshot:
        payload = await self._request_with_retry(
            "GET", f"{self._rest_url}/fapi/v1/depth",
            params={"symbol": symbol, "limit": depth},
        )
        SchemaValidator.validate(payload, {"bids": list, "asks": list})
        bids = [(float(p), float(s)) for p, s in payload["bids"]]
        asks = [(float(p), float(s)) for p, s in payload["asks"]]
        bids.sort(key=lambda x: -x[0])
        asks.sort(key=lambda x: x[0])
        ts = float(payload.get("E", 0) or 0)
        if ts > 1e12:
            ts /= 1000.0
        if ts == 0:
            ts = now_ts()
        return OrderBookSnapshot(
            venue=self.name,
            symbol=symbol,
            bids=bids,
            asks=asks,
            timestamp=ts,
            received_at=now_ts(),
        )

    async def get_candles(self, symbol: str, interval: str = "1m", limit: int = 200) -> list[Candle]:
        payload = await self._request_with_retry(
            "GET", f"{self._rest_url}/fapi/v1/klines",
            params={"symbol": symbol, "interval": interval, "limit": limit},
        )
        if not isinstance(payload, list):
            return []
        out: list[Candle] = []
        for row in payload:
            try:
                out.append(Candle(
                    venue=self.name,
                    symbol=symbol,
                    tf=interval,
                    open=float(row[1]),
                    high=float(row[2]),
                    low=float(row[3]),
                    close=float(row[4]),
                    volume=float(row[5]),
                    open_time=float(row[0]) / 1000.0,
                    close_time=float(row[6]) / 1000.0,
                ))
            except (IndexError, TypeError, ValueError):
                continue
        return out

    async def get_funding(self, symbol: str) -> FundingRate | None:
        payload = await self._request_with_retry(
            "GET", f"{self._rest_url}/fapi/v1/premiumIndex",
            params={"symbol": symbol},
        )
        if not isinstance(payload, dict):
            return None
        try:
            ts = float(payload.get("time", 0) or 0)
            if ts > 1e12:
                ts /= 1000.0
            if ts == 0:
                ts = now_ts()
            next_funding = float(payload.get("nextFundingTime", ts))
            if next_funding > 1e12:
                next_funding /= 1000.0
            return FundingRate(
                venue=self.name,
                symbol=symbol,
                rate=float(payload.get("lastFundingRate", 0.0) or 0.0),
                next_funding_time=next_funding,
                timestamp=ts,
            )
        except (TypeError, ValueError):
            return None

    async def get_open_interest(self, symbol: str) -> OpenInterest | None:
        payload = await self._request_with_retry(
            "GET", f"{self._rest_url}/fapi/v1/openInterest",
            params={"symbol": symbol},
        )
        if not isinstance(payload, dict):
            return None
        try:
            ts = float(payload.get("time", 0) or 0)
            if ts > 1e12:
                ts /= 1000.0
            if ts == 0:
                ts = now_ts()
            oi_base = float(payload.get("openInterest", 0.0) or 0.0)
            # Need mark price to compute USD notional.
            mark_payload = await self._request_with_retry(
                "GET", f"{self._rest_url}/fapi/v1/premiumIndex",
                params={"symbol": symbol},
            )
            mark = float(mark_payload.get("markPrice", 0.0) or 0.0) if isinstance(mark_payload, dict) else 0.0
            return OpenInterest(
                venue=self.name,
                symbol=symbol,
                oi_base=oi_base,
                oi_usd=oi_base * mark,
                timestamp=ts,
            )
        except (TypeError, ValueError):
            return None
