"""SL/TP builder — uses ATR and market structure, not arbitrary percentages."""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from ..core.types import Candle, Side


@dataclass
class SLTPResult:
    entry_zone_low: float
    entry_zone_high: float
    stop_loss: float
    tp1: float
    tp2: float
    tp3: float
    rr: float
    atr: float
    valid: bool
    reason: str = ""


class SLTPBuilder:
    """Build entry zone, SL, TP1/TP2/TP3 from ATR and structure."""

    def __init__(
        self,
        atr_period: int = 14,
        atr_mult_sl: float = 1.5,
        atr_mult_tp1: float = 3.0,
        atr_mult_tp2: float = 5.0,
        atr_mult_tp3: float = 8.0,
        min_rr: float = 1.5,
    ) -> None:
        self._atr_period = int(atr_period)
        self._sl_mult = float(atr_mult_sl)
        self._tp1_mult = float(atr_mult_tp1)
        self._tp2_mult = float(atr_mult_tp2)
        self._tp3_mult = float(atr_mult_tp3)
        self._min_rr = float(min_rr)

    def build(
        self,
        candles: list[Candle],
        side: Side,
        current_price: float,
        spread_bps: float = 0.0,
    ) -> SLTPResult:
        if not candles or len(candles) < self._atr_period:
            return SLTPResult(0, 0, 0, 0, 0, 0, 0, 0, False, "insufficient candles")
        if side == Side.FLAT:
            return SLTPResult(0, 0, 0, 0, 0, 0, 0, 0, False, "flat side")
        if current_price <= 0:
            return SLTPResult(0, 0, 0, 0, 0, 0, 0, 0, False, "invalid price")

        atr = self._compute_atr(candles[-self._atr_period * 3:])
        if atr <= 0 or not math.isfinite(atr):
            return SLTPResult(0, 0, 0, 0, 0, 0, 0, 0, False, "atr invalid")

        # Entry zone: current price ± 25% of ATR (within typical noise).
        entry_zone_low = current_price - 0.25 * atr
        entry_zone_high = current_price + 0.25 * atr

        # Adjust entry zone for spread (give some room).
        spread_price = current_price * spread_bps / 1e4
        entry_zone_low -= spread_price / 2
        entry_zone_high += spread_price / 2

        if side == Side.LONG:
            stop_loss = entry_zone_low - self._sl_mult * atr
            tp1 = current_price + self._tp1_mult * atr
            tp2 = current_price + self._tp2_mult * atr
            tp3 = current_price + self._tp3_mult * atr
        else:  # SHORT
            stop_loss = entry_zone_high + self._sl_mult * atr
            tp1 = current_price - self._tp1_mult * atr
            tp2 = current_price - self._tp2_mult * atr
            tp3 = current_price - self._tp3_mult * atr

        # R:R = (TP1 - entry) / (entry - SL).
        risk = abs(current_price - stop_loss)
        reward = abs(tp1 - current_price)
        if risk <= 0:
            return SLTPResult(0, 0, 0, 0, 0, 0, 0, 0, False, "zero risk")
        rr = reward / risk
        if rr < self._min_rr:
            return SLTPResult(
                entry_zone_low, entry_zone_high, stop_loss, tp1, tp2, tp3,
                rr, atr, False, f"R:R {rr:.2f} < {self._min_rr}",
            )

        # Sanity: TPs and SL must be on the correct side of current_price.
        if side == Side.LONG:
            if not (stop_loss < current_price < tp1 < tp2 < tp3):
                return SLTPResult(0, 0, 0, 0, 0, 0, 0, 0, False, "TP/SL ordering invalid (LONG)")
        else:
            if not (tp3 < tp2 < tp1 < current_price < stop_loss):
                return SLTPResult(0, 0, 0, 0, 0, 0, 0, 0, False, "TP/SL ordering invalid (SHORT)")

        return SLTPResult(
            entry_zone_low=entry_zone_low,
            entry_zone_high=entry_zone_high,
            stop_loss=stop_loss,
            tp1=tp1, tp2=tp2, tp3=tp3,
            rr=rr, atr=atr, valid=True,
        )

    def _compute_atr(self, candles: list[Candle]) -> float:
        if len(candles) < 2:
            return 0.0
        trs: list[float] = []
        for i in range(1, len(candles)):
            high = candles[i].high
            low = candles[i].low
            prev_close = candles[i-1].close
            tr = max(
                high - low,
                abs(high - prev_close),
                abs(low - prev_close),
            )
            trs.append(tr)
        if not trs:
            return 0.0
        # Simple moving average of TR over the last `atr_period` samples.
        window = trs[-self._atr_period:] if len(trs) >= self._atr_period else trs
        return float(np.mean(window))
