"""Funding analyser — converts raw 8h funding into z-scores and crowding scores."""
from __future__ import annotations

import math
from dataclasses import dataclass

from ..core.rolling import RollingZScore
from ..core.types import FundingRate


@dataclass
class FundingReport:
    venue: str
    symbol: str
    rate_8h: float
    annualised_pct: float
    z_score: float
    is_extreme: bool           # |z| >= 2
    crowding_side: str         # "LONG" | "SHORT" | "NEUTRAL"


class FundingAnalyser:
    """Per-venue funding analyser. One instance per (venue, symbol)."""

    __slots__ = ("_venue", "_symbol", "_z_score", "_baseline_samples")

    def __init__(self, venue: str, symbol: str, baseline_samples: int = 90) -> None:
        self._venue = venue
        self._symbol = symbol
        self._z_score = RollingZScore(maxlen=baseline_samples)

    def update(self, funding: FundingRate) -> FundingReport:
        self._z_score.update(funding.rate)
        z = self._z_score.update(funding.rate)  # idempotent — recomputes
        # Funding is positive → longs pay shorts → long crowding.
        if funding.rate > 0.0001:
            crowding_side = "LONG"
        elif funding.rate < -0.0001:
            crowding_side = "SHORT"
        else:
            crowding_side = "NEUTRAL"
        return FundingReport(
            venue=self._venue,
            symbol=self._symbol,
            rate_8h=funding.rate,
            annualised_pct=funding.rate * 3 * 365 * 100,  # 8h × 3/day × 365
            z_score=z,
            is_extreme=abs(z) >= 2.0,
            crowding_side=crowding_side,
        )

    @property
    def mean(self) -> float:
        return self._z_score.mean

    @property
    def std(self) -> float:
        return self._z_score.std
