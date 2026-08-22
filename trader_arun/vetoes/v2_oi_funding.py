"""V2 — OI/Funding contradiction.

Trigger: funding and OI are sending opposing signals about crowding direction.
e.g. funding strongly positive (long crowding) but OI falling (longs exiting)
→ contradiction. The mismatch suggests an unwind is in progress but not yet
clear; signal should be blocked until alignment returns.

Logic:
- If |funding_z| >= 1.5 AND sign(funding) ≠ sign(oi_delta) AND |oi_delta_pct| > 0.5%
  AND this state persists for 6h+ → HARD veto.
- Otherwise ADVISORY.

Persistence: requires analyser_state['oi_funding_contradiction_persistence_sec']
which the engine tracks over time.
"""
from __future__ import annotations

import time
from typing import Any

from ..core.types import VetoReport, VetoSeverity
from .base import Veto, VetoContext


class V2OIFundingContradiction(Veto):
    veto_id = "V2"
    description = "OI/Funding contradiction"

    def evaluate(self, ctx: VetoContext) -> VetoReport:
        snap = ctx.snap
        funding_report = ctx.analyser_state.get("funding_report")
        oi_report = ctx.analyser_state.get("oi_report")

        if funding_report is None or oi_report is None:
            return VetoReport(
                veto_id=self.veto_id, pair=snap.pair.base,
                severity=VetoSeverity.HARD, triggered=True,
                detail="missing funding or OI — fail-closed",
                components={}, timestamp=time.time(),
            )

        funding_z = funding_report.z_score
        oi_delta_pct = oi_report.delta_pct
        contradiction = (
            abs(funding_z) >= 1.5
            and abs(oi_delta_pct) >= 0.005
            and (
                (funding_z > 0 and oi_delta_pct < 0)
                or (funding_z < 0 and oi_delta_pct > 0)
            )
        )
        persistence_sec = ctx.analyser_state.get("oi_funding_contradiction_persistence_sec", 0.0)
        if contradiction and persistence_sec >= 6 * 3600:
            severity = VetoSeverity.HARD
            triggered = True
            detail = f"persistent OI/funding contradiction for {persistence_sec/3600:.1f}h"
        elif contradiction:
            severity = VetoSeverity.SOFT
            triggered = True
            detail = f"OI/funding contradiction {persistence_sec/3600:.1f}h < 6h"
        else:
            severity = VetoSeverity.ADVISORY
            triggered = False
            detail = "funding/OI aligned"

        return VetoReport(
            veto_id=self.veto_id, pair=snap.pair.base,
            severity=severity, triggered=triggered, detail=detail,
            components={
                "funding_z": funding_z,
                "oi_delta_pct": oi_delta_pct,
                "persistence_sec": persistence_sec,
                "contradiction": float(contradiction),
            },
            timestamp=time.time(),
        )
