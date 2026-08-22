"""Price-impact estimator — square-root impact model (Almgren-Chriss style).

Slippage estimate for a notional N against 5% book depth D:
    impact_bps = k * sqrt(N / D) * spread_factor

The constant k is calibrated from observed fills when available. Default k=10.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from ..core.types import OrderBookSnapshot


@dataclass
class ImpactEstimate:
    expected_slippage_bps: float
    expected_slippage_pct: float
    book_depth_5pct_usd: float
    is_illiquid: bool


class PriceImpactEstimator:
    """Estimate slippage for a given notional size."""

    __slots__ = ("_k", "_illiquid_threshold_usd")

    def __init__(self, k: float = 10.0, illiquid_threshold_usd: float = 250_000.0) -> None:
        self._k = float(k)
        self._illiquid_threshold_usd = float(illiquid_threshold_usd)

    def estimate(
        self,
        book: OrderBookSnapshot | None,
        notional_usd: float,
        side: str = "BUY",
    ) -> ImpactEstimate:
        if book is None or not book.bids or not book.asks:
            return ImpactEstimate(
                expected_slippage_bps=999.0,
                expected_slippage_pct=9.99,
                book_depth_5pct_usd=0.0,
                is_illiquid=True,
            )
        bid_depth, ask_depth = book.depth_within_pct(0.05)
        side_depth = ask_depth if side == "BUY" else bid_depth
        total_depth = bid_depth + ask_depth
        if side_depth <= 0:
            return ImpactEstimate(
                expected_slippage_bps=999.0,
                expected_slippage_pct=9.99,
                book_depth_5pct_usd=total_depth,
                is_illiquid=True,
            )
        # Square-root impact.
        ratio = notional_usd / side_depth
        if ratio < 0:
            ratio = 0
        # Cap ratio at 1.0 — beyond that, walking the book dominates.
        ratio = min(1.0, ratio)
        impact_bps = self._k * math.sqrt(ratio)
        is_illiquid = total_depth < self._illiquid_threshold_usd
        return ImpactEstimate(
            expected_slippage_bps=impact_bps,
            expected_slippage_pct=impact_bps / 100.0,
            book_depth_5pct_usd=total_depth,
            is_illiquid=is_illiquid,
        )
