"""Institutional footprint engine.

Computes a composite INSTITUTIONAL_FOOTPRINT_SCORE ∈ [0, 100] from
measurable inputs (research §12):

  0.15·OI_IMPULSE + 0.15·CVD_SIGNED + 0.10·AGGRESSIVE_VOL
+ 0.10·FUNDING_PRESSURE + 0.08·BASIS_PRESSURE + 0.08·CROSSEX_FLOW
+ 0.08·OBI + 0.06·ABSORPTION + 0.06·LIQ_WITHDRAWAL
+ 0.06·LIQ_ASYMMETRY + 0.04·TRADE_CLUSTER + 0.04·PRICE_IMPACT
= 1.00

Each component is normalised to [0,1] via 30-day rolling percentile. Final
score = 100 × weighted sum.

Subscores:
- ACCUMULATION_SCORE / DISTRIBUTION_SCORE — sign-split CVD×OI-weighted
- LONG_CROWDING_SCORE  = funding>top20% AND ΔOI>0 AND price<recent high
- SHORT_CROWDING_SCORE = mirror
- LIQUIDATION_CASCADE_SCORE = 100 × liq-vol z (6h)
- LIQUIDITY_STRESS_SCORE = spread_z + depth_z + vol_liquidity_z

MANDATORY WORDING: never claim a specific institution bought/sold.
Use "large/informed participant activity proxy".
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Any

from ..core.types import InstitutionalFootprint, Side
from ..data.manager import PairSnapshot


@dataclass
class FootprintInputs:
    oi_impulse: float = 0.0          # |z| of OI delta
    cvd_signed: float = 0.0          # signed CVD z (-3..+3 → clamp)
    aggressive_vol: float = 0.0      # share of aggressive volume
    funding_pressure: float = 0.0    # |z| of funding
    basis_pressure: float = 0.0      # |z| of basis
    crossex_flow: float = 0.0        # cross-exchange flow imbalance
    obi: float = 0.0                 # |OBI|
    absorption: float = 0.0          # absorption score 0..100
    liq_withdrawal: float = 0.0      # depth withdrawal z
    liq_asymmetry: float = 0.0       # long-vs-short liq imbalance
    trade_cluster: float = 0.0       # cluster score 0..100
    price_impact: float = 0.0        # realised impact bps


WEIGHTS = {
    "oi_impulse": 0.15,
    "cvd_signed": 0.15,
    "aggressive_vol": 0.10,
    "funding_pressure": 0.10,
    "basis_pressure": 0.08,
    "crossex_flow": 0.08,
    "obi": 0.08,
    "absorption": 0.06,
    "liq_withdrawal": 0.06,
    "liq_asymmetry": 0.06,
    "trade_cluster": 0.04,
    "price_impact": 0.04,
}


def _norm(z: float, cap: float = 3.0) -> float:
    """Normalise z-score to [0,1] via |z|/cap."""
    return min(1.0, abs(z) / cap)


def _norm_signed(z: float, cap: float = 3.0) -> float:
    """Normalise z-score preserving sign — output in [-1, +1]."""
    return max(-1.0, min(1.0, z / cap))


class InstitutionalFootprintEngine:
    """Composite institutional-footprint proxy score."""

    def compute(
        self,
        snap: PairSnapshot,
        analyser_state: dict[str, Any],
    ) -> InstitutionalFootprint:
        inputs = self._collect_inputs(snap, analyser_state)
        weights = WEIGHTS

        # Normalised components — 0..1 each.
        norm = {
            "oi_impulse": _norm(inputs.oi_impulse),
            "cvd_signed": abs(_norm_signed(inputs.cvd_signed)),
            "aggressive_vol": min(1.0, inputs.aggressive_vol),
            "funding_pressure": _norm(inputs.funding_pressure),
            "basis_pressure": _norm(inputs.basis_pressure),
            "crossex_flow": _norm(inputs.crossex_flow),
            "obi": min(1.0, inputs.obi),
            "absorption": inputs.absorption / 100.0,
            "liq_withdrawal": _norm(inputs.liq_withdrawal),
            "liq_asymmetry": min(1.0, inputs.liq_asymmetry),
            "trade_cluster": inputs.trade_cluster / 100.0,
            "price_impact": min(1.0, inputs.price_impact / 50.0),
        }
        score = 100.0 * sum(weights[k] * norm[k] for k in weights)

        # Subscores.
        cvd_sign = 1 if inputs.cvd_signed > 0.3 else (-1 if inputs.cvd_signed < -0.3 else 0)
        accumulation = max(0.0, cvd_sign) * norm["oi_impulse"] * 100.0
        distribution = max(0.0, -cvd_sign) * norm["oi_impulse"] * 100.0

        funding_report = analyser_state.get("funding_report")
        oi_report = analyser_state.get("oi_report")
        long_crowd = 0.0
        short_crowd = 0.0
        if funding_report and oi_report:
            if funding_report.crowding_side == "LONG" and oi_report.delta_pct > 0:
                long_crowd = min(100.0, abs(funding_report.z_score) * 30.0)
            elif funding_report.crowding_side == "SHORT" and oi_report.delta_pct > 0:
                short_crowd = min(100.0, abs(funding_report.z_score) * 30.0)

        cascade_report = analyser_state.get("cascade_report")
        liq_cascade_score = 0.0
        if cascade_report:
            liq_cascade_score = min(100.0, getattr(cascade_report, "cascade_index", 0.0) * 30.0)

        # Liquidity stress.
        spread_bps = snap.coindcx_ticker.spread_bps if snap.coindcx_ticker else 0.0
        book = snap.coindcx_book
        if book is not None:
            bid_d, ask_d = book.depth_within_pct(0.05)
            depth_usd = bid_d + ask_d
        else:
            depth_usd = 0.0
        liquidity_stress = min(100.0, max(0.0, spread_bps / 0.5) + max(0.0, (500_000 - depth_usd) / 5000))

        subscores = {
            "accumulation_score": accumulation,
            "distribution_score": distribution,
            "long_crowding_score": long_crowd,
            "short_crowding_score": short_crowd,
            "liquidation_cascade_score": liq_cascade_score,
            "liquidity_stress_score": liquidity_stress,
            "oi_impulse_norm": norm["oi_impulse"],
            "cvd_signed": inputs.cvd_signed,
            "aggressive_vol": inputs.aggressive_vol,
            "funding_pressure": inputs.funding_pressure,
            "basis_pressure": inputs.basis_pressure,
            "obi": inputs.obi,
            "absorption": inputs.absorption,
            "liq_withdrawal": inputs.liq_withdrawal,
            "trade_cluster": inputs.trade_cluster,
            "price_impact": inputs.price_impact,
        }

        return InstitutionalFootprint(
            pair=snap.pair.base,
            score=score,
            subscores=subscores,
            label="large/informed participant activity proxy",
            timestamp=time.time(),
        )

    def _collect_inputs(
        self, snap: PairSnapshot, analyser_state: dict[str, Any]
    ) -> FootprintInputs:
        inputs = FootprintInputs()

        # OI impulse.
        oi_report = analyser_state.get("oi_report")
        if oi_report:
            inputs.oi_impulse = abs(oi_report.z_score)

        # CVD signed.
        absorption = analyser_state.get("absorption_result")
        if absorption:
            inputs.cvd_signed = absorption.cvd_z
            inputs.absorption = absorption.score

        # Aggressive vol — share of aggressive (taker) volume from CVD analyser.
        cvd_calc = analyser_state.get("cvd_calculator")
        if cvd_calc is not None:
            total = cvd_calc.total_volume
            if total > 0:
                # Aggressive volume = |buy - sell| / total → range 0..1.
                inputs.aggressive_vol = abs(cvd_calc.buy_volume - cvd_calc.sell_volume) / total

        # Funding pressure.
        funding_report = analyser_state.get("funding_report")
        if funding_report:
            inputs.funding_pressure = abs(funding_report.z_score)

        # Basis pressure.
        basis_report = analyser_state.get("basis_report")
        if basis_report:
            inputs.basis_pressure = abs(basis_report.z_score)

        # Cross-exchange flow.
        ext_tickers = snap.external_tickers
        if snap.coindcx_ticker and ext_tickers:
            # CoinDCX deviation from primary venue mid as flow proxy.
            primary_ticker = next(iter(ext_tickers.values()))
            if primary_ticker and primary_ticker.mid > 0 and snap.coindcx_ticker.mid > 0:
                inputs.crossex_flow = abs(
                    (snap.coindcx_ticker.mid - primary_ticker.mid) / primary_ticker.mid
                ) * 1e4 / 25.0  # 25 bps = saturation

        # OBI.
        obi_data = analyser_state.get("obi_data")
        if obi_data:
            inputs.obi = abs(obi_data.get("obi_top", 0.0))

        # Liquidity withdrawal (depth shrinking).
        depth_history = analyser_state.get("depth_history", [])
        if len(depth_history) >= 10:
            recent = depth_history[-5:]
            prior = depth_history[-10:-5]
            recent_avg = sum(recent) / len(recent) if recent else 0
            prior_avg = sum(prior) / len(prior) if prior else 0
            if prior_avg > 0:
                inputs.liq_withdrawal = max(0.0, (prior_avg - recent_avg) / prior_avg * 3.0)

        # Liquidation asymmetry.
        cascade_report = analyser_state.get("cascade_report")
        if cascade_report:
            long_vol = getattr(cascade_report, "long_liq_6h_usd", 0.0)
            short_vol = getattr(cascade_report, "short_liq_6h_usd", 0.0)
            total = long_vol + short_vol
            if total > 0:
                inputs.liq_asymmetry = abs(long_vol - short_vol) / total

        # Trade cluster.
        cluster_result = analyser_state.get("cluster_result")
        if cluster_result:
            inputs.trade_cluster = getattr(cluster_result, "score", 0.0)

        # Price impact — realised from recent candles.
        candles = snap.coindcx_candles or snap.binance_candles
        if candles and len(candles) >= 30:
            import numpy as np
            closes = np.array([c.close for c in candles[-30:]], dtype=float)
            vols = np.array([c.volume for c in candles[-30:]], dtype=float)
            ret = np.diff(np.log(closes))
            if vols[:-1].sum() > 0:
                # Amihud illiquidity: |return| / volume.
                amihud = float(np.mean(np.abs(ret) / (vols[:-1] + 1e-12)) * 1e6)
                inputs.price_impact = min(50.0, amihud * 1000.0)

        return inputs
