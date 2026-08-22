"""S5 — Perp-Basis vs Spot Convergence.

Edge: When perp basis (perp mid - spot mid) reaches an extreme z-score,
arbitrage pressure mechanically pulls it back to mean.

Trigger:
- |basis_z| >= 2.0
- CoinDCX spread is reasonable (< 3× median)
- Funding is not in event-day territory (|rate_8h| < 0.001)

Direction:
- PERP_PREMIUM (perp > spot, basis_z > +2): SHORT perp / hedge with spot
  → for signal-only bot, signal SHORT (expecting perp to revert down)
- PERP_DISCOUNT (perp < spot, basis_z < -2): LONG perp

NOTE: Single-leg signal — bot does NOT execute spot hedge. Operator must
manage basis risk manually if attempting two-leg arb.
"""
from __future__ import annotations

import math
from typing import Any

from ..core.types import Regime, Side
from ..data.manager import PairSnapshot
from .base import AlphaSignal, AlphaStrategy


class S5BasisConvergence(AlphaStrategy):
    strategy_id = "S5_BASIS_CONVERGENCE"
    description = "Perp-basis vs spot convergence"

    def evaluate(self, snap: PairSnapshot, analyser_state: dict[str, Any]) -> AlphaSignal:
        basis_report = analyser_state.get("basis_report")
        if basis_report is None or not basis_report.is_extreme:
            return self._no_signal(snap, "basis not extreme",
                                   extras={"basis_z": getattr(basis_report, "z_score", 0)})

        # Need both perp and spot on CoinDCX (or external proxy).
        if snap.coindcx_ticker is None:
            return self._no_signal(snap, "missing coindcx ticker")

        # Check funding event-day filter.
        funding_report = analyser_state.get("funding_report")
        if funding_report is not None and abs(funding_report.rate_8h) >= 0.001:
            return self._no_signal(snap, "funding event-day — basis unstable",
                                   extras={"funding_8h": funding_report.rate_8h})

        # Spread gate.
        median_spread = analyser_state.get("coindcx_median_spread_bps", 5.0)
        if snap.coindcx_ticker.spread_bps > 3.0 * max(median_spread, 1.0):
            return self._no_signal(snap, "coindcx spread too wide",
                                   extras={"spread_bps": snap.coindcx_ticker.spread_bps})

        z = basis_report.z_score
        if basis_report.direction == "PERP_PREMIUM":
            side = Side.SHORT
        elif basis_report.direction == "PERP_DISCOUNT":
            side = Side.LONG
        else:
            return self._no_signal(snap, "basis direction neutral")

        # Confidence scales with |z|.
        z_abs = abs(z)
        if z_abs >= 3:
            confidence = 65.0
        elif z_abs >= 2:
            confidence = 50.0
        else:
            confidence = 35.0

        # Edge estimate: basis reversion magnitude = |basis_bps| × 0.6 (conservative).
        edge_bps = abs(basis_report.basis_bps) * 0.6

        return AlphaSignal(
            strategy_id=self.strategy_id,
            pair=snap.pair.base,
            side=side,
            confidence=confidence,
            edge_estimate_bps=edge_bps,
            primary_alpha=f"basis convergence ({basis_report.direction}, z={z:.2f})",
            regime=Regime.RANGE,
            holding_estimate_sec=4 * 3600,
            audit={
                "basis_bps": basis_report.basis_bps,
                "basis_z": basis_report.z_score,
                "direction": basis_report.direction,
                "funding_8h": funding_report.rate_8h if funding_report else None,
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
