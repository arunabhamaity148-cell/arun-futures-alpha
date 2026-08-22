"""S4 — Order-Book Absorption / CVD Divergence.

Edge: When aggressive sell volume (negative CVD) fails to push price down —
i.e. passive buyers are absorbing — it signals large/informed participant
accumulation. Opposite for buy volume into stable price.

Trigger:
- AbsorptionResult.score >= 50
- AbsorptionResult.direction != FLAT
- CoinDCX book has depth > 100k USD within 5% (sufficient liquidity)
- OBI on CoinDCX aligns with direction (positive OBI for LONG setup)

Confidence scales with absorption score.
"""
from __future__ import annotations

import math
from typing import Any

from ..core.types import Regime, Side
from ..data.manager import PairSnapshot
from .base import AlphaSignal, AlphaStrategy


class S4AbsorptionCVD(AlphaStrategy):
    strategy_id = "S4_ABSORPTION_CVD"
    description = "Order-book absorption / CVD divergence"

    def evaluate(self, snap: PairSnapshot, analyser_state: dict[str, Any]) -> AlphaSignal:
        absorption = analyser_state.get("absorption_result")
        if absorption is None:
            return self._no_signal(snap, "no absorption result")

        if absorption.score < 50.0 or absorption.direction == Side.FLAT:
            return self._no_signal(snap, "absorption too weak",
                                   extras={"score": absorption.score})

        if snap.coindcx_book is None:
            return self._no_signal(snap, "missing coindcx book")

        bid_depth, ask_depth = snap.coindcx_book.depth_within_pct(0.05)
        if (bid_depth + ask_depth) < 100_000:
            return self._no_signal(snap, "coindcx book too thin",
                                   extras={"depth_5pct_usd": bid_depth + ask_depth})

        # OBI on CoinDCX should align with direction.
        if (bid_depth + ask_depth) > 0:
            coindcx_obi = (bid_depth - ask_depth) / (bid_depth + ask_depth)
        else:
            coindcx_obi = 0.0
        if absorption.direction == Side.LONG and coindcx_obi < -0.1:
            return self._no_signal(snap, "coindcx OBI disagrees",
                                   extras={"coindcx_obi": coindcx_obi})
        if absorption.direction == Side.SHORT and coindcx_obi > 0.1:
            return self._no_signal(snap, "coindcx OBI disagrees",
                                   extras={"coindcx_obi": coindcx_obi})

        # Confidence: absorption score + OBI alignment + CVD intensity.
        cvd_intensity = min(1.0, abs(absorption.cvd_z) / 3.0)
        obi_alignment = (1.0 - abs(coindcx_obi - (1.0 if absorption.direction == Side.LONG else -1.0)) / 2.0)
        confidence = min(80.0, absorption.score * 0.6 + 30.0 * cvd_intensity + 10.0 * obi_alignment)

        # Edge estimate: absorption plays tend to produce ~30–80 bps moves over 15m–6h.
        edge_bps = 60.0 * (confidence / 100.0) * 1.5

        return AlphaSignal(
            strategy_id=self.strategy_id,
            pair=snap.pair.base,
            side=absorption.direction,
            confidence=confidence,
            edge_estimate_bps=edge_bps,
            primary_alpha=f"absorption/CVD divergence (cvd_z={absorption.cvd_z:.2f})",
            regime=Regime.RANGE,
            holding_estimate_sec=2 * 3600,
            audit={
                "absorption_score": absorption.score,
                "cvd_z": absorption.cvd_z,
                "price_move_bps": absorption.price_move_bps,
                "obi_top": absorption.obi_top,
                "coindcx_obi_5pct": coindcx_obi,
                "coindcx_depth_5pct_usd": bid_depth + ask_depth,
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
