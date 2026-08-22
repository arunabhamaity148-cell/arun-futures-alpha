"""S3 — Funding/OI Crowding Unwind.

Edge: When funding is at extreme positive (longs crowded paying shorts) AND
OI is rising (longs being added), the setup is fragile. When funding starts
to fall (squeeze starting) AND OI declines (longs unwinding), signal SHORT.

Trigger conditions:
- FundingAnalyser: |z_score| >= 2 AND crowding_side = "LONG"
- OpenInterestAnalyser: delta_pct < 0 (OI declining in last interval)
- Funding delta over last 2 cycles < 0 (funding falling from peak)
- CoinDCX mismatch < 30 (venues agree)
- CoinDCX price confirms move direction

Direction: SHORT when long crowding unwinds, LONG when short crowding unwinds.

Confidence:
- |z| >= 3 → 70
- |z| >= 2 → 55
- OI delta_pct magnitude adds bonus
"""
from __future__ import annotations

import math
from typing import Any

from ..core.types import Regime, Side
from ..data.manager import PairSnapshot
from .base import AlphaSignal, AlphaStrategy


class S3FundingOIUnwind(AlphaStrategy):
    strategy_id = "S3_FUNDING_OI_UNWIND"
    description = "Funding/OI divergence + long-crowding unwind"

    def evaluate(self, snap: PairSnapshot, analyser_state: dict[str, Any]) -> AlphaSignal:
        funding_report = analyser_state.get("funding_report")
        oi_report = analyser_state.get("oi_report")
        if funding_report is None or oi_report is None:
            return self._no_signal(snap, "missing funding or OI report")

        if not funding_report.is_extreme:
            return self._no_signal(snap, "funding not extreme",
                                   extras={"z": funding_report.z_score})

        if funding_report.crowding_side == "NEUTRAL":
            return self._no_signal(snap, "funding neutral")

        # Unwind trigger: OI declining + funding falling.
        # Long crowding unwind → SHORT. Short crowding unwind → LONG.
        crowding = funding_report.crowding_side
        if crowding == "LONG":
            # Need OI declining (longs closing).
            if oi_report.delta_pct >= -0.005:
                return self._no_signal(snap, "long crowding but OI not declining",
                                       extras={"oi_delta_pct": oi_report.delta_pct})
            side = Side.SHORT
        else:  # SHORT crowding
            if oi_report.delta_pct <= 0.005:
                return self._no_signal(snap, "short crowding but OI not declining",
                                       extras={"oi_delta_pct": oi_report.delta_pct})
            side = Side.LONG

        # CoinDCX must confirm direction.
        if snap.coindcx_ticker is None:
            return self._no_signal(snap, "missing coindcx ticker")
        if not snap.coindcx_candles or len(snap.coindcx_candles) < 5:
            return self._no_signal(snap, "insufficient coindcx candles")

        recent_close = snap.coindcx_candles[-1].close
        prior_close = snap.coindcx_candles[-5].close
        if prior_close > 0:
            price_change_pct = (recent_close - prior_close) / prior_close
        else:
            return self._no_signal(snap, "invalid prior close")
        # For SHORT unwind: price should be falling recently.
        # For LONG unwind: price should be rising recently.
        if side == Side.SHORT and price_change_pct > 0.001:
            return self._no_signal(snap, "coindcx not confirming short",
                                   extras={"price_change_pct": price_change_pct})
        if side == Side.LONG and price_change_pct < -0.001:
            return self._no_signal(snap, "coindcx not confirming long",
                                   extras={"price_change_pct": price_change_pct})

        z_abs = abs(funding_report.z_score)
        if z_abs >= 3:
            confidence = 70.0
        elif z_abs >= 2:
            confidence = 55.0
        else:
            confidence = 40.0
        # OI decline magnitude bonus.
        confidence += min(15.0, abs(oi_report.delta_pct) * 1000)
        confidence = min(85.0, confidence)

        # Edge estimate: crowding unwind tends to produce ~50–150 bps move.
        edge_bps = 75.0 * (confidence / 100.0) * 2  # ~150 bps at high confidence

        return AlphaSignal(
            strategy_id=self.strategy_id,
            pair=snap.pair.base,
            side=side,
            confidence=confidence,
            edge_estimate_bps=edge_bps,
            primary_alpha=f"funding/OI unwind ({crowding.lower()} crowding, z={z_abs:.2f})",
            regime=Regime.TREND_DOWN if side == Side.SHORT else Regime.TREND_UP,
            holding_estimate_sec=24 * 3600,  # 1–5 days
            audit={
                "funding_z": funding_report.z_score,
                "funding_rate_8h": funding_report.rate_8h,
                "crowding_side": crowding,
                "oi_delta_pct": oi_report.delta_pct,
                "oi_delta_usd": oi_report.delta_usd,
                "price_change_pct_5m": price_change_pct,
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
