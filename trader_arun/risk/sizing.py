"""Risk-based position sizing.

size_usd = (equity × risk_pct × size_multiplier) / stop_distance_pct
clipped to:
  - max notional cap
  - max leverage × equity
  - book depth cap (max 5% of 5% depth)
  - correlated exposure cap
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class SizeResult:
    size_usd: float
    size_base: float
    leverage: float
    clipped: bool
    reasons: list[str]


class PositionSizer:
    def __init__(
        self,
        equity_usd: float = 10_000.0,
        risk_pct: float = 0.01,
        max_leverage: float = 10.0,
        max_notional_usd: float = 50_000.0,
        max_book_impact_pct: float = 0.05,
    ) -> None:
        self._equity = float(equity_usd)
        self._risk_pct = float(risk_pct)
        self._max_lev = float(max_leverage)
        self._max_notional = float(max_notional_usd)
        self._max_book_impact = float(max_book_impact_pct)

    def size(
        self,
        entry_price: float,
        stop_price: float,
        book_depth_5pct_usd: float,
        size_multiplier: float = 1.0,
        correlated_exposure_usd: float = 0.0,
        max_correlated_usd: float = 20_000.0,
    ) -> SizeResult:
        if entry_price <= 0 or stop_price <= 0:
            return SizeResult(0.0, 0.0, 0.0, True, ["invalid entry/stop"])
        if size_multiplier <= 0:
            return SizeResult(0.0, 0.0, 0.0, True, ["size multiplier zero"])

        stop_distance_pct = abs(entry_price - stop_price) / entry_price
        if stop_distance_pct <= 0:
            return SizeResult(0.0, 0.0, 0.0, True, ["stop distance zero"])

        risk_usd = self._equity * self._risk_pct * size_multiplier
        size_usd = risk_usd / stop_distance_pct
        reasons: list[str] = []
        clipped = False

        # Cap 1: max leverage.
        max_lev_notional = self._equity * self._max_lev
        if size_usd > max_lev_notional:
            size_usd = max_lev_notional
            clipped = True
            reasons.append(f"capped at max leverage {self._max_lev}x")

        # Cap 2: max notional.
        if size_usd > self._max_notional:
            size_usd = self._max_notional
            clipped = True
            reasons.append(f"capped at max notional ${self._max_notional:,.0f}")

        # Cap 3: book depth (max 5% of 5% depth).
        if book_depth_5pct_usd > 0:
            book_cap = book_depth_5pct_usd * self._max_book_impact / 0.05 * 0.05  # = depth × 5%
            book_cap = book_depth_5pct_usd * 0.05  # 5% of available 5%-depth
            if size_usd > book_cap:
                size_usd = book_cap
                clipped = True
                reasons.append(f"capped at 5% of book depth (${book_cap:,.0f})")

        # Cap 4: correlated exposure.
        if max_correlated_usd > 0:
            remaining_corr = max_correlated_usd - correlated_exposure_usd
            if size_usd > remaining_corr:
                size_usd = max(0.0, remaining_corr)
                clipped = True
                reasons.append(f"capped by correlated exposure (${remaining_corr:,.0f})")

        size_base = size_usd / entry_price if entry_price > 0 else 0.0
        leverage = size_usd / self._equity if self._equity > 0 else 0.0
        return SizeResult(
            size_usd=size_usd, size_base=size_base,
            leverage=leverage, clipped=clipped, reasons=reasons,
        )

    @property
    def equity(self) -> float:
        return self._equity
