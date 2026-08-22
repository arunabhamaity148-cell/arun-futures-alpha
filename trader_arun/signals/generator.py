"""Signal generator — composes all engines into a final Signal.

Pipeline (research §14):
  ALPHA → MISMATCH → REGIME → FOOTPRINT → VETO → NEWS → PORTFOLIO
        → RISK → SIZING → SL/TP → SIGNAL

Any HARD veto or NO_TRADE decision → no signal emitted.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from ..alpha.engine import AlphaEngine
from ..core.config import Config
from ..core.logger import get_logger
from ..core.types import (
    InstitutionalFootprint,
    MismatchReport,
    PortfolioCrowding,
    Regime,
    RiskDecision,
    Signal,
    SignalGrade,
    Side,
    new_signal_id,
)
from ..data.leadlag import LeadLagEngine
from ..data.manager import PairSnapshot
from ..data.mismatch import MismatchEngine
from ..derivatives.basis import BasisAnalyser
from ..derivatives.funding import FundingAnalyser
from ..derivatives.liquidations import LiquidationAnalyser
from ..derivatives.open_interest import OpenInterestAnalyser
from ..institutional.footprint import InstitutionalFootprintEngine
from ..microstructure.absorption import AbsorptionDetector
from ..microstructure.cvd import CVDCalculator
from ..microstructure.obi import OBICalculator
from ..microstructure.price_impact import PriceImpactEstimator
from ..microstructure.trade_clusters import TradeClusterDetector
from ..newsguard.engine import NewsGuard
from ..portfolio.crowding import PortfolioCrowdingEngine
from ..regime.classifier import RegimeEngine
from ..risk.gate import RiskGate, RiskInputs
from ..risk.sizing import PositionSizer
from ..risk.sltp import SLTPBuilder
from ..vetoes.engine import VetoEngine
from ..vetoes.base import VetoContext

log = get_logger("signal_generator")


@dataclass
class GenerationResult:
    signal: Signal | None
    audit: dict[str, Any]


class SignalGenerator:
    """End-to-end signal generator for one pair."""

    def __init__(
        self,
        cfg: Config,
        news_guard: NewsGuard,
        portfolio_engine: PortfolioCrowdingEngine,
        coindcx_futures_verified: bool = False,
    ) -> None:
        self._cfg = cfg
        self._alpha = AlphaEngine()
        self._mismatch = MismatchEngine()
        self._regime = RegimeEngine()
        self._footprint = InstitutionalFootprintEngine()
        self._vetoes = VetoEngine()
        self._risk = RiskGate(cfg)
        self._sizer = PositionSizer(
            equity_usd=10_000.0,
            risk_pct=cfg.default_risk_pct,
            max_leverage=cfg.max_leverage,
        )
        self._sltp = SLTPBuilder()
        self._news_guard = news_guard
        self._portfolio = portfolio_engine
        self._coindcx_verified = coindcx_futures_verified
        self._leadlag = LeadLagEngine()
        # Per-pair analysers are created lazily.
        self._cvd_calcs: dict[str, CVDCalculator] = {}
        self._obi_calcs: dict[str, OBICalculator] = {}
        self._absorption_dets: dict[str, AbsorptionDetector] = {}
        self._cluster_dets: dict[str, TradeClusterDetector] = {}
        self._impact_ests: dict[str, PriceImpactEstimator] = {}
        self._funding_analysers: dict[str, FundingAnalyser] = {}
        self._oi_analysers: dict[str, OpenInterestAnalyser] = {}
        self._basis_analysers: dict[str, BasisAnalyser] = {}
        self._liq_analysers: dict[str, LiquidationAnalyser] = {}
        self._spread_history: dict[str, list[float]] = {}
        self._depth_history: dict[str, list[float]] = {}
        self._last_signal_ts: dict[str, float] = {}

    def generate(
        self,
        snap: PairSnapshot,
        trade_history: dict[str, list] | None = None,
    ) -> GenerationResult:
        audit: dict[str, Any] = {
            "pair": snap.pair.base,
            "timestamp": time.time(),
        }
        base = snap.pair.base

        # 1. CoinDCX futures symbol must be verified.
        if not self._coindcx_verified:
            audit["reject"] = "coindcx futures universe NOT VERIFIED — fail-closed"
            return GenerationResult(None, audit)

        # 2. Build analyser state.
        analyser_state = self._build_analyser_state(snap, trade_history or {})
        analyser_state["coindcx_futures_verified"] = self._coindcx_verified

        # 3. Compute mismatch.
        mismatch = self._mismatch.compute(snap, analyser_state)
        analyser_state["mismatch_score"] = mismatch.score
        audit["mismatch"] = {
            "score": mismatch.score, "band": mismatch.band,
            "components": mismatch.components,
        }
        if mismatch.band == "NO_TRADE":
            audit["reject"] = f"mismatch NO_TRADE ({mismatch.score:.1f})"
            return GenerationResult(None, audit)

        # 4. Regime.
        regime = self._regime.classify(snap, analyser_state)
        analyser_state["regime"] = regime.regime
        audit["regime"] = {
            "regime": regime.regime.value, "confidence": regime.confidence,
            "components": regime.components,
        }

        # 5. Alpha.
        alpha_result = self._alpha.evaluate(snap, analyser_state)
        if alpha_result.best_signal is None or not alpha_result.best_signal.is_actionable:
            audit["reject"] = "no actionable alpha"
            audit["alpha_signals"] = [
                {"strategy": s.strategy_id, "side": s.side.value,
                 "confidence": s.confidence, "primary": s.primary_alpha}
                for s in alpha_result.all_signals
            ]
            return GenerationResult(None, audit)
        best_alpha = alpha_result.best_signal
        audit["alpha"] = {
            "strategy": best_alpha.strategy_id,
            "side": best_alpha.side.value,
            "confidence": best_alpha.confidence,
            "edge_bps": best_alpha.edge_estimate_bps,
            "primary_alpha": best_alpha.primary_alpha,
        }

        # 6. NewsGuard.
        news_state = self._news_guard.state(base)
        analyser_state["news_state"] = news_state
        audit["news"] = {
            "action": news_state.action.value,
            "blocking": len(news_state.blocking_items),
            "reduce": len(news_state.reduce_items),
        }

        # 7. Institutional footprint.
        footprint = self._footprint.compute(snap, analyser_state)
        audit["footprint"] = {"score": footprint.score, "label": footprint.label}

        # 8. Veto.
        veto_ctx = VetoContext(
            snap=snap, analyser_state=analyser_state,
            cfg=self._cfg, signal_side=best_alpha.side,
        )
        veto_result = self._vetoes.evaluate(veto_ctx)
        audit["vetoes"] = {
            "hard_veto": veto_result.hard_veto,
            "hard_ids": veto_result.hard_veto_ids,
            "soft_count": veto_result.soft_veto_count,
            "detail": veto_result.detail,
        }
        if veto_result.hard_veto:
            audit["reject"] = f"hard veto: {veto_result.hard_veto_ids}"
            return GenerationResult(None, audit)

        # 9. SL/TP.
        candles = snap.coindcx_candles or snap.binance_candles
        if not candles or snap.coindcx_ticker is None:
            audit["reject"] = "missing candles or ticker for SL/TP"
            return GenerationResult(None, audit)
        sltp = self._sltp.build(
            candles, best_alpha.side, snap.coindcx_ticker.mid,
            snap.coindcx_ticker.spread_bps,
        )
        if not sltp.valid:
            audit["reject"] = f"SL/TP invalid: {sltp.reason}"
            return GenerationResult(None, audit)
        audit["sltp"] = {
            "entry_low": sltp.entry_zone_low, "entry_high": sltp.entry_zone_high,
            "sl": sltp.stop_loss, "tp1": sltp.tp1, "tp2": sltp.tp2, "tp3": sltp.tp3,
            "rr": sltp.rr, "atr": sltp.atr,
        }

        # 10. Portfolio crowding.
        portfolio = self._portfolio.compute()
        audit["portfolio"] = {
            "score": portfolio.score,
            "directional_exposure": portfolio.directional_exposure,
            "sector_corr": portfolio.sector_corr_avg,
        }

        # 11. Risk gate.
        book = snap.coindcx_book
        if book is not None:
            bid_d, ask_d = book.depth_within_pct(0.05)
            book_depth = bid_d + ask_d
        else:
            book_depth = 0.0

        # Slippage estimate.
        impact_est = self._impact_ests.setdefault(base, PriceImpactEstimator()).estimate(
            book, 5_000.0, best_alpha.side.value,
        )
        analyser_state["impact_estimate"] = impact_est

        risk_inputs = RiskInputs(
            pair=base,
            signal_confidence=best_alpha.confidence,
            edge_estimate_bps=best_alpha.edge_estimate_bps,
            volatility_z=regime.components.get("vol_ratio", 0.0) * 2.0,
            spread_bps=snap.coindcx_ticker.spread_bps,
            spread_z=analyser_state.get("spread_z", 0.0),
            slippage_estimate_bps=impact_est.expected_slippage_bps,
            book_depth_5pct_usd=book_depth,
            funding_z=analyser_state.get("funding_z", 0.0),
            cascade_index=analyser_state.get("cascade_index", 0.0),
            cross_exchange_deviation_bps=mismatch.components.get("price_dev", 0.0) * 0.6,
            mismatch_score=mismatch.score,
            news_action=news_state.action.value,
            data_fresh=True,
            stop_distance_atr=abs(snap.coindcx_ticker.mid - sltp.stop_loss) / max(sltp.atr, 1e-9),
            rr_ratio=sltp.rr,
            portfolio_correlation_avg=portfolio.sector_corr_avg,
            directional_exposure=portfolio.directional_exposure,
            coinbase_match_score=100.0 - mismatch.score,
            required_inputs_present=True,
        )
        risk = self._risk.assess(risk_inputs)
        audit["risk"] = {
            "score": risk.score, "decision": risk.decision.value,
            "size_mult": risk.size_multiplier, "reasons": risk.reasons,
            "components": risk.components,
        }
        if risk.decision == RiskDecision.NO_TRADE:
            audit["reject"] = f"risk NO_TRADE (score={risk.score:.1f})"
            return GenerationResult(None, audit)
        if risk.decision == RiskDecision.WATCH:
            audit["reject"] = f"risk WATCH (score={risk.score:.1f})"
            return GenerationResult(None, audit)

        # 12. Position sizing.
        correlated_exposure = sum(
            p.notional_usd for p in self._portfolio.positions
            if p.pair != base
        )
        sizing = self._sizer.size(
            entry_price=snap.coindcx_ticker.mid,
            stop_price=sltp.stop_loss,
            book_depth_5pct_usd=book_depth,
            size_multiplier=risk.size_multiplier,
            correlated_exposure_usd=correlated_exposure,
            max_correlated_usd=self._cfg.max_correlated_exposure * self._sizer.equity,
        )
        audit["sizing"] = {
            "size_usd": sizing.size_usd, "size_base": sizing.size_base,
            "leverage": sizing.leverage, "clipped": sizing.clipped,
            "reasons": sizing.reasons,
        }
        if sizing.size_usd <= 0:
            audit["reject"] = "size zero"
            return GenerationResult(None, audit)

        # 13. Cooldown check.
        last_ts = self._last_signal_ts.get(base, 0.0)
        if time.time() - last_ts < self._cfg.signal_min_cooldown_sec:
            remaining = self._cfg.signal_min_cooldown_sec - (time.time() - last_ts)
            audit["reject"] = f"cooldown {remaining:.0f}s remaining"
            return GenerationResult(None, audit)

        # 14. Build final signal.
        confidence = best_alpha.confidence
        # Adjust grade by risk and footprint.
        if risk.decision == RiskDecision.TRADE and risk.score < 30 and confidence >= 70:
            grade = SignalGrade.A
        elif risk.decision == RiskDecision.TRADE and confidence >= 55:
            grade = SignalGrade.B
        else:
            grade = SignalGrade.C

        # Leverage range.
        lev_min = 1.0
        lev_max = max(2.0, min(self._cfg.max_leverage, sizing.leverage * 1.5))

        # Validity window.
        valid_until = time.time() + self._cfg.entry_validity_window_sec

        # Invalidation condition.
        if best_alpha.side == Side.LONG:
            invalidation = (
                f"Price closes below {sltp.stop_loss:.4f} on 5m candle, OR "
                f"mismatch score exceeds {self._cfg.mismatch_no_trade}, OR "
                f"validity window expires."
            )
        else:
            invalidation = (
                f"Price closes above {sltp.stop_loss:.4f} on 5m candle, OR "
                f"mismatch score exceeds {self._cfg.mismatch_no_trade}, OR "
                f"validity window expires."
            )

        signal = Signal(
            signal_id=new_signal_id(),
            brand=self._cfg.brand,
            pair=f"{snap.pair.base}/{snap.pair.quote}",
            coindcx_futures_symbol=snap.pair.coindcx_futures_symbol,
            coindcx_spot_symbol=snap.pair.coindcx_spot_symbol,
            side=best_alpha.side,
            strategy=best_alpha.strategy_id,
            regime=regime.regime,
            entry_zone_low=sltp.entry_zone_low,
            entry_zone_high=sltp.entry_zone_high,
            stop_loss=sltp.stop_loss,
            tp1=sltp.tp1, tp2=sltp.tp2, tp3=sltp.tp3,
            rr=sltp.rr,
            leverage_min=lev_min,
            leverage_max=lev_max,
            risk_pct=self._cfg.default_risk_pct * risk.size_multiplier,
            confidence=confidence,
            grade=grade,
            primary_alpha=best_alpha.primary_alpha,
            institutional_footprint=footprint.score,
            coindcx_match=100.0 - mismatch.score,
            transfer_score=100.0 - mismatch.score,  # proxy until calibrated
            liquidity_state=("STRESSED" if book_depth < 250_000 else "ADEQUATE"),
            funding_context=self._format_funding_context(analyser_state),
            oi_context=self._format_oi_context(analyser_state),
            news_state=news_state.action.value,
            portfolio_crowding=portfolio.score,
            validity_window_sec=self._cfg.entry_validity_window_sec,
            valid_until=valid_until,
            invalidation_condition=invalidation,
            audit=audit,
        )
        self._last_signal_ts[base] = time.time()
        audit["signal_id"] = signal.signal_id
        return GenerationResult(signal, audit)

    def _build_analyser_state(
        self,
        snap: PairSnapshot,
        trade_history: dict[str, list],
    ) -> dict[str, Any]:
        base = snap.pair.base
        state: dict[str, Any] = {}

        # CVD.
        cvd_calc = self._cvd_calcs.setdefault(base, CVDCalculator(window_sec=300))
        for venue, trades in trade_history.items():
            for t in trades:
                cvd_calc.update(t)
        # Also feed coindcx recent trades.
        for t in snap.trades_by_venue.get("coindcx", []):
            cvd_calc.update(t)
        state["cvd_calculator"] = cvd_calc

        # OBI.
        obi_calc = self._obi_calcs.setdefault(base, OBICalculator(levels=10))
        if snap.coindcx_book is not None:
            obi_data = obi_calc.compute(snap.coindcx_book)
            state["obi_data"] = obi_data

        # Absorption.
        abs_det = self._absorption_dets.setdefault(
            base, AbsorptionDetector(cvd_calc, window_sec=300)
        )
        coindcx_trades = snap.trades_by_venue.get("coindcx", [])
        current_price = snap.coindcx_ticker.mid if snap.coindcx_ticker else 0.0
        abs_result = abs_det.update(coindcx_trades, snap.coindcx_book, current_price)
        state["absorption_result"] = abs_result

        # Cluster.
        cluster_det = self._cluster_dets.setdefault(base, TradeClusterDetector(window_sec=10))
        cluster_result = cluster_det.update(coindcx_trades)
        state["cluster_result"] = cluster_result

        # Spread history for z-score.
        if snap.coindcx_ticker is not None:
            spread_history = self._spread_history.setdefault(base, [])
            spread_history.append(snap.coindcx_ticker.spread_bps)
            if len(spread_history) > 120:
                spread_history[:] = spread_history[-120:]
            import numpy as np
            if len(spread_history) >= 30:
                median_spread = float(np.median(spread_history))
                std_spread = float(np.std(spread_history))
                spread_z = (
                    (snap.coindcx_ticker.spread_bps - median_spread) / std_spread
                    if std_spread > 0 else 0.0
                )
                state["coindcx_median_spread_bps"] = median_spread
                state["spread_z"] = spread_z

        # Depth history.
        if snap.coindcx_book is not None:
            bid_d, ask_d = snap.coindcx_book.depth_within_pct(0.05)
            depth_history = self._depth_history.setdefault(base, [])
            depth_history.append(bid_d + ask_d)
            if len(depth_history) > 60:
                depth_history[:] = depth_history[-60:]
            state["depth_history"] = depth_history

        # Funding.
        if snap.funding:
            primary_venue = snap.pair.primary_discovery
            funding = snap.funding.get(primary_venue) or next(iter(snap.funding.values()))
            if funding is not None:
                fa = self._funding_analysers.setdefault(
                    f"{base}:{funding.venue}",
                    FundingAnalyser(venue=funding.venue, symbol=funding.symbol),
                )
                funding_report = fa.update(funding)
                state["funding_report"] = funding_report
                state["funding_z"] = funding_report.z_score

        # OI.
        if snap.open_interest:
            primary_venue = snap.pair.primary_discovery
            oi = snap.open_interest.get(primary_venue) or next(iter(snap.open_interest.values()))
            if oi is not None:
                oa = self._oi_analysers.setdefault(
                    f"{base}:{oi.venue}",
                    OpenInterestAnalyser(venue=oi.venue, symbol=oi.symbol),
                )
                oi_report = oa.update(oi)
                state["oi_report"] = oi_report

        # Basis.
        if snap.external_tickers and snap.coindcx_ticker:
            primary_ticker = next(iter(snap.external_tickers.values()))
            if primary_ticker is not None:
                ba = self._basis_analysers.setdefault(base, BasisAnalyser())
                basis_report = ba.update(primary_ticker, snap.coindcx_ticker)
                state["basis_report"] = basis_report

        # Liquidations.
        liq_analyser = self._liq_analysers.setdefault(base, LiquidationAnalyser(base=base))
        cascade_report = liq_analyser.update(snap.liquidations)
        state["cascade_report"] = cascade_report
        state["cascade_index"] = cascade_report.cascade_index

        # Lead/lag.
        leadlag_report = self._leadlag.analyse(snap)
        state["leadlag_corr"] = leadlag_report.best_corr
        state["leadlag_report"] = leadlag_report

        return state

    def _format_funding_context(self, state: dict[str, Any]) -> str:
        fr = state.get("funding_report")
        if fr is None:
            return "funding NOT VERIFIED (CoinDCX public API)"
        return f"{fr.venue} {fr.rate_8h*1e4:.2f}bp/8h (z={fr.z_score:+.2f}, {fr.crowding_side})"

    def _format_oi_context(self, state: dict[str, Any]) -> str:
        oi = state.get("oi_report")
        if oi is None:
            return "OI NOT VERIFIED"
        return f"{oi.venue} ΔOI {oi.delta_pct*100:+.2f}% (z={oi.z_score:+.2f})"
