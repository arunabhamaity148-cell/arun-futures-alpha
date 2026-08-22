"""Hyperliquid provider — REST + WS — verified working in research run (no-key, <1s).

Endpoints used (research FACT):
- POST /info  payload={"type":"allMids"}                — all mids
- POST /info  payload={"type":"metaAndAssetCtxs"}       — perp meta + funding/OI
- POST /info  payload={"type":"assetCtxs"}              — perp contexts only
- WS wss://.../ws  subscribe to trades / l2Book / candle
"""
from __future__ import annotations

import asyncio
import time
from typing import Any

import aiohttp

from ..core.exceptions import ProviderError, SchemaError
from ..core.logger import get_logger
from ..core.time_utils import now_ts
from ..core.types import Candle, FundingRate, OpenInterest, OrderBookSnapshot, Trade, Ticker
from .base import Provider, SchemaValidator

log = get_logger("hyperliquid")


class HyperliquidProvider(Provider):
    name = "hyperliquid"

    def __init__(self, rest_url: str, ws_url: str, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._rest_url = rest_url.rstrip("/")
        self._ws_url = ws_url
        # Optional per-asset subscription tracking.
        self._subscribed_assets: set[str] = set()
        # Latest snapshot cache (very small — one entry per asset, replaced atomically).
        self._mids: dict[str, float] = {}
        self._asset_ctx: dict[str, dict[str, Any]] = {}
        self._ws_task: asyncio.Task | None = None
        self._ws_stop = asyncio.Event()

    async def _post_info(self, payload: dict[str, Any]) -> Any:
        return await self._request_with_retry(
            "POST", f"{self._rest_url}/info", json_body=payload
        )

    async def fetch_all_mids(self) -> dict[str, float]:
        payload = await self._post_info({"type": "allMids"})
        SchemaValidator.validate(payload, {"mids": dict})
        out: dict[str, float] = {}
        for asset, price_str in payload["mids"].items():
            try:
                p = float(price_str)
                if p > 0:
                    out[asset] = p
            except (TypeError, ValueError):
                continue
        self._mids.update(out)
        return out

    async def fetch_meta_and_asset_ctxs(self) -> tuple[dict, list[dict]]:
        payload = await self._post_info({"type": "metaAndAssetCtxs"})
        if not isinstance(payload, list) or len(payload) != 2:
            raise SchemaError("metaAndAssetCtxs malformed")
        meta, ctxs = payload[0], payload[1]
        if not isinstance(meta, dict) or not isinstance(ctxs, list):
            raise SchemaError("metaAndAssetCtxs wrong shape")
        # Cache ctxs by asset name from meta.universe.
        universe = meta.get("universe", [])
        if not isinstance(universe, list):
            raise SchemaError("meta.universe not list")
        for i, u in enumerate(universe):
            if i >= len(ctxs):
                break
            if not isinstance(u, dict) or not isinstance(ctxs[i], dict):
                continue
            asset = u.get("name")
            if isinstance(asset, str):
                self._asset_ctx[asset] = ctxs[i]
        return meta, ctxs

    async def fetch_funding_and_oi(self, asset: str) -> tuple[FundingRate | None, OpenInterest | None]:
        if asset not in self._asset_ctx:
            await self.fetch_meta_and_asset_ctxs()
        ctx = self._asset_ctx.get(asset)
        if not isinstance(ctx, dict):
            return None, None
        try:
            funding = float(ctx.get("funding", 0.0))
            open_interest_str = ctx.get("openInterest", "0")
            oi_base = float(open_interest_str)
            mid = self._mids.get(asset, 0.0) or float(ctx.get("markPx", 0.0) or 0.0)
            oi_usd = oi_base * mid
            ts = now_ts()
            next_funding = float(ctx.get("nextFundingTime", ts))
            if next_funding > 1e12:
                next_funding /= 1000.0
            fr = FundingRate(
                venue="hyperliquid",
                symbol=f"{asset}USDT",
                rate=funding,
                next_funding_time=next_funding,
                timestamp=ts,
            )
            oi = OpenInterest(
                venue="hyperliquid",
                symbol=f"{asset}USDT",
                oi_base=oi_base,
                oi_usd=oi_usd,
                timestamp=ts,
            )
            return fr, oi
        except (TypeError, ValueError) as exc:
            log.x_warn("hyperliquid parse error", extras={"asset": asset, "err": str(exc)})
            return None, None

    async def fetch_l2_book(self, asset: str) -> OrderBookSnapshot | None:
        payload = await self._post_info({
            "type": "l2Book",
            "coin": asset,
        })
        if not isinstance(payload, dict) or "levels" not in payload:
            return None
        levels = payload["levels"]
        if not isinstance(levels, list) or len(levels) != 2:
            return None
        bids_raw, asks_raw = levels[0], levels[1]
        bids = [(float(lvl["px"]), float(lvl["sz"])) for lvl in bids_raw[:50]]
        asks = [(float(lvl["px"]), float(lvl["sz"])) for lvl in asks_raw[:50]]
        ts = now_ts()
        return OrderBookSnapshot(
            venue="hyperliquid",
            symbol=f"{asset}USDT",
            bids=bids,
            asks=asks,
            timestamp=ts,
            received_at=ts,
        )

    async def fetch_candles(
        self, asset: str, interval: str = "1m", limit: int = 200
    ) -> list[Candle]:
        # Hyperliquid candleSnapshot endpoint requires the request wrapped in "req".
        interval_map = {"1m": "1m", "5m": "5m", "15m": "15m", "1h": "1h", "4h": "4h", "1d": "1d"}
        hl_interval = interval_map.get(interval, interval)
        end_ts = int(now_ts() * 1000)
        start_ts = end_ts - limit * 60_000
        payload = await self._post_info({
            "type": "candleSnapshot",
            "req": {
                "coin": asset,
                "interval": hl_interval,
                "startTime": start_ts,
                "endTime": end_ts,
            },
        })
        if not isinstance(payload, list):
            return []
        out: list[Candle] = []
        for row in payload:
            try:
                out.append(Candle(
                    venue="hyperliquid",
                    symbol=f"{asset}USDT",
                    tf=interval,
                    open=float(row["o"]),
                    high=float(row["h"]),
                    low=float(row["l"]),
                    close=float(row["c"]),
                    volume=float(row["v"]),
                    open_time=float(row["t"]) / 1000.0,
                    close_time=float(row["T"]) / 1000.0,
                ))
            except (KeyError, TypeError, ValueError):
                continue
        return out

    async def get_ticker_for_asset(self, asset: str) -> Ticker | None:
        """Build a Ticker from l2Book snapshot (top-of-book)."""
        book = await self.fetch_l2_book(asset)
        if book is None:
            return None
        bid = book.bids[0][0] if book.bids else 0.0
        ask = book.asks[0][0] if book.asks else 0.0
        mid = book.mid()
        spread_bps = (book.spread() / mid * 1e4) if mid > 0 else 0.0
        return Ticker(
            venue="hyperliquid",
            symbol=f"{asset}USDT",
            base=asset,
            quote="USDT",
            bid=bid,
            ask=ask,
            last=mid,
            mid=mid,
            spread_bps=spread_bps,
            timestamp=book.timestamp,
            received_at=book.received_at,
        )

    async def close(self) -> None:
        self._ws_stop.set()
        if self._ws_task is not None:
            self._ws_task.cancel()
            try:
                await self._ws_task
            except (asyncio.CancelledError, Exception):
                pass
            self._ws_task = None
        await super().close()
