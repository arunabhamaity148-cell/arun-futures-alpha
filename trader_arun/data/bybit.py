"""Bybit v5 provider — REST — fallback for SOL/SUI (research PRIMARY for SUI)."""
from __future__ import annotations

from typing import Any

from ..core.exceptions import SchemaError
from ..core.time_utils import now_ts
from ..core.types import Candle, FundingRate, OpenInterest, OrderBookSnapshot, Ticker
from .base import Provider, SchemaValidator


class BybitProvider(Provider):
    name = "bybit"

    def __init__(self, rest_url: str, ws_url: str, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._rest_url = rest_url.rstrip("/")
        self._ws_url = ws_url

    async def _v5_get(self, path: str, params: dict | None = None) -> dict:
        params = params or {}
        params.setdefault("category", "linear")
        payload = await self._request_with_retry(
            "GET", f"{self._rest_url}{path}", params=params,
        )
        if not isinstance(payload, dict):
            raise SchemaError("bybit response not dict")
        if payload.get("retCode") not in (0, None):
            raise SchemaError(f"bybit error: {payload.get('retMsg')}")
        return payload

    async def get_ticker(self, symbol: str) -> Ticker:
        payload = await self._v5_get("/v5/market/tickers", {"symbol": symbol})
        result = payload.get("result", {})
        rows = result.get("list", [])
        if not rows:
            raise SchemaError(f"bybit ticker empty for {symbol}")
        row = rows[0]
        bid = float(row.get("bid1Price", 0.0) or 0.0)
        ask = float(row.get("ask1Price", 0.0) or 0.0)
        last = float(row.get("lastPrice", 0.0) or 0.0)
        mid = (bid + ask) / 2.0 if bid > 0 and ask > 0 else last
        spread_bps = (ask - bid) / mid * 1e4 if mid > 0 else 0.0
        ts = float(row.get("timestamp", payload.get("time", 0) or 0))
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
            last=last,
            mid=mid,
            spread_bps=spread_bps,
            timestamp=ts,
            received_at=now_ts(),
        )

    async def get_orderbook(self, symbol: str, depth: int = 50) -> OrderBookSnapshot:
        payload = await self._v5_get("/v5/market/orderbook", {
            "symbol": symbol, "limit": min(depth, 200),
        })
        result = payload.get("result", {})
        bids_raw = result.get("b", [])
        asks_raw = result.get("a", [])
        bids = [(float(p), float(s)) for p, s in bids_raw]
        asks = [(float(p), float(s)) for p, s in asks_raw]
        bids.sort(key=lambda x: -x[0])
        asks.sort(key=lambda x: x[0])
        ts = float(result.get("ts", payload.get("time", 0) or 0))
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

    async def get_candles(self, symbol: str, interval: str = "1", limit: int = 200) -> list[Candle]:
        # Bybit interval strings: 1,3,5,15,30,60,240,D
        payload = await self._v5_get("/v5/market/kline", {
            "symbol": symbol, "interval": interval, "limit": limit,
        })
        result = payload.get("result", {})
        rows = result.get("list", [])
        out: list[Candle] = []
        tf_map = {"1": "1m", "5": "5m", "15": "15m", "60": "1h", "240": "4h", "D": "1d"}
        tf = tf_map.get(interval, interval)
        for row in rows:
            try:
                # Bybit returns [start, open, high, low, close, volume, turnover]
                open_ts = float(row[0]) / 1000.0
                out.append(Candle(
                    venue=self.name,
                    symbol=symbol,
                    tf=tf,
                    open=float(row[1]),
                    high=float(row[2]),
                    low=float(row[3]),
                    close=float(row[4]),
                    volume=float(row[5]),
                    open_time=open_ts,
                    close_time=open_ts + 60.0,
                ))
            except (IndexError, TypeError, ValueError):
                continue
        out.sort(key=lambda c: c.open_time)
        return out

    async def get_funding(self, symbol: str) -> FundingRate | None:
        payload = await self._v5_get("/v5/market/tickers", {"symbol": symbol})
        result = payload.get("result", {})
        rows = result.get("list", [])
        if not rows:
            return None
        row = rows[0]
        try:
            ts = float(row.get("fundingRateTimestamp", payload.get("time", 0) or 0))
            if ts > 1e12:
                ts /= 1000.0
            if ts == 0:
                ts = now_ts()
            next_funding = float(row.get("nextFundingTime", ts))
            if next_funding > 1e12:
                next_funding /= 1000.0
            return FundingRate(
                venue=self.name,
                symbol=symbol,
                rate=float(row.get("fundingRate", 0.0) or 0.0),
                next_funding_time=next_funding,
                timestamp=ts,
            )
        except (TypeError, ValueError):
            return None

    async def get_open_interest(self, symbol: str) -> OpenInterest | None:
        payload = await self._v5_get("/v5/market/tickers", {"symbol": symbol})
        result = payload.get("result", {})
        rows = result.get("list", [])
        if not rows:
            return None
        row = rows[0]
        try:
            ts = float(payload.get("time", 0) or 0)
            if ts > 1e12:
                ts /= 1000.0
            if ts == 0:
                ts = now_ts()
            oi_base = float(row.get("openInterest", 0.0) or 0.0)
            mark = float(row.get("markPrice", 0.0) or 0.0)
            return OpenInterest(
                venue=self.name,
                symbol=symbol,
                oi_base=oi_base,
                oi_usd=oi_base * mark,
                timestamp=ts,
            )
        except (TypeError, ValueError):
            return None
