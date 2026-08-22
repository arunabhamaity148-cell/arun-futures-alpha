"""Data manager — orchestrates all providers and exposes a unified snapshot.

Holds the latest snapshot per (venue, symbol). All snapshots are time-bounded
via the per-symbol freshness config. If a snapshot is stale, get_snapshot()
returns None and the pipeline must propagate NO-TRADE.
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any

import aiohttp

from ..core.config import Config, PairConfig
from ..core.exceptions import DataQualityError, ProviderUnavailable, StaleDataError
from ..core.logger import get_logger
from ..core.ringbuffer import RingBuffer
from ..core.time_utils import age_sec, now_ts
from ..core.types import (
    Candle,
    FundingRate,
    Liquidation,
    OpenInterest,
    OrderBookSnapshot,
    Ticker,
    Trade,
)
from .base import ProviderRegistry
from .binance import BinanceFuturesProvider
from .bybit import BybitProvider
from .coindcx import CoinDCXProvider
from .coinglass import CoinGlassProvider
from .fred import FREDProvider
from .gdelt import GDELTProvider
from .hyperliquid import HyperliquidProvider
from .kraken import KrakenProvider
from .tokenunlocks import TokenUnlocksProvider

log = get_logger("data_manager")


@dataclass
class PairSnapshot:
    """All current data for a single pair across venues."""

    pair: PairConfig
    coindcx_ticker: Ticker | None = None
    coindcx_book: OrderBookSnapshot | None = None
    coindcx_candles: list[Candle] = field(default_factory=list)
    external_tickers: dict[str, Ticker] = field(default_factory=dict)  # venue → Ticker
    external_books: dict[str, OrderBookSnapshot] = field(default_factory=dict)
    funding: dict[str, FundingRate] = field(default_factory=dict)      # venue → FundingRate
    open_interest: dict[str, OpenInterest] = field(default_factory=dict)
    liquidations: list[Liquidation] = field(default_factory=list)
    hl_candles: list[Candle] = field(default_factory=list)
    binance_candles: list[Candle] = field(default_factory=list)
    trades_by_venue: dict[str, list[Trade]] = field(default_factory=dict)
    timestamp: float = 0.0

    def is_complete(self, required: set[str]) -> bool:
        return all(getattr(self, k) is not None for k in required)


class DataManager:
    """Coordinates all providers, fetches data for the watchlist."""

    def __init__(self, cfg: Config) -> None:
        self._cfg = cfg
        self._registry = ProviderRegistry()
        self._coindcx: CoinDCXProvider | None = None
        self._hyperliquid: HyperliquidProvider | None = None
        self._kraken: KrakenProvider | None = None
        self._binance: BinanceFuturesProvider | None = None
        self._bybit: BybitProvider | None = None
        self._coinglass: CoinGlassProvider | None = None
        self._gdelt: GDELTProvider | None = None
        self._fred: FREDProvider | None = None
        self._tokenunlocks: TokenUnlocksProvider | None = None
        # Bounded trade buffer (per venue) — capped at 200 trades per pair.
        self._trade_buffers: dict[str, RingBuffer] = {}
        # Bounded liquidation buffer — 200 events per pair.
        self._liquidation_buffers: dict[str, RingBuffer] = {}

    async def __aenter__(self) -> "DataManager":
        await self.start()
        return self

    async def __aexit__(self, *_args: object) -> None:
        await self.stop()

    async def start(self) -> None:
        # Single shared session for all REST providers.
        timeout = aiohttp.ClientTimeout(total=self._cfg.request_timeout_sec)
        session = aiohttp.ClientSession(timeout=timeout)
        self._shared_session = session

        self._coindcx = CoinDCXProvider(
            rest_url=self._cfg.coindcx_rest_url,
            session=session,
            rate_per_sec=4.0,
        )
        self._hyperliquid = HyperliquidProvider(
            rest_url=self._cfg.hyperliquid_rest_url,
            ws_url=self._cfg.hyperliquid_ws_url,
            session=session,
            rate_per_sec=8.0,
        )
        self._kraken = KrakenProvider(
            rest_url=self._cfg.kraken_rest_url,
            ws_url=self._cfg.kraken_ws_url,
            session=session,
            rate_per_sec=2.0,
        )
        self._binance = BinanceFuturesProvider(
            rest_url=self._cfg.binance_fapi_rest_url,
            ws_url=self._cfg.binance_fapi_ws_url,
            session=session,
            rate_per_sec=8.0,
        )
        self._bybit = BybitProvider(
            rest_url=self._cfg.bybit_rest_url,
            ws_url=self._cfg.bybit_ws_url,
            session=session,
            rate_per_sec=6.0,
        )
        self._coinglass = CoinGlassProvider(
            base_url=self._cfg.coinglass_url,
            api_key=self._cfg.coinglass_api_key,
            session=session,
            rate_per_sec=1.0,
        )
        self._gdelt = GDELTProvider(
            base_url=self._cfg.gdelt_url,
            session=session,
            rate_per_sec=0.5,
        )
        self._fred = FREDProvider(
            base_url=self._cfg.fred_url,
            api_key=self._cfg.fred_api_key,
            session=session,
            rate_per_sec=0.2,
        )
        self._tokenunlocks = TokenUnlocksProvider(
            base_url=self._cfg.tokenunlocks_url,
            session=session,
            rate_per_sec=0.2,
        )
        for p in (
            self._coindcx, self._hyperliquid, self._kraken,
            self._binance, self._bybit, self._coinglass,
            self._gdelt, self._fred, self._tokenunlocks,
        ):
            self._registry.register(p)
        log.x_info("data_manager started", extras={
            "providers": list(self._registry.all().keys()),
        })

    async def stop(self) -> None:
        await self._registry.close_all()
        # Close the shared session if we still hold it.
        session = getattr(self, "_shared_session", None)
        if session is not None and not session.closed:
            await session.close()
            self._shared_session = None

    @property
    def registry(self) -> ProviderRegistry:
        return self._registry

    @property
    def coindcx(self) -> CoinDCXProvider:
        assert self._coindcx is not None
        return self._coindcx

    @property
    def hyperliquid(self) -> HyperliquidProvider:
        assert self._hyperliquid is not None
        return self._hyperliquid

    @property
    def kraken(self) -> KrakenProvider:
        assert self._kraken is not None
        return self._kraken

    @property
    def binance(self) -> BinanceFuturesProvider:
        assert self._binance is not None
        return self._binance

    @property
    def bybit(self) -> BybitProvider:
        assert self._bybit is not None
        return self._bybit

    @property
    def coinglass(self) -> CoinGlassProvider:
        assert self._coinglass is not None
        return self._coinglass

    @property
    def gdelt(self) -> GDELTProvider:
        assert self._gdelt is not None
        return self._gdelt

    @property
    def fred(self) -> FREDProvider:
        assert self._fred is not None
        return self._fred

    @property
    def tokenunlocks(self) -> TokenUnlocksProvider:
        assert self._tokenunlocks is not None
        return self._tokenunlocks

    async def verify_futures_universe(self) -> bool:
        """Verify CoinDCX futures instrument list."""
        if self._coindcx is None:
            return False
        _, verified = await self._coindcx.verify_futures_universe()
        return verified

    def _trade_buffer(self, key: str) -> RingBuffer:
        if key not in self._trade_buffers:
            self._trade_buffers[key] = RingBuffer(maxlen=200)
        return self._trade_buffers[key]

    def _liquidation_buffer(self, key: str) -> RingBuffer:
        if key not in self._liquidation_buffers:
            self._liquidation_buffers[key] = RingBuffer(maxlen=200)
        return self._liquidation_buffers[key]

    async def fetch_pair_snapshot(
        self,
        pair: PairConfig,
        coindcx_tickers: dict[str, Ticker] | None = None,
    ) -> PairSnapshot:
        """Fetch all data sources for a pair in parallel.

        If `coindcx_tickers` is provided (a dict keyed by CoinDCX spot symbol),
        we look up the ticker from that cache instead of fetching the full
        ticker list again. This avoids 10x redundant full-list fetches per
        decision cycle.
        """
        snap = PairSnapshot(pair=pair, timestamp=now_ts())
        tasks: list[tuple[str, Any]] = []

        # CoinDCX (execution truth — required).
        if coindcx_tickers is not None and pair.coindcx_spot_symbol in coindcx_tickers:
            # Use cached ticker (already fetched once per decision cycle).
            cached_ticker = coindcx_tickers[pair.coindcx_spot_symbol]
            snap.coindcx_ticker = cached_ticker
            # Still need book, candles, trades (these are per-pair).
            tasks.append(("coindcx_book", self._safe(
                self._coindcx.get_orderbook(pair.coindcx_spot_symbol, depth=50), default=None
            )))
            tasks.append(("coindcx_candles", self._safe(
                self._coindcx.get_candles(pair.coindcx_spot_symbol, "1m", 200), default=[]
            )))
            tasks.append(("coindcx_trades", self._safe(
                self._coindcx.get_recent_trades(pair.coindcx_spot_symbol, 50), default=[]
            )))
        else:
            # Fallback: fetch ticker per-pair (slower, used when cache miss).
            tasks.append(("coindcx_ticker", self._safe(
                self._coindcx.get_ticker(pair.coindcx_spot_symbol), default=None
            )))
            tasks.append(("coindcx_book", self._safe(
                self._coindcx.get_orderbook(pair.coindcx_spot_symbol, depth=50), default=None
            )))
            tasks.append(("coindcx_candles", self._safe(
                self._coindcx.get_candles(pair.coindcx_spot_symbol, "1m", 200), default=[]
            )))
            tasks.append(("coindcx_trades", self._safe(
                self._coindcx.get_recent_trades(pair.coindcx_spot_symbol, 50), default=[]
            )))

        # External discovery — primary first.
        if pair.primary_discovery == "binance":
            tasks.append(("binance_ticker", self._safe(
                self._binance.get_ticker(pair.binance_symbol), default=None
            )))
            tasks.append(("binance_book", self._safe(
                self._binance.get_orderbook(pair.binance_symbol, 50), default=None
            )))
            tasks.append(("binance_candles", self._safe(
                self._binance.get_candles(pair.binance_symbol, "1m", 200), default=[]
            )))
            tasks.append(("binance_funding", self._safe(
                self._binance.get_funding(pair.binance_symbol), default=None
            )))
            tasks.append(("binance_oi", self._safe(
                self._binance.get_open_interest(pair.binance_symbol), default=None
            )))
        elif pair.primary_discovery == "bybit":
            tasks.append(("bybit_ticker", self._safe(
                self._bybit.get_ticker(pair.bybit_symbol or pair.binance_symbol), default=None
            )))
            tasks.append(("bybit_book", self._safe(
                self._bybit.get_orderbook(pair.bybit_symbol or pair.binance_symbol, 50), default=None
            )))
            tasks.append(("bybit_candles", self._safe(
                self._bybit.get_candles(pair.bybit_symbol or pair.binance_symbol, "1", 200), default=[]
            )))
            tasks.append(("bybit_funding", self._safe(
                self._bybit.get_funding(pair.bybit_symbol or pair.binance_symbol), default=None
            )))
            tasks.append(("bybit_oi", self._safe(
                self._bybit.get_open_interest(pair.bybit_symbol or pair.binance_symbol), default=None
            )))

        # Hyperliquid — primary for DOGE; secondary for others.
        if pair.hyperliquid_asset:
            tasks.append(("hl_ticker", self._safe(
                self._hyperliquid.get_ticker_for_asset(pair.hyperliquid_asset), default=None
            )))
            tasks.append(("hl_book", self._safe(
                self._hyperliquid.fetch_l2_book(pair.hyperliquid_asset), default=None
            )))
            tasks.append(("hl_candles", self._safe(
                self._hyperliquid.fetch_candles(pair.hyperliquid_asset, "1m", 200), default=[]
            )))
            tasks.append(("hl_funding_oi", self._safe(
                self._hyperliquid.fetch_funding_and_oi(pair.hyperliquid_asset), default=(None, None)
            )))

        # Kraken spot anchor.
        if pair.kraken_pair:
            tasks.append(("kraken_ticker", self._safe(
                self._kraken.get_ticker(pair.kraken_pair), default=None
            )))
            tasks.append(("kraken_book", self._safe(
                self._kraken.get_orderbook(pair.kraken_pair, 50), default=None
            )))

        # CoinGlass liquidations (if API key configured).
        tasks.append(("liquidations", self._safe(
            self._coinglass.get_liquidations(pair.binance_symbol, 50), default=[]
        )))

        # Run in parallel — cap concurrency at the registry level via rate limiters.
        keys = [k for k, _ in tasks]
        coros = [c for _, c in tasks]
        results = await asyncio.gather(*coros, return_exceptions=False)

        for key, value in zip(keys, results):
            self._apply_snapshot(snap, key, value)

        return snap

    def _apply_snapshot(self, snap: PairSnapshot, key: str, value: Any) -> None:
        if value is None:
            return
        if key == "coindcx_ticker":
            snap.coindcx_ticker = value
        elif key == "coindcx_book":
            snap.coindcx_book = value
        elif key == "coindcx_candles":
            snap.coindcx_candles = value
        elif key == "coindcx_trades":
            snap.trades_by_venue["coindcx"] = value
            buf = self._trade_buffer(f"coindcx:{snap.pair.base}")
            buf.extend(value)
        elif key == "binance_ticker":
            snap.external_tickers["binance"] = value
        elif key == "binance_book":
            snap.external_books["binance"] = value
        elif key == "binance_candles":
            snap.binance_candles = value
        elif key == "binance_funding":
            if value is not None:
                snap.funding["binance"] = value
        elif key == "binance_oi":
            if value is not None:
                snap.open_interest["binance"] = value
        elif key == "bybit_ticker":
            snap.external_tickers["bybit"] = value
        elif key == "bybit_book":
            snap.external_books["bybit"] = value
        elif key == "bybit_candles":
            snap.binance_candles = value  # share slot — bybit is fallback
        elif key == "bybit_funding":
            if value is not None:
                snap.funding["bybit"] = value
        elif key == "bybit_oi":
            if value is not None:
                snap.open_interest["bybit"] = value
        elif key == "hl_ticker":
            snap.external_tickers["hyperliquid"] = value
        elif key == "hl_book":
            snap.external_books["hyperliquid"] = value
        elif key == "hl_candles":
            snap.hl_candles = value
        elif key == "hl_funding_oi":
            funding, oi = value  # type: ignore[misc]
            if funding is not None:
                snap.funding["hyperliquid"] = funding
            if oi is not None:
                snap.open_interest["hyperliquid"] = oi
        elif key == "kraken_ticker":
            snap.external_tickers["kraken"] = value
        elif key == "kraken_book":
            snap.external_books["kraken"] = value
        elif key == "liquidations":
            snap.liquidations = value
            buf = self._liquidation_buffer(snap.pair.base)
            buf.extend(value)

    async def _safe(self, coro: Any, default: Any = None) -> Any:
        try:
            return await coro
        except (ProviderUnavailable, Exception) as exc:  # pragma: no cover - defensive
            log.x_debug("data fetch failed", extras={"err": str(exc)})
            return default

    def get_trade_history(self, venue: str, base: str) -> list[Trade]:
        return self._trade_buffer(f"{venue}:{base}").snapshot()

    def get_liquidation_history(self, base: str) -> list[Liquidation]:
        return self._liquidation_buffer(base).snapshot()

    def validate_ticker(self, t: Ticker | None, venue: str) -> bool:
        if t is None:
            return False
        max_age = self._cfg.max_data_age_sec.get("ticker", 30)
        if age_sec(t.timestamp) > max_age:
            return False
        if not (t.bid > 0 and t.ask > 0 and t.mid > 0):
            return False
        if t.ask < t.bid:
            return False
        # Impossible spread filter: >5000 bps (50%) is suspicious.
        if t.spread_bps > 5000:
            return False
        return True

    def validate_book(self, book: OrderBookSnapshot | None) -> bool:
        if book is None:
            return False
        max_age = self._cfg.max_data_age_sec.get("orderbook", 15)
        if age_sec(book.timestamp) > max_age:
            return False
        if not book.bids or not book.asks:
            return False
        return True
