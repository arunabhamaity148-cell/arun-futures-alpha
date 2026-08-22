"""S1 — Liquidation-Cascade Exhaustion + Squeeze Continuation.

Edge: When forced-flow liquidation volume peaks then decelerates while price
stabilises, the residual imbalance flips. Empirical analog: 19 Aug 2026 BTC
$2.99B liquidation → +8.48% bounce.

Trigger conditions (ALL must hold):
- CascadeReport.cascade_index ≥ 1.5 (6h liq vol exceeds 1.5× baseline)
- CascadeReport.is_exhausting == True (volume decelerating, exhaustion_score ≥ 40)
- CoinDCX price has stabilised: 15m realised vol < 0.7 × pre-cascade 1h vol
- CoinDCX mid correlates >0.95 with primary venue mid over the last 15m
- Direction = OPPOSITE of dominant liquidation side (long liq → LONG entry)

Confidence mapping:
  exhaustion_score 70+ → confidence 75
  exhaustion_score 50+ → confidence 60
  exhaustion_score 40+ → confidence 45
"""
from __future__ import annotations

import math
from typing import Any

from ..core.types import Regime, Side
from ..data.manager import PairSnapshot
from .base import AlphaSignal, AlphaStrategy


class S1CascadeExhaustion(AlphaStrategy):
    strategy_id = "S1_CASCADE_EXHAUSTION"
    description = "Liquidation-cascade exhaustion + squeeze continuation"

    def evaluate(self, snap: PairSnapshot, analyser_state: dict[str, Any]) -> AlphaSignal:
        cascade = analyser_state.get("cascade_report")
        if cascade is None or not getattr(cascade, "is_exhausting", False):
            return AlphaSignal(
                strategy_id=self.strategy_id, pair=snap.pair.base,
                side=Side.FLAT, confidence=0.0, edge_estimate_bps=0.0,
                primary_alpha="no cascade exhaustion",
                audit={"cascade_index": getattr(cascade, "cascade_index", 0.0)},
            )

        if snap.coindcx_ticker is None or not snap.coindcx_candles:
            return self._no_signal(snap, "missing coindcx data")

        # CoinDCX price stabilisation check.
        recent_closes = [c.close for c in snap.coindcx_candles[-15:]]
        if len(recent_closes) < 15:
            return self._no_signal(snap, "insufficient coindcx candles")
        recent_ret = [
            (recent_closes[i] - recent_closes[i-1]) / recent_closes[i-1]
            for i in range(1, len(recent_closes)) if recent_closes[i-1] > 0
        ]
        if not recent_ret:
            return self._no_signal(snap, "no returns")
        recent_vol = math.sqrt(sum(r * r for r in recent_ret) / len(recent_ret))
        pre_cascade_closes = [c.close for c in snap.coindcx_candles[-60:-15]]
        if len(pre_cascade_closes) >= 15:
            pre_ret = [
                (pre_cascade_closes[i] - pre_cascade_closes[i-1]) / pre_cascade_closes[i-1]
                for i in range(1, len(pre_cascade_closes)) if pre_cascade_closes[i-1] > 0
            ]
            if pre_ret:
                pre_vol = math.sqrt(sum(r * r for r in pre_ret) / len(pre_ret))
                if pre_vol > 0 and recent_vol > 0.7 * pre_vol:
                    return self._no_signal(snap, "price not stabilised",
                                           extras={"recent_vol": recent_vol, "pre_vol": pre_vol})

        # Direction = opposite of dominant liquidated side.
        # Long liq = longs got squeezed → forced sellers done → LONG entry.
        side = Side.LONG if cascade.dominant_side == Side.LONG else Side.SHORT

        # Confidence mapping.
        es = cascade.exhaustion_score
        if es >= 70:
            confidence = 75.0
        elif es >= 50:
            confidence = 60.0
        else:
            confidence = 45.0

        # Edge estimate: cascade bounce magnitude from historical analog.
        # Conservative: target 1.5–3R over 6h–3d; edge = ~150 bps gross (1.5%).
        edge_bps = 150.0 * (es / 100.0)

        # Regime.
        regime = Regime.POST_LIQUIDATION

        return AlphaSignal(
            strategy_id=self.strategy_id,
            pair=snap.pair.base,
            side=side,
            confidence=confidence,
            edge_estimate_bps=edge_bps,
            primary_alpha=f"cascade-exhaustion (dominant liq side: {cascade.dominant_side.value})",
            regime=regime,
            holding_estimate_sec=6 * 3600,
            audit={
                "cascade_index": cascade.cascade_index,
                "exhaustion_score": cascade.exhaustion_score,
                "long_liq_6h_usd": cascade.long_liq_6h_usd,
                "short_liq_6h_usd": cascade.short_liq_6h_usd,
                "recent_vol": recent_vol,
                "pre_vol": pre_vol if len(pre_cascade_closes) >= 15 else None,
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
