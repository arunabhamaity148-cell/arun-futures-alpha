"""CoinDCX provider — REST + WS — execution truth.

Verified endpoints (research FACT, docs.coindcx.com):
- GET /exchange/ticker
- GET /exchange/v1/markets
- GET /exchange/v1/markets_details
- GET /market_data/trade_history?pair=B-BTC_USDT&limit=50
- GET /market_data/orderbook?pair=B-BTC_USDT
- GET /market_data/candles?pair=B-BTC_USDT&interval=1m

Futures API: NOT VERIFIED (sandbox geo-block during research). The bot will
attempt /exchange/v1/derivatives/futures/data/instruments and fall back to
spot-only mode if it returns 404/403/geo-block. In spot-only mode the bot
will emit NO-TRADE for any pair whose futures symbol cannot be confirmed.
"""
from __future__ import annotations

import asyncio
import time
from typing import Any

import aiohttp

from ..core.exceptions import ProviderError, ProviderUnavailable, SchemaError, StaleDataError
from ..core.logger import get_logger
from ..core.time_utils import now_ts
from ..core.types import Candle, OrderBookSnapshot, Ticker, Trade
from .base import Provider, SchemaValidator

log = get_logger("coindcx")


class CoinDCXProvider(Provider):
    """CoinDCX spot + futures (where available) data provider."""

    name = "coindcx"

    def __init__(self, rest_url: str, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._rest_url = rest_url.rstrip("/")
        self._futures_instruments: set[str] = set()
        self._futures_verified = False

    # ----------------------------- REST ---------------------------------

    async def get_ticker(self, coindcx_symbol: str) -> Ticker:
        # /exchange/ticker returns a list of all tickers; we filter locally
        # to avoid one request per pair (rate-limit friendly).
        payload = await self._request_with_retry(
            "GET", f"{self._rest_url}/exchange/ticker"
        )
        if not isinstance(payload, list):
            raise SchemaError("coindcx /exchange/ticker did not return list")
        for row in payload:
            if not isinstance(row, dict):
                continue
            if row.get("market") == coindcx_symbol:
                return self._parse_ticker(row)
        raise ProviderError(f"coindcx symbol {coindcx_symbol} not in ticker list")

    async def get_all_tickers(self) -> dict[str, Ticker]:
        payload = await self._request_with_retry(
            "GET", f"{self._rest_url}/exchange/ticker"
        )
        if not isinstance(payload, list):
            raise SchemaError("coindcx /exchange/ticker did not return list")
        out: dict[str, Ticker] = {}
        for row in payload:
            if not isinstance(row, dict):
                continue
            sym = row.get("market")
            if not sym:
                continue
            try:
                out[sym] = self._parse_ticker(row)
            except (SchemaError, ValueError):
                continue
        return out

    async def get_orderbook(self, coindcx_symbol: str, depth: int = 50) -> OrderBookSnapshot:
        payload = await self._request_with_retry(
            "GET",
            f"{self._rest_url}/market_data/orderbook",
            params={"pair": coindcx_symbol},
        )
        SchemaValidator.validate(payload, {"bids": list, "asks": list})
        bids = [(float(p), float(s)) for p, s in payload["bids"][:depth]]
        asks = [(float(p), float(s)) for p, s in payload["asks"][:depth]]
        # Orderbook endpoint does not return a server timestamp; use receive time.
        ts = now_ts()
        return OrderBookSnapshot(
            venue=self.name,
            symbol=coindcx_symbol,
            bids=bids,
            asks=asks,
            timestamp=ts,
            received_at=ts,
        )

    async def get_candles(
        self,
        coindcx_symbol: str,
        interval: str = "1m",
        limit: int = 200,
    ) -> list[Candle]:
        payload = await self._request_with_retry(
            "GET",
            f"{self._rest_url}/market_data/candles",
            params={"pair": coindcx_symbol, "interval": interval, "limit": limit},
        )
        if not isinstance(payload, list):
            raise SchemaError("coindcx candles did not return list")
        out: list[Candle] = []
        for row in payload:
            try:
                out.append(Candle(
                    venue=self.name,
                    symbol=coindcx_symbol,
                    tf=interval,
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=float(row["volume"]),
                    open_time=float(row["time"]),
                    close_time=float(row["time"]) + 60.0,
                ))
            except (KeyError, TypeError, ValueError):
                continue
        return out

    async def get_recent_trades(self, coindcx_symbol: str, limit: int = 50) -> list[Trade]:
        payload = await self._request_with_retry(
            "GET",
            f"{self._rest_url}/market_data/trade_history",
            params={"pair": coindcx_symbol, "limit": limit},
        )
        if not isinstance(payload, list):
            raise SchemaError("coindcx trades did not return list")
        from ..core.types import Side  # local import to avoid cycle
        out: list[Trade] = []
        for row in payload:
            try:
                side = "BUY" if float(row.get("takeRate", 0.0)) >= 0 else "SELL"
                # CoinDCX trade_history format: { price, size, timestamp, side? }
                # Some versions use 'takeRate'/'makeRate' as +ve/-ve hints; use 'side' if present.
                if "side" in row:
                    side = str(row["side"]).upper()
                out.append(Trade(
                    venue=self.name,
                    symbol=coindcx_symbol,
                    price=float(row["price"]),
                    size=float(row["size"]),
                    side=side,  # type: ignore[arg-type]
                    timestamp=float(row.get("timestamp", row.get("time", 0))),
                ))
            except (KeyError, TypeError, ValueError):
                continue
        return out

    # --------------------- FUTURES INSTRUMENT LIST ---------------------

    async def verify_futures_universe(self) -> tuple[set[str], bool]:
        """Attempt to verify the CoinDCX futures instrument list.

        The futures API base URL differs from the public spot base. Several
        candidate URLs are tried; if all fail, returns (empty set, False) and
        the bot will mark all futures symbols NOT VERIFIED → NO-TRADE.
        """
        if self._futures_verified:
            return self._futures_instruments, True

        candidate_urls = [
            "https://api.coindcx.com/exchange/v1/derivatives/futures/data/instruments",
            "https://public.coindcx.com/api/v1/futures/instruments",
            "https://api.coindcx.com/api/v1/futures/instruments",
        ]
        last_exc: Exception | None = None
        for url in candidate_urls:
            try:
                payload = await self._request_with_retry("GET", url)
                if isinstance(payload, list) and payload:
                    instruments: set[str] = set()
                    for row in payload:
                        if not isinstance(row, dict):
                            continue
                        sym = row.get("symbol") or row.get("instrument") or row.get("contract")
                        if isinstance(sym, str) and sym:
                            instruments.add(sym)
                    if instruments:
                        self._futures_instruments = instruments
                        self._futures_verified = True
                        log.x_info("coindcx futures universe verified", extras={
                            "count": len(instruments),
                            "url": url,
                        })
                        return self._futures_instruments, True
            except (ProviderError, ProviderUnavailable, SchemaError) as exc:
                last_exc = exc
                continue
        log.x_warn("coindcx futures universe NOT VERIFIED — running spot-only fail-closed",
                   extras={"last_err": str(last_exc) if last_exc else "no candidates succeeded"})
        self._futures_verified = False
        return set(), False

    def is_futures_symbol_verified(self, futures_symbol: str) -> bool:
        return self._futures_verified and futures_symbol in self._futures_instruments

    # ----------------------------- PARSERS ------------------------------

    @staticmethod
    def _parse_ticker(row: dict[str, Any]) -> Ticker:
        sym = row.get("market", "")
        bid = float(row.get("bid", 0.0) or 0.0)
        ask = float(row.get("ask", 0.0) or 0.0)
        last = float(row.get("last_price", 0.0) or 0.0)
        if last <= 0:
            last = (bid + ask) / 2.0 if bid > 0 and ask > 0 else 0.0
        mid = (bid + ask) / 2.0 if bid > 0 and ask > 0 else last
        spread = (ask - bid) if (bid > 0 and ask > 0) else 0.0
        spread_bps = (spread / mid * 1e4) if mid > 0 else 0.0
        # Split B-BTC_USDT → BTC/USDT
        if sym.startswith("B-"):
            stripped = sym[2:]
        else:
            stripped = sym
        if "_" in stripped:
            parts = stripped.split("_")
            base = parts[0]
            quote = parts[1] if len(parts) > 1 else ""
        else:
            base, quote = "", ""
        ts_str = row.get("timestamp")
        try:
            ts = float(ts_str) if ts_str else now_ts()
            # CoinDCX timestamp is in milliseconds.
            if ts > 1e12:
                ts /= 1000.0
        except (TypeError, ValueError):
            ts = now_ts()
        return Ticker(
            venue="coindcx",
            symbol=sym,
            base=base,
            quote=quote,
            bid=bid,
            ask=ask,
            last=last,
            mid=mid,
            spread_bps=spread_bps,
            timestamp=ts,
            received_at=now_ts(),
        )
