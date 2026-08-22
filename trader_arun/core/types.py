"""Shared type definitions: enums, dataclasses, TypedDicts.

Pure data — no I/O. Used across the entire pipeline.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Literal


class Side(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"
    FLAT = "FLAT"


class SignalGrade(str, Enum):
    A = "A"        # Strongest
    B = "B"
    C = "C"
    REJECTED = "REJECTED"


class RiskDecision(str, Enum):
    TRADE = "TRADE"
    REDUCED_RISK = "REDUCED_RISK"
    WATCH = "WATCH"
    NO_TRADE = "NO_TRADE"


class Regime(str, Enum):
    TREND_UP = "TREND_UP"
    TREND_DOWN = "TREND_DOWN"
    RANGE = "RANGE"
    LOW_VOL = "LOW_VOL"
    HIGH_VOL = "HIGH_VOL"
    POST_LIQUIDATION = "POST_LIQUIDATION"
    LIQUIDITY_STRESS = "LIQUIDITY_STRESS"
    EVENT_RISK = "EVENT_RISK"
    CROSS_EXCHANGE_DISLOCATION = "CROSS_EXCHANGE_DISLOCATION"
    UNKNOWN = "UNKNOWN"


class NewsAction(str, Enum):
    ALLOW = "ALLOW"
    REDUCE = "REDUCE"
    BLOCK = "BLOCK"


class ProviderState(str, Enum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    UNAVAILABLE = "UNAVAILABLE"
    CIRCUIT_OPEN = "CIRCUIT_OPEN"


class VetoSeverity(str, Enum):
    HARD = "HARD"        # forces NO_TRADE
    SOFT = "SOFT"        # increases risk score
    ADVISORY = "ADVISORY"


@dataclass(frozen=True)
class Ticker:
    """Normalized ticker across venues."""

    venue: str
    symbol: str           # venue-native symbol
    base: str
    quote: str
    bid: float
    ask: float
    last: float
    mid: float
    spread_bps: float
    timestamp: float      # unix seconds (provider time)
    received_at: float    # monotonic-local receive time


@dataclass(frozen=True)
class OrderBookSnapshot:
    venue: str
    symbol: str
    bids: list[tuple[float, float]]   # [(price, size), ...] descending price
    asks: list[tuple[float, float]]
    timestamp: float
    received_at: float

    def mid(self) -> float:
        if not self.bids or not self.asks:
            return float("nan")
        return (self.bids[0][0] + self.asks[0][0]) / 2.0

    def spread(self) -> float:
        if not self.bids or not self.asks:
            return float("nan")
        return self.asks[0][0] - self.bids[0][0]

    def depth_within_pct(self, pct: float) -> tuple[float, float]:
        """Return (bid_depth_usd, ask_depth_usd) within pct of mid."""
        if not self.bids or not self.asks:
            return (0.0, 0.0)
        m = self.mid()
        if m <= 0 or m != m:
            return (0.0, 0.0)
        bid_cutoff = m * (1.0 - pct)
        ask_cutoff = m * (1.0 + pct)
        bid_depth = sum(p * s for p, s in self.bids if p >= bid_cutoff)
        ask_depth = sum(p * s for p, s in self.asks if p <= ask_cutoff)
        return (bid_depth, ask_depth)


@dataclass(frozen=True)
class Candle:
    venue: str
    symbol: str
    tf: str            # "1m", "5m", "1h"
    open: float
    high: float
    low: float
    close: float
    volume: float
    open_time: float
    close_time: float


@dataclass(frozen=True)
class FundingRate:
    venue: str
    symbol: str
    rate: float          # 8h fractional (e.g. 0.0001 = 1bp)
    next_funding_time: float
    timestamp: float


@dataclass(frozen=True)
class OpenInterest:
    venue: str
    symbol: str
    oi_base: float       # contracts
    oi_usd: float        # notional USD
    timestamp: float


@dataclass(frozen=True)
class Liquidation:
    venue: str
    symbol: str
    side: Side           # LONG = long position liquidated
    price: float
    size_usd: float
    timestamp: float


@dataclass(frozen=True)
class Trade:
    venue: str
    symbol: str
    price: float
    size: float
    side: Literal["BUY", "SELL"]   # aggressor side
    timestamp: float


@dataclass
class MismatchReport:
    pair: str
    score: float            # 0–100
    components: dict[str, float]
    band: str               # NORMAL | WATCH | REDUCE | NO_TRADE
    timestamp: float


@dataclass
class TransferReport:
    pair: str
    score: float            # 0–100
    components: dict[str, float]
    timestamp: float


@dataclass
class InstitutionalFootprint:
    pair: str
    score: float                       # 0–100
    subscores: dict[str, float]
    label: str                         # "large/informed participant activity proxy"
    timestamp: float


@dataclass
class RiskAssessment:
    pair: str
    score: float                       # 0–100 (higher = riskier)
    components: dict[str, float]
    decision: RiskDecision
    size_multiplier: float             # 1.0 / 0.5 / 0.0
    reasons: list[str]
    timestamp: float


@dataclass
class VetoReport:
    veto_id: str                       # V1..V5
    pair: str
    severity: VetoSeverity
    triggered: bool
    detail: str
    components: dict[str, float]
    timestamp: float


@dataclass
class NewsItem:
    source: str
    headline: str
    severity: str                      # CRITICAL | HIGH | MEDIUM | LOW
    pair_tags: list[str]               # ["BTC","ETH","*"] for macro
    url: str
    published_at: float
    received_at: float


@dataclass
class NewsState:
    action: NewsAction
    blocking_items: list[NewsItem]
    reduce_items: list[NewsItem]
    cooldown_until: float
    timestamp: float


@dataclass
class PortfolioCrowding:
    score: float                       # 0–100
    btc_beta_avg: float
    eth_beta_avg: float
    sector_corr_avg: float
    pca_concentration: float           # share of variance from PC1
    directional_exposure: float        # net long/short notional/equity
    timestamp: float


@dataclass
class Signal:
    """Final premium ARUN Telegram signal."""

    signal_id: str
    brand: str = "ARUN"
    pair: str = ""
    coindcx_futures_symbol: str = ""   # NOT VERIFIED until live confirmation
    coindcx_spot_symbol: str = ""
    side: Side = Side.FLAT
    strategy: str = ""
    regime: Regime = Regime.UNKNOWN

    entry_zone_low: float = 0.0
    entry_zone_high: float = 0.0
    stop_loss: float = 0.0
    tp1: float = 0.0
    tp2: float = 0.0
    tp3: float = 0.0
    rr: float = 0.0
    leverage_min: float = 1.0
    leverage_max: float = 10.0
    risk_pct: float = 0.0
    confidence: float = 0.0            # 0–100
    grade: SignalGrade = SignalGrade.REJECTED

    primary_alpha: str = ""
    institutional_footprint: float = 0.0
    coindcx_match: float = 0.0         # 0–100
    transfer_score: float = 0.0
    liquidity_state: str = ""
    funding_context: str = ""
    oi_context: str = ""
    news_state: str = ""
    portfolio_crowding: float = 0.0

    validity_window_sec: float = 900.0
    valid_until: float = 0.0
    invalidation_condition: str = ""

    audit: dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["side"] = self.side.value
        d["grade"] = self.grade.value
        d["regime"] = self.regime.value
        return d


def new_signal_id() -> str:
    return f"ARUN-{uuid.uuid4().hex[:12].upper()}"


@dataclass
class ProviderHealth:
    name: str
    state: ProviderState
    last_success: float
    last_failure: float
    failures_in_window: int
    circuit_state: str
    latency_p95_sec: float
    timestamp: float
