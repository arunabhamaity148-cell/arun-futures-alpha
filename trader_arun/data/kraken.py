"""Kraken provider — REST + WS — spot anchor (verified working in research).

Endpoints:
- GET /0/public/Ticker   pair=XXBTZUSD
- GET /0/public/OHLC     pair=XXBTZUSD&interval=1
- GET /0/public/Depth    pair=XXBTZUSD&count=50
- WS wss://ws.kraken.com — book/trade channels
"""
from __future__ import annotations

from typing import Any

import aiohttp

from ..core.exceptions import ProviderError, SchemaError
from ..core.logger import get_logger
from ..core.time_utils import now_ts
from ..core.types import Candle, OrderBookSnapshot, Ticker
from .base import Provider, SchemaValidator

log = get_logger("kraken")


class KrakenProvider(Provider):
    name = "kraken"

    def __init__(self, rest_url: str, ws_url: str, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._rest_url = rest_url.rstrip("/")
        self._ws_url = ws_url

    async def get_ticker(self, pair: str) -> Ticker:
        payload = await self._request_with_retry(
            "GET", f"{self._rest_url}/0/public/Ticker", params={"pair": pair}
        )
        SchemaValidator.validate(payload, {"error": list})
        result = payload.get("result")
        if not isinstance(result, dict) or not result:
            raise SchemaError("kraken ticker empty result")
        # Result key may differ from requested pair (normalised form).
        actual_key = next(iter(result.keys()))
        row = result[actual_key]
        if not isinstance(row, dict):
            raise SchemaError("kraken ticker malformed row")
        try:
            bid = float(row["b"][0])
            ask = float(row["a"][0])
            last = float(row["c"][0])
            mid = (bid + ask) / 2.0 if bid > 0 and ask > 0 else last
            spread_bps = (ask - bid) / mid * 1e4 if mid > 0 else 0.0
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise SchemaError(f"kraken ticker field error: {exc}") from exc
        return Ticker(
            venue="kraken",
            symbol=pair,
            base="",
            quote="",
            bid=bid,
            ask=ask,
            last=last,
            mid=mid,
            spread_bps=spread_bps,
            timestamp=now_ts(),
            received_at=now_ts(),
        )

    async def get_orderbook(self, pair: str, depth: int = 50) -> OrderBookSnapshot:
        payload = await self._request_with_retry(
            "GET", f"{self._rest_url}/0/public/Depth",
            params={"pair": pair, "count": depth},
        )
        SchemaValidator.validate(payload, {"error": list})
        result = payload.get("result")
        if not isinstance(result, dict) or not result:
            raise SchemaError("kraken depth empty result")
        actual_key = next(iter(result.keys()))
        row = result[actual_key]
        bids = [(float(p), float(s)) for p, s, *_ in row.get("bids", [])[:depth]]
        asks = [(float(p), float(s)) for p, s, *_ in row.get("asks", [])[:depth]]
        bids.sort(key=lambda x: -x[0])
        asks.sort(key=lambda x: x[0])
        ts = now_ts()
        return OrderBookSnapshot(
            venue="kraken",
            symbol=pair,
            bids=bids,
            asks=asks,
            timestamp=ts,
            received_at=ts,
        )

    async def get_candles(self, pair: str, interval_min: int = 1) -> list[Candle]:
        payload = await self._request_with_retry(
            "GET", f"{self._rest_url}/0/public/OHLC",
            params={"pair": pair, "interval": interval_min},
        )
        SchemaValidator.validate(payload, {"error": list})
        result = payload.get("result")
        if not isinstance(result, dict) or not result:
            return []
        actual_key = next(iter(result.keys()))
        rows = result[actual_key]
        out: list[Candle] = []
        tf = f"{interval_min}m" if interval_min < 60 else f"{interval_min // 60}h"
        for row in rows:
            try:
                open_ts = float(row[0])
                out.append(Candle(
                    venue="kraken",
                    symbol=pair,
                    tf=tf,
                    open=float(row[1]),
                    high=float(row[2]),
                    low=float(row[3]),
                    close=float(row[4]),
                    volume=float(row[6]),
                    open_time=open_ts,
                    close_time=open_ts + interval_min * 60.0,
                ))
            except (IndexError, TypeError, ValueError):
                continue
        return out
