"""V3 — Liquidity vacuum.

Trigger: CoinDCX book depth within 5% of mid is <10% of the primary venue's
depth, OR CoinDCX spread > 5× median.

Severity: HARD (always — illiquid CoinDCX book = NO TRADE).
"""
from __future__ import annotations

import time

from ..core.types import VetoReport, VetoSeverity
from .base import Veto, VetoContext


class V3LiquidityVacuum(Veto):
    veto_id = "V3"
    description = "Liquidity vacuum"

    def evaluate(self, ctx: VetoContext) -> VetoReport:
        snap = ctx.snap
        if snap.coindcx_book is None or snap.coindcx_ticker is None:
            return VetoReport(
                veto_id=self.veto_id, pair=snap.pair.base,
                severity=VetoSeverity.HARD, triggered=True,
                detail="missing CoinDCX book or ticker — fail-closed",
                components={}, timestamp=time.time(),
            )
        coindcx_bid_d, coindcx_ask_d = snap.coindcx_book.depth_within_pct(0.05)
        coindcx_depth = coindcx_bid_d + coindcx_ask_d
        spread_bps = snap.coindcx_ticker.spread_bps
        median_spread = ctx.analyser_state.get("coindcx_median_spread_bps", 5.0)

        # Compare to external depth (primary venue).
        ext_depth = 0.0
        primary_venue = snap.pair.primary_discovery
        ext_book = snap.external_books.get(primary_venue)
        if ext_book is not None:
            eb, ea = ext_book.depth_within_pct(0.05)
            ext_depth = eb + ea

        # BTC pair penalty (10× larger depth threshold).
        depth_threshold_ratio = 0.10
        if snap.pair.base == "BTC":
            depth_threshold_ratio = 0.20

        if ext_depth > 0:
            depth_ratio = coindcx_depth / ext_depth
            depth_vacuum = depth_ratio < depth_threshold_ratio
        else:
            depth_ratio = 0.0
            depth_vacuum = coindcx_depth < 100_000  # absolute fallback

        spread_vacuum = spread_bps > 5.0 * max(median_spread, 1.0)
        triggered = depth_vacuum or spread_vacuum

        if triggered:
            severity = VetoSeverity.HARD
            detail = f"liquidity vacuum: depth_ratio={depth_ratio:.2f} spread={spread_bps:.1f}bp"
        else:
            severity = VetoSeverity.ADVISORY
            detail = "liquidity adequate"

        return VetoReport(
            veto_id=self.veto_id, pair=snap.pair.base,
            severity=severity, triggered=triggered, detail=detail,
            components={
                "coindcx_depth_5pct_usd": coindcx_depth,
                "ext_depth_5pct_usd": ext_depth,
                "depth_ratio": depth_ratio,
                "spread_bps": spread_bps,
                "median_spread_bps": median_spread,
                "spread_vacuum": float(spread_vacuum),
                "depth_vacuum": float(depth_vacuum),
            },
            timestamp=time.time(),
        )
