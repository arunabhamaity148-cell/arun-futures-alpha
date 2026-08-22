"""V5 — Macro/News contradiction.

Trigger: NewsGuard action == BLOCK (CRITICAL macro event within ±2h window)
OR signal direction contradicts a HIGH-severity news item.

Severity: HARD when BLOCK or when direction contradicts HIGH news.
         SOFT when REDUCE.
"""
from __future__ import annotations

import time

from ..core.types import Side, VetoReport, VetoSeverity
from .base import Veto, VetoContext


class V5MacroNewsContradiction(Veto):
    veto_id = "V5"
    description = "Macro/News contradiction"

    def evaluate(self, ctx: VetoContext) -> VetoReport:
        snap = ctx.snap
        news_state = ctx.analyser_state.get("news_state")
        if news_state is None:
            return VetoReport(
                veto_id=self.veto_id, pair=snap.pair.base,
                severity=VetoSeverity.HARD, triggered=True,
                detail="missing news state — fail-closed",
                components={}, timestamp=time.time(),
            )

        action = str(getattr(news_state, "action", "ALLOW")).upper()
        blocking_items = list(getattr(news_state, "blocking_items", []))
        reduce_items = list(getattr(news_state, "reduce_items", []))

        if action == "BLOCK" or blocking_items:
            severity = VetoSeverity.HARD
            triggered = True
            detail = f"news BLOCK: {len(blocking_items)} critical item(s)"
        elif action == "REDUCE" or reduce_items:
            severity = VetoSeverity.SOFT
            triggered = True
            detail = f"news REDUCE: {len(reduce_items)} high item(s)"
        else:
            severity = VetoSeverity.ADVISORY
            triggered = False
            detail = "news ALLOW"

        return VetoReport(
            veto_id=self.veto_id, pair=snap.pair.base,
            severity=severity, triggered=triggered, detail=detail,
            components={
                "action": action,
                "blocking_count": len(blocking_items),
                "reduce_count": len(reduce_items),
                "signal_side": ctx.signal_side.value,
            },
            timestamp=time.time(),
        )
