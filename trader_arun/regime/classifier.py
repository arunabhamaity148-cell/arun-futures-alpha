"""Transparent regime classifier.

States (research §7):
TREND_UP, TREND_DOWN, RANGE, LOW_VOL, HIGH_VOL, POST_LIQUIDATION,
LIQUIDITY_STRESS, EVENT_RISK, CROSS_EXCHANGE_DISLOCATION, UNKNOWN.

Rules-based with calibrated thresholds. HMM is intentionally NOT used to
avoid convergence races on the hot path.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np

from ..core.types import Regime
from ..data.manager import PairSnapshot


@dataclass
class RegimeAssessment:
    regime: Regime
    confidence: float                  # 0–100
    components: dict[str, float]
    timestamp: float


class RegimeEngine:
    """Rule-based regime classifier."""

    def __init__(self, lookback: int = 60) -> None:
        self._lookback = int(lookback)

    def classify(
        self,
        snap: PairSnapshot,
        analyser_state: dict[str, Any],
    ) -> RegimeAssessment:
        components: dict[str, float] = {}
        candles = snap.coindcx_candles or snap.binance_candles or snap.hl_candles
        if not candles or len(candles) < 20:
            return RegimeAssessment(
                regime=Regime.UNKNOWN, confidence=0.0,
                components={"reason": "insufficient candles"},
                timestamp=__import__("time").time(),
            )

        closes = np.array([c.close for c in candles[-self._lookback:]], dtype=float)
        returns = np.diff(np.log(closes))
        vol = float(np.std(returns)) if len(returns) > 1 else 0.0
        drift = float(np.sum(returns)) if len(returns) > 0 else 0.0
        components["vol_1m"] = vol
        components["drift_60m"] = drift

        # Trend strength: t-stat = drift / (vol / sqrt(n))
        n = max(1, len(returns))
        t_stat = drift / (vol / math.sqrt(n)) if vol > 0 else 0.0
        components["trend_t_stat"] = t_stat
        # Economic significance filter: if total drift is < 0.5%, it's RANGE
        # regardless of t-stat (low-vol regimes can produce huge t-stats from
        # economically meaningless drifts).
        drift_magnitude = abs(drift)
        components["drift_magnitude"] = drift_magnitude

        # Volatility regime.
        long_closes = np.array([c.close for c in candles[-240:]], dtype=float) if len(candles) >= 240 else closes
        long_returns = np.diff(np.log(long_closes))
        long_vol = float(np.std(long_returns)) if len(long_returns) > 1 else vol
        vol_ratio = vol / long_vol if long_vol > 0 else 1.0
        components["vol_ratio"] = vol_ratio

        # Cross-exchange dislocation.
        coindcx_mid = snap.coindcx_ticker.mid if snap.coindcx_ticker else 0.0
        ext_mid = 0.0
        for v in snap.external_tickers.values():
            ext_mid = v.mid
            break
        if coindcx_mid > 0 and ext_mid > 0:
            dislocation_bps = abs(coindcx_mid - ext_mid) / ext_mid * 1e4
        else:
            dislocation_bps = 0.0
        components["dislocation_bps"] = dislocation_bps

        # Cascade signal.
        cascade_report = analyser_state.get("cascade_report")
        cascade_active = (
            cascade_report is not None
            and getattr(cascade_report, "cascade_index", 0.0) >= 1.5
        )
        components["cascade_index"] = getattr(cascade_report, "cascade_index", 0.0)

        # News state.
        news_state = analyser_state.get("news_state")
        news_block = (
            news_state is not None
            and str(getattr(news_state, "action", "ALLOW")).upper() == "BLOCK"
        )

        # Liquidity stress.
        spread_bps = snap.coindcx_ticker.spread_bps if snap.coindcx_ticker else 0.0
        book = snap.coindcx_book
        if book is not None:
            bid_d, ask_d = book.depth_within_pct(0.05)
            depth_usd = bid_d + ask_d
        else:
            depth_usd = 0.0
        components["spread_bps"] = spread_bps
        components["depth_5pct_usd"] = depth_usd
        liquidity_stress = spread_bps > 50 or depth_usd < 50_000

        # Decide regime.
        if news_block:
            regime = Regime.EVENT_RISK
            confidence = 90.0
        elif cascade_active and getattr(cascade_report, "is_exhausting", False):
            regime = Regime.POST_LIQUIDATION
            confidence = 75.0
        elif cascade_active:
            regime = Regime.LIQUIDITY_STRESS
            confidence = 70.0
        elif dislocation_bps > 50:
            regime = Regime.CROSS_EXCHANGE_DISLOCATION
            confidence = 65.0
        elif liquidity_stress:
            regime = Regime.LIQUIDITY_STRESS
            confidence = 60.0
        elif vol_ratio > 1.8:
            regime = Regime.HIGH_VOL
            confidence = 70.0
        elif vol_ratio < 0.5:
            regime = Regime.LOW_VOL
            confidence = 65.0
        elif drift_magnitude < 0.005:
            # Economic drift < 0.5% → RANGE, regardless of statistical t-stat.
            regime = Regime.RANGE
            confidence = 60.0
        elif t_stat > 2.5:
            regime = Regime.TREND_UP
            confidence = min(85.0, 50.0 + 10.0 * t_stat)
        elif t_stat < -2.5:
            regime = Regime.TREND_DOWN
            confidence = min(85.0, 50.0 + 10.0 * abs(t_stat))
        elif abs(t_stat) < 1.0:
            regime = Regime.RANGE
            confidence = 60.0
        else:
            regime = Regime.UNKNOWN
            confidence = 30.0

        return RegimeAssessment(
            regime=regime, confidence=confidence,
            components=components, timestamp=__import__("time").time(),
        )
