"""V4 — Liquidation exhaustion / incomplete cascade.

Trigger: cascade_index >= 3σ AND exhaustion_score < 40 (cascade still
accelerating, NOT exhausted). Entering during an incomplete cascade is
knife-catching — veto HARD.

If cascade_index < 1.5σ (no cascade) or exhaustion_score >= 50 (exhausted)
→ ALLOW (no veto).
"""
from __future__ import annotations

import time

from ..core.types import VetoReport, VetoSeverity
from .base import Veto, VetoContext


class V4LiquidationExhaustion(Veto):
    veto_id = "V4"
    description = "Liquidation exhaustion / incomplete cascade"

    def evaluate(self, ctx: VetoContext) -> VetoReport:
        snap = ctx.snap
        cascade_report = ctx.analyser_state.get("cascade_report")
        if cascade_report is None:
            return VetoReport(
                veto_id=self.veto_id, pair=snap.pair.base,
                severity=VetoSeverity.ADVISORY, triggered=False,
                detail="no cascade data — no liq signal possible",
                components={}, timestamp=time.time(),
            )
        cascade_index = cascade_report.cascade_index
        exhaustion = cascade_report.exhaustion_score
        continuation = cascade_report.continuation_score

        # Incomplete cascade: high cascade_index but not yet exhausting.
        if cascade_index >= 3.0 and exhaustion < 40.0:
            severity = VetoSeverity.HARD
            triggered = True
            detail = f"incomplete cascade: idx={cascade_index:.2f} exhaust={exhaustion:.1f}"
        elif cascade_index >= 1.5 and continuation > 60.0 and exhaustion < 30.0:
            severity = VetoSeverity.HARD
            triggered = True
            detail = f"cascade accelerating: cont={continuation:.1f}"
        elif cascade_index >= 1.5 and exhaustion < 40.0:
            severity = VetoSeverity.SOFT
            triggered = True
            detail = f"cascade not yet exhausted: exhaust={exhaustion:.1f}"
        else:
            severity = VetoSeverity.ADVISORY
            triggered = False
            detail = "no cascade veto"

        return VetoReport(
            veto_id=self.veto_id, pair=snap.pair.base,
            severity=severity, triggered=triggered, detail=detail,
            components={
                "cascade_index": cascade_index,
                "exhaustion_score": exhaustion,
                "continuation_score": continuation,
                "dominant_side": cascade_report.dominant_side.value,
            },
            timestamp=time.time(),
        )
