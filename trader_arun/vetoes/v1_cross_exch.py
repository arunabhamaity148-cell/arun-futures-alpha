"""V1 — Cross-exchange contradiction.

Trigger: CoinDCX last deviates > 95th percentile (default 30 bp) from the
median of 2+ external venues' mids over the last 5 minutes.

Severity: HARD when deviation > 60 bp (NO TRADE).
         SOFT when deviation 30–60 bp (raises risk score).
"""
from __future__ import annotations

import time
from typing import Any

from ..core.types import VetoReport, VetoSeverity
from .base import Veto, VetoContext


class V1CrossExchangeContradiction(Veto):
    veto_id = "V1"
    description = "Cross-exchange contradiction"

    def evaluate(self, ctx: VetoContext) -> VetoReport:
        snap = ctx.snap
        if snap.coindcx_ticker is None or not snap.external_tickers:
            return VetoReport(
                veto_id=self.veto_id, pair=snap.pair.base,
                severity=VetoSeverity.HARD, triggered=True,
                detail="missing CoinDCX or external data — fail-closed",
                components={}, timestamp=time.time(),
            )
        coindcx_mid = snap.coindcx_ticker.mid
        if coindcx_mid <= 0:
            return VetoReport(
                veto_id=self.veto_id, pair=snap.pair.base,
                severity=VetoSeverity.HARD, triggered=True,
                detail="CoinDCX mid invalid", components={}, timestamp=time.time(),
            )
        ext_mids = [t.mid for t in snap.external_tickers.values() if t.mid > 0]
        if len(ext_mids) < 1:
            return VetoReport(
                veto_id=self.veto_id, pair=snap.pair.base,
                severity=VetoSeverity.HARD, triggered=True,
                detail="no valid external mids", components={}, timestamp=time.time(),
            )
        median_ext = sorted(ext_mids)[len(ext_mids) // 2]
        deviation_bps = abs(coindcx_mid - median_ext) / median_ext * 1e4

        cfg = ctx.cfg
        hard_threshold = getattr(cfg, "mismatch_no_trade", 60.0) if cfg else 60.0
        soft_threshold = getattr(cfg, "mismatch_watch_max", 40.0) if cfg else 40.0
        # Meme-pair multiplier (more tolerant for high-vol meme coins).
        if snap.pair.base in ("PEPE", "DOGE"):
            hard_threshold *= 1.5
            soft_threshold *= 1.5

        triggered = deviation_bps >= soft_threshold
        if deviation_bps >= hard_threshold:
            severity = VetoSeverity.HARD
            detail = f"deviation {deviation_bps:.1f}bp >= {hard_threshold:.0f}bp HARD"
        elif deviation_bps >= soft_threshold:
            severity = VetoSeverity.SOFT
            detail = f"deviation {deviation_bps:.1f}bp in soft zone"
        else:
            severity = VetoSeverity.ADVISORY
            detail = f"deviation {deviation_bps:.1f}bp normal"

        return VetoReport(
            veto_id=self.veto_id, pair=snap.pair.base,
            severity=severity, triggered=triggered, detail=detail,
            components={
                "deviation_bps": deviation_bps,
                "hard_threshold": hard_threshold,
                "soft_threshold": soft_threshold,
                "coindcx_mid": coindcx_mid,
                "median_ext_mid": median_ext,
                "venues_compared": len(ext_mids),
            },
            timestamp=time.time(),
        )
