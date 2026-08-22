"""Risk gate — RISK_SCORE = 0–100 (higher = riskier).

Inputs:
- volatility_z, spread_z, slippage_est
- liquidity, OI, funding, liquidation risk
- cross-exchange agreement, CoinDCX mismatch
- news severity, macro score
- signal confidence, data freshness
- stop distance / ATR, R:R
- portfolio correlation

Outputs:
- TRADE       (0–39)
- REDUCED_RISK(40–59, size ×0.5)
- WATCH       (60–74, hold-no-new)
- NO_TRADE    (≥75)

Fail-closed: any required input unknown/stale → NO_TRADE.
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Any

from ..core.types import RiskAssessment, RiskDecision
from ..data.manager import PairSnapshot


@dataclass
class RiskInputs:
    pair: str
    signal_confidence: float = 0.0
    edge_estimate_bps: float = 0.0
    volatility_z: float = 0.0
    spread_bps: float = 0.0
    spread_z: float = 0.0
    slippage_estimate_bps: float = 0.0
    book_depth_5pct_usd: float = 0.0
    funding_z: float = 0.0
    cascade_index: float = 0.0
    cross_exchange_deviation_bps: float = 0.0
    mismatch_score: float = 0.0
    news_action: str = "ALLOW"
    data_fresh: bool = True
    stop_distance_atr: float = 0.0
    rr_ratio: float = 0.0
    portfolio_correlation_avg: float = 0.0
    directional_exposure: float = 0.0
    coinbase_match_score: float = 0.0
    required_inputs_present: bool = True
    missing_inputs: list[str] = field(default_factory=list)


class RiskGate:
    """Compute RISK_SCORE and decision."""

    def __init__(self, cfg: Any = None) -> None:
        self._cfg = cfg
        self._no_trade = float(getattr(cfg, "risk_score_no_trade", 75.0)) if cfg else 75.0
        self._watch = float(getattr(cfg, "risk_score_watch", 60.0)) if cfg else 60.0
        self._reduced = float(getattr(cfg, "risk_score_reduced", 40.0)) if cfg else 40.0

    def assess(self, inputs: RiskInputs) -> RiskAssessment:
        # Fail-closed.
        if not inputs.required_inputs_present or not inputs.data_fresh:
            return RiskAssessment(
                pair=inputs.pair, score=100.0,
                components={"fail_closed": 1.0, "missing": ",".join(inputs.missing_inputs)},
                decision=RiskDecision.NO_TRADE, size_multiplier=0.0,
                reasons=["fail-closed: missing required inputs or stale data"],
                timestamp=time.time(),
            )

        # News BLOCK is a hard override → NO_TRADE.
        if inputs.news_action == "BLOCK":
            return RiskAssessment(
                pair=inputs.pair, score=100.0,
                components={"news_block": 1.0},
                decision=RiskDecision.NO_TRADE, size_multiplier=0.0,
                reasons=["news BLOCK — fail-closed"],
                timestamp=time.time(),
            )

        components: dict[str, float] = {}
        reasons: list[str] = []

        # 1. Volatility z-score — |z|>3 = +20 risk points.
        vol_risk = min(20.0, max(0.0, abs(inputs.volatility_z) - 1.0) * 8.0)
        components["vol_risk"] = vol_risk

        # 2. Spread z-score — |z|>2 = +15 risk points.
        spread_risk = min(15.0, max(0.0, abs(inputs.spread_z) - 1.0) * 7.5)
        components["spread_risk"] = spread_risk
        if spread_risk > 0:
            reasons.append(f"spread elevated (z={inputs.spread_z:.2f})")

        # 3. Slippage vs edge ratio — if slippage > 0.5×edge, +20 points.
        if inputs.edge_estimate_bps > 0:
            slippage_ratio = inputs.slippage_estimate_bps / inputs.edge_estimate_bps
        else:
            slippage_ratio = 1.0
        slippage_risk = min(20.0, max(0.0, slippage_ratio - 0.25) * 30.0)
        components["slippage_risk"] = slippage_risk
        if slippage_ratio > 0.5:
            reasons.append(f"slippage {slippage_ratio*100:.0f}% of edge")

        # 4. Liquidity risk — book depth < 250k USD = +15 points.
        if inputs.book_depth_5pct_usd < 250_000:
            liq_risk = min(15.0, (250_000 - inputs.book_depth_5pct_usd) / 250_000 * 15.0)
        else:
            liq_risk = 0.0
        components["liquidity_risk"] = liq_risk
        if liq_risk > 0:
            reasons.append(f"thin book (${inputs.book_depth_5pct_usd:,.0f})")

        # 5. Funding risk — |z|>2 = +10 points.
        funding_risk = min(10.0, max(0.0, abs(inputs.funding_z) - 1.5) * 6.0)
        components["funding_risk"] = funding_risk

        # 6. Liquidation risk — cascade_index>2 = +10 points.
        liq_risk = min(10.0, max(0.0, inputs.cascade_index - 1.0) * 5.0)
        components["liquidation_risk"] = liq_risk
        if liq_risk > 0:
            reasons.append(f"cascade active (idx={inputs.cascade_index:.2f})")

        # 7. Cross-exchange deviation — >30bp = +15 points.
        crossex_risk = min(15.0, max(0.0, inputs.cross_exchange_deviation_bps - 15.0) * 0.5)
        components["cross_exchange_risk"] = crossex_risk
        if crossex_risk > 0:
            reasons.append(f"cross-exch dev {inputs.cross_exchange_deviation_bps:.1f}bp")

        # 8. Mismatch risk — linear scale 0–60 → 0–15 points.
        mismatch_risk = min(15.0, inputs.mismatch_score / 60.0 * 15.0)
        components["mismatch_risk"] = mismatch_risk

        # 9. News risk.
        if inputs.news_action == "BLOCK":
            news_risk = 20.0
            reasons.append("news BLOCK")
        elif inputs.news_action == "REDUCE":
            news_risk = 10.0
            reasons.append("news REDUCE")
        else:
            news_risk = 0.0
        components["news_risk"] = news_risk

        # 10. Confidence discount — low confidence raises risk.
        # If confidence < 50, add up to 10 points.
        confidence_risk = max(0.0, (50.0 - inputs.signal_confidence) / 5.0)
        components["confidence_risk"] = confidence_risk

        # 11. R:R risk — if R:R < 1.5, add up to 10 points.
        rr_risk = max(0.0, (1.5 - inputs.rr_ratio) * 10.0) if inputs.rr_ratio > 0 else 10.0
        components["rr_risk"] = rr_risk

        # 12. Portfolio correlation risk.
        portfolio_risk = min(10.0, inputs.portfolio_correlation_avg * 10.0)
        components["portfolio_risk"] = portfolio_risk

        # 13. Directional exposure risk.
        exposure_risk = min(15.0, abs(inputs.directional_exposure) * 5.0)
        components["exposure_risk"] = exposure_risk

        total = sum(components.values())
        total = min(100.0, total)

        if total >= self._no_trade:
            decision = RiskDecision.NO_TRADE
            size_mult = 0.0
        elif total >= self._watch:
            decision = RiskDecision.WATCH
            size_mult = 0.0
        elif total >= self._reduced:
            decision = RiskDecision.REDUCED_RISK
            size_mult = 0.5
        else:
            decision = RiskDecision.TRADE
            size_mult = 1.0

        return RiskAssessment(
            pair=inputs.pair, score=total,
            components=components, decision=decision,
            size_multiplier=size_mult,
            reasons=reasons, timestamp=time.time(),
        )
