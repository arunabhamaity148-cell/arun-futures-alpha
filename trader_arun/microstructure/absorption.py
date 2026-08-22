"""Absorption detector.

Absorption = aggressive flow meets passive liquidity without price move.

Signal: high |CVD| (one-sided aggression) + small price move → opposite-side
absorption likely.

Output: ABSORPTION_SCORE ∈ [0, 100] and direction (LONG/SHORT/NEUTRAL).
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from ..core.types import OrderBookSnapshot, Side, Trade
from .cvd import CVDCalculator


@dataclass
class AbsorptionResult:
    score: float                  # 0–100
    direction: Side               # LONG = buyers absorbed sell-pressure (bullish)
    cvd_z: float
    price_move_bps: float
    obi_top: float


class AbsorptionDetector:
    """Detect absorption from CVD + price + OBI."""

    __slots__ = ("_cvd_calc", "_last_price", "_window_sec")

    def __init__(self, cvd_calc: CVDCalculator, window_sec: float = 300.0) -> None:
        self._cvd_calc = cvd_calc
        self._last_price: float = 0.0
        self._window_sec = float(window_sec)

    def update(
        self,
        trades: list[Trade],
        book: OrderBookSnapshot | None,
        current_price: float,
    ) -> AbsorptionResult:
        for t in trades:
            self._cvd_calc.update(t)
        cvd_z = self._cvd_calc.cvd_zscore()
        if self._last_price > 0:
            price_move_bps = (current_price - self._last_price) / self._last_price * 1e4
        else:
            price_move_bps = 0.0
        self._last_price = current_price

        obi_top = 0.0
        if book is not None and book.bids and book.asks:
            bid_top = sum(s for _, s in book.bids[:5])
            ask_top = sum(s for _, s in book.asks[:5])
            if (bid_top + ask_top) > 0:
                obi_top = (bid_top - ask_top) / (bid_top + ask_top)

        # Strong CVD + small price move → absorption.
        # Score formula: how extreme is CVD vs how muted is price response?
        cvd_intensity = min(1.0, abs(cvd_z) / 3.0)  # |z|>3 → saturation
        price_muted = max(0.0, 1.0 - abs(price_move_bps) / 10.0)  # |move|>10bp → no absorption
        score = 100.0 * cvd_intensity * price_muted

        # Direction: high sell aggression (negative CVD) absorbed → LONG setup.
        if cvd_z < -1.0 and price_muted > 0.4:
            direction = Side.LONG
        elif cvd_z > 1.0 and price_muted > 0.4:
            direction = Side.SHORT
        else:
            direction = Side.FLAT

        return AbsorptionResult(
            score=score,
            direction=direction,
            cvd_z=cvd_z,
            price_move_bps=price_move_bps,
            obi_top=obi_top,
        )
