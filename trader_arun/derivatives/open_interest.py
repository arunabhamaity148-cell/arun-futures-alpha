"""Open interest analyser — tracks ΔOI and impulse z-scores."""
from __future__ import annotations

import math
from dataclasses import dataclass

from ..core.rolling import RollingZScore
from ..core.types import OpenInterest


@dataclass
class OIReport:
    venue: str
    symbol: str
    oi_usd: float
    delta_usd: float
    delta_pct: float
    z_score: float
    is_impulse: bool         # z >= 2


class OpenInterestAnalyser:
    """Per-venue OI tracker."""

    __slots__ = ("_venue", "_symbol", "_z", "_prev_oi", "_delta_z")

    def __init__(self, venue: str, symbol: str, baseline_samples: int = 120) -> None:
        self._venue = venue
        self._symbol = symbol
        self._z = RollingZScore(maxlen=baseline_samples)
        self._prev_oi: float = 0.0
        self._delta_z = RollingZScore(maxlen=baseline_samples)

    def update(self, oi: OpenInterest) -> OIReport:
        self._z.update(oi.oi_usd)
        if self._prev_oi > 0:
            delta = oi.oi_usd - self._prev_oi
            delta_pct = delta / self._prev_oi
        else:
            delta = 0.0
            delta_pct = 0.0
        delta_z = self._delta_z.update(delta_pct)
        self._prev_oi = oi.oi_usd
        return OIReport(
            venue=self._venue,
            symbol=self._symbol,
            oi_usd=oi.oi_usd,
            delta_usd=delta,
            delta_pct=delta_pct,
            z_score=delta_z,
            is_impulse=abs(delta_z) >= 2.0,
        )
