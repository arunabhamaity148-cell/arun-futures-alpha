"""Basis analyser — perp vs spot basis z-score for mean-reversion detection."""
from __future__ import annotations

import math
from dataclasses import dataclass

from ..core.rolling import RollingZScore
from ..core.types import Ticker


@dataclass
class BasisReport:
    basis_bps: float           # perp - spot, in bps
    z_score: float
    is_extreme: bool           # |z| >= 2
    direction: str             # "PERP_PREMIUM" | "PERP_DISCOUNT" | "NEUTRAL"


class BasisAnalyser:
    """Compute perp vs spot basis z-score."""

    __slots__ = ("_z",)

    def __init__(self, baseline_samples: int = 240) -> None:
        self._z = RollingZScore(maxlen=baseline_samples)

    def update(self, perp: Ticker, spot: Ticker) -> BasisReport:
        if perp.mid <= 0 or spot.mid <= 0:
            return BasisReport(basis_bps=0.0, z_score=0.0, is_extreme=False, direction="NEUTRAL")
        basis_bps = (perp.mid - spot.mid) / spot.mid * 1e4
        z = self._z.update(basis_bps)
        is_extreme = abs(z) >= 2.0
        if basis_bps > 5 and is_extreme:
            direction = "PERP_PREMIUM"
        elif basis_bps < -5 and is_extreme:
            direction = "PERP_DISCOUNT"
        else:
            direction = "NEUTRAL"
        return BasisReport(
            basis_bps=basis_bps,
            z_score=z,
            is_extreme=is_extreme,
            direction=direction,
        )
