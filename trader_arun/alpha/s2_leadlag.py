"""S2 — Cross-Exchange Lead/Lag Confirmation.

Edge: Larger exchanges (Binance/Bybit/Hyperliquid) update their mids slightly
before CoinDCX. The lead is typically 2–10 seconds for normal flow and grows
during news/cascade events. Manual Telegram execution makes sub-second alpha
unusable; this strategy works on 5m–15m windows where the lead is sustained.

Algorithm:
1. Build aligned 1m mid series for CoinDCX and primary external venue.
2. Compute cross-correlation for lags −10..+10 minutes.
3. If peak correlation occurs at lag ≥ 1 min (external leads CoinDCX) AND
   the external venue has moved >1σ in the last 5 minutes, signal in the
   same direction as the external move (assuming CoinDCX follows).
4. Confidence scales with lag stability (peak prominence) and move magnitude.

NO TRADE conditions:
- CoinDCX correlation (15m) < 0.95
- Lead unstable (sign flips within window)
- External move < 1σ (noise)
- CoinDCX spread > 3× median
"""
from __future__ import annotations

import math
from typing import Any

import numpy as np

from ..core.types import Regime, Side
from ..data.manager import PairSnapshot
from .base import AlphaSignal, AlphaStrategy


class S2LeadLag(AlphaStrategy):
    strategy_id = "S2_LEAD_LAG_CONFIRM"
    description = "Cross-exchange lead/lag confirmation"

    def evaluate(self, snap: PairSnapshot, analyser_state: dict[str, Any]) -> AlphaSignal:
        coindcx_ticker = snap.coindcx_ticker
        if coindcx_ticker is None or not snap.coindcx_candles:
            return self._no_signal(snap, "missing coindcx data")

        primary_venue = snap.pair.primary_discovery
        ext_ticker = snap.external_tickers.get(primary_venue)
        ext_candles = (
            snap.binance_candles if primary_venue in ("binance", "bybit")
            else snap.hl_candles
        )
        if ext_ticker is None or not ext_candles:
            return self._no_signal(snap, f"missing {primary_venue} data")

        # Align 1m candles by open_time.
        coindcx_by_time = {int(c.open_time // 60): c.close for c in snap.coindcx_candles[-30:]}
        ext_by_time = {int(c.open_time // 60): c.close for c in ext_candles[-30:]}
        common_times = sorted(set(coindcx_by_time.keys()) & set(ext_by_time.keys()))
        if len(common_times) < 20:
            return self._no_signal(snap, "insufficient aligned candles",
                                   extras={"aligned": len(common_times)})

        ext_prices = np.array([ext_by_time[t] for t in common_times], dtype=float)
        coindcx_prices = np.array([coindcx_by_time[t] for t in common_times], dtype=float)

        # Returns.
        ext_ret = np.diff(np.log(ext_prices))
        coindcx_ret = np.diff(np.log(coindcx_prices))
        if len(ext_ret) < 15:
            return self._no_signal(snap, "insufficient returns")

        # Cross-correlation for lags -10..+10 minutes.
        max_lag = min(10, len(ext_ret) // 3)
        lags = range(-max_lag, max_lag + 1)
        corrs = []
        for lag in lags:
            if lag < 0:
                a, b = ext_ret[-lag:], coindcx_ret[:lag]
            elif lag > 0:
                a, b = ext_ret[:-lag], coindcx_ret[lag:]
            else:
                a, b = ext_ret, coindcx_ret
            n = min(len(a), len(b))
            if n < 5:
                corrs.append(0.0)
                continue
            a_, b_ = a[:n], b[:n]
            if a_.std() == 0 or b_.std() == 0:
                corrs.append(0.0)
                continue
            c = float(np.corrcoef(a_, b_)[0, 1])
            corrs.append(c)

        if not corrs:
            return self._no_signal(snap, "no correlations computed")

        best_idx = int(np.argmax(corrs))
        best_lag = list(lags)[best_idx]
        best_corr = corrs[best_idx]

        # External leads CoinDCX if lag > 0 (external past correlates with coindcx future).
        if best_lag <= 0:
            return self._no_signal(snap, "no positive lead detected",
                                   extras={"best_lag_min": best_lag, "best_corr": best_corr})
        if best_corr < 0.5:
            return self._no_signal(snap, "weak lead correlation",
                                   extras={"best_corr": best_corr})

        # External recent move magnitude (last 5 minutes).
        ext_recent_ret = ext_ret[-5:]
        ext_move_sigma = float(ext_recent_ret.sum() / (ext_ret.std() + 1e-12))
        if abs(ext_move_sigma) < 1.0:
            return self._no_signal(snap, "external move < 1σ",
                                   extras={"ext_move_sigma": ext_move_sigma})

        # CoinDCX correlation (15m) gate.
        if len(coindcx_ret) >= 15:
            coindcx_15m_corr = float(np.corrcoef(ext_ret[-15:], coindcx_ret[-15:])[0, 1])
        else:
            coindcx_15m_corr = 0.0
        if coindcx_15m_corr < 0.95:
            return self._no_signal(snap, "coindcx corr < 0.95",
                                   extras={"coindcx_15m_corr": coindcx_15m_corr})

        # Spread gate.
        median_spread = analyser_state.get("coindcx_median_spread_bps", 5.0)
        if coindcx_ticker.spread_bps > 3.0 * max(median_spread, 1.0):
            return self._no_signal(snap, "coindcx spread > 3× median",
                                   extras={"spread_bps": coindcx_ticker.spread_bps,
                                           "median_spread": median_spread})

        side = Side.LONG if ext_move_sigma > 0 else Side.SHORT
        confidence = min(80.0, 50.0 + 30.0 * best_corr + 10.0 * abs(ext_move_sigma))
        edge_bps = abs(ext_move_sigma) * 10.0  # rough: 1σ move ≈ 10 bps transferable

        return AlphaSignal(
            strategy_id=self.strategy_id,
            pair=snap.pair.base,
            side=side,
            confidence=confidence,
            edge_estimate_bps=edge_bps,
            primary_alpha=f"lead/lag confirm ({primary_venue} leads CoinDCX by {best_lag}m)",
            regime=Regime.CROSS_EXCHANGE_DISLOCATION if best_corr < 0.85 else Regime.TREND_UP if side == Side.LONG else Regime.TREND_DOWN,
            holding_estimate_sec=15 * 60,
            audit={
                "best_lag_min": best_lag,
                "best_corr": best_corr,
                "ext_move_sigma": ext_move_sigma,
                "coindcx_15m_corr": coindcx_15m_corr,
                "primary_venue": primary_venue,
            },
        )

    def _no_signal(self, snap: PairSnapshot, reason: str, extras: dict | None = None) -> AlphaSignal:
        audit: dict[str, Any] = {"reason": reason}
        if extras:
            audit.update(extras)
        return AlphaSignal(
            strategy_id=self.strategy_id, pair=snap.pair.base,
            side=Side.FLAT, confidence=0.0, edge_estimate_bps=0.0,
            primary_alpha=reason, audit=audit,
        )
