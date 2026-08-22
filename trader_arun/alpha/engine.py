"""Alpha engine — orchestrates all strategies and picks the best signal per pair."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..core.logger import get_logger
from ..core.types import Side
from ..data.manager import PairSnapshot
from .base import AlphaSignal
from .s1_cascade import S1CascadeExhaustion
from .s2_leadlag import S2LeadLag
from .s3_funding_oi import S3FundingOIUnwind
from .s4_absorption import S4AbsorptionCVD
from .s5_basis import S5BasisConvergence

log = get_logger("alpha_engine")


@dataclass
class EngineResult:
    pair: str
    best_signal: AlphaSignal | None
    all_signals: list[AlphaSignal]


class AlphaEngine:
    """Run all strategies, return the strongest actionable signal."""

    def __init__(self) -> None:
        self._strategies = [
            S1CascadeExhaustion(),
            S2LeadLag(),
            S3FundingOIUnwind(),
            S4AbsorptionCVD(),
            S5BasisConvergence(),
        ]

    @property
    def strategies(self) -> list:
        return list(self._strategies)

    def evaluate(
        self,
        snap: PairSnapshot,
        analyser_state: dict[str, Any],
    ) -> EngineResult:
        all_signals: list[AlphaSignal] = []
        for strat in self._strategies:
            try:
                sig = strat.evaluate(snap, analyser_state)
                all_signals.append(sig)
            except Exception as exc:  # pragma: no cover - defensive
                log.x_warn("strategy error", extras={
                    "strategy": strat.strategy_id, "pair": snap.pair.base, "err": str(exc),
                })
                all_signals.append(AlphaSignal(
                    strategy_id=strat.strategy_id,
                    pair=snap.pair.base,
                    side=Side.FLAT,
                    confidence=0.0,
                    edge_estimate_bps=0.0,
                    primary_alpha=f"strategy error: {exc}",
                ))

        actionable = [s for s in all_signals if s.is_actionable]
        if not actionable:
            return EngineResult(pair=snap.pair.base, best_signal=None, all_signals=all_signals)

        # Pick highest confidence; tie-break by edge.
        best = max(actionable, key=lambda s: (s.confidence, s.edge_estimate_bps))
        return EngineResult(pair=snap.pair.base, best_signal=best, all_signals=all_signals)
