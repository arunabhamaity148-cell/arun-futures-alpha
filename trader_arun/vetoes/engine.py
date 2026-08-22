"""Veto engine — runs all 5 vetoes, returns aggregated report."""
from __future__ import annotations

import time
from dataclasses import dataclass, field

from ..core.logger import get_logger
from ..core.types import VetoReport, VetoSeverity
from .base import Veto, VetoContext
from .v1_cross_exch import V1CrossExchangeContradiction
from .v2_oi_funding import V2OIFundingContradiction
from .v3_liquidity_vacuum import V3LiquidityVacuum
from .v4_liq_exhaustion import V4LiquidationExhaustion
from .v5_macro_news import V5MacroNewsContradiction

log = get_logger("veto_engine")


@dataclass
class VetoEngineResult:
    pair: str
    reports: list[VetoReport] = field(default_factory=list)
    hard_veto: bool = False
    soft_veto_count: int = 0
    hard_veto_ids: list[str] = field(default_factory=list)
    detail: str = ""


class VetoEngine:
    """Runs all vetoes. Hard veto = NO TRADE."""

    def __init__(self) -> None:
        self._vetoes: list[Veto] = [
            V1CrossExchangeContradiction(),
            V2OIFundingContradiction(),
            V3LiquidityVacuum(),
            V4LiquidationExhaustion(),
            V5MacroNewsContradiction(),
        ]

    @property
    def vetoes(self) -> list[Veto]:
        return list(self._vetoes)

    def evaluate(self, ctx: VetoContext) -> VetoEngineResult:
        reports: list[VetoReport] = []
        hard_ids: list[str] = []
        soft_count = 0
        for v in self._vetoes:
            try:
                report = v.evaluate(ctx)
                reports.append(report)
                if report.triggered and report.severity == VetoSeverity.HARD:
                    hard_ids.append(v.veto_id)
                elif report.triggered and report.severity == VetoSeverity.SOFT:
                    soft_count += 1
            except Exception as exc:  # pragma: no cover - defensive
                log.x_warn("veto error", extras={
                    "veto": v.veto_id, "pair": ctx.snap.pair.base, "err": str(exc),
                })
                # Fail-closed: treat as HARD veto.
                reports.append(VetoReport(
                    veto_id=v.veto_id, pair=ctx.snap.pair.base,
                    severity=VetoSeverity.HARD, triggered=True,
                    detail=f"veto error: {exc}",
                    components={"error": str(exc)},
                    timestamp=time.time(),
                ))
                hard_ids.append(v.veto_id)

        hard_veto = bool(hard_ids)
        detail = (
            f"HARD vetoes: {','.join(hard_ids)}" if hard_ids
            else f"{soft_count} soft veto(s)" if soft_count
            else "no vetoes"
        )
        return VetoEngineResult(
            pair=ctx.snap.pair.base,
            reports=reports,
            hard_veto=hard_veto,
            soft_veto_count=soft_count,
            hard_veto_ids=hard_ids,
            detail=detail,
        )
