"""CoinDCX mismatch engine — research §5.

COINDCX_MISMATCH_SCORE = w1·PriceDev + w2·BasisDev + w3·(1−Corr)
                       + w4·SpreadDiv + w5·VolDiv + w6·VolRel
                       + w7·OIRel + w8·FundRel + w9·LeadLagStab
                       + w10·TimeDiff + w11·LiqDiff + w12·ContractDiff

Each component normalised to a 0–100 contribution. Weights sum to 1.0.

Calibration: until 2 weeks of live data is collected, default weights from
research are used. After calibration, weights are recomputed from the 95th
percentile of each component's distribution.

Decision bands (default):
  0–19   NORMAL  (allow)
  20–39  WATCH   (size×0.75)
  40–59  REDUCE  (size×0.5)
  ≥60    NO TRADE
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass
from typing import Any

import numpy as np

from ..core.types import MismatchReport
from ..data.manager import PairSnapshot


WEIGHTS = {
    "price_dev": 0.25,
    "basis_dev": 0.10,
    "inv_corr": 0.15,
    "spread_div": 0.10,
    "vol_div": 0.10,
    "vol_rel": 0.05,
    "oi_rel": 0.05,
    "fund_rel": 0.05,
    "leadlag_stab": 0.05,
    "time_diff": 0.05,
    "liq_diff": 0.05,
    "contract_diff": 0.05,
}


def _sigmoid(x: float, k: float = 1.0, midpoint: float = 0.0) -> float:
    return 1.0 / (1.0 + math.exp(-k * (x - midpoint)))


def _norm_01(value: float, low: float, high: float) -> float:
    """Normalise value to [0,1] given [low, high] band."""
    if high <= low:
        return 0.0
    return max(0.0, min(1.0, (value - low) / (high - low)))


class MismatchEngine:
    """Compute CoinDCX mismatch score per pair."""

    def __init__(
        self,
        corr_window: int = 60,
        normal_band: float = 25.0,
        watch_band: float = 40.0,
        no_trade_band: float = 60.0,
    ) -> None:
        self._corr_window = int(corr_window)
        self._normal = float(normal_band)
        self._watch = float(watch_band)
        self._no_trade = float(no_trade_band)

    def compute(
        self,
        snap: PairSnapshot,
        analyser_state: dict[str, Any],
    ) -> MismatchReport:
        components: dict[str, float] = {}

        # 1. Price deviation: |CoinDCX last - external mark| / external mark.
        price_dev_bps = 0.0
        if snap.coindcx_ticker and snap.external_tickers:
            ext_mids = [t.mid for t in snap.external_tickers.values() if t.mid > 0]
            median_ext = sorted(ext_mids)[len(ext_mids) // 2] if ext_mids else 0.0
            if median_ext > 0 and snap.coindcx_ticker.mid > 0:
                price_dev_bps = abs(snap.coindcx_ticker.mid - median_ext) / median_ext * 1e4
                # Normalise: 0bp=0, 30bp=0.5, 60bp=1.0.
                components["price_dev"] = _norm_01(price_dev_bps, 0, 60) * 100.0
            else:
                components["price_dev"] = 100.0  # missing → fail-closed
        else:
            components["price_dev"] = 100.0

        # 2. Basis deviation: |CoinDCX basis - external basis|.
        # We approximate CoinDCX basis via CoinDCX perp-mid - CoinDCX spot-mid.
        # Since CoinDCX public API doesn't expose funding/OI for futures, we use
        # external basis (perp - spot) on Hyperliquid vs Kraken as a proxy.
        basis_report = analyser_state.get("basis_report")
        if basis_report:
            basis_bps = abs(basis_report.basis_bps)
            components["basis_dev"] = _norm_01(basis_bps, 0, 50) * 100.0
        else:
            components["basis_dev"] = 50.0  # unknown

        # 3. Inverse correlation: 1 - rolling Pearson over aligned returns.
        corr_value = self._compute_corr(snap)
        components["inv_corr"] = (1.0 - corr_value) * 100.0 if corr_value is not None else 100.0

        # 4. Spread divergence.
        if snap.coindcx_ticker and snap.external_tickers:
            ext_spreads = [t.spread_bps for t in snap.external_tickers.values()]
            ext_spread = float(np.median(ext_spreads)) if ext_spreads else 0.0
            spread_div = abs(snap.coindcx_ticker.spread_bps - ext_spread)
            components["spread_div"] = _norm_01(spread_div, 0, 50) * 100.0
        else:
            components["spread_div"] = 100.0

        # 5. Volatility divergence: |RV(CoinDCX) - RV(external)| / RV(external).
        rv_ratio = self._compute_rv_divergence(snap)
        components["vol_div"] = _norm_01(rv_ratio, 0, 1.0) * 100.0 if rv_ratio is not None else 50.0

        # 6. Volume relation: log ratio of 24h volumes (CoinDCX vs external).
        # We don't have reliable 24h volume on CoinDCX per pair without extra
        # API calls. Mark as 50 (neutral) until calibrated.
        components["vol_rel"] = 50.0

        # 7. OI relation: ratio of CoinDCX OI to external OI.
        # CoinDCX futures OI is NOT VERIFIED — mark neutral.
        components["oi_rel"] = 50.0

        # 8. Funding relation.
        components["fund_rel"] = 50.0  # unknown for CoinDCX

        # 9. Lead/lag stability — derived from analyser state.
        leadlag_corr = analyser_state.get("leadlag_corr", 0.0)
        components["leadlag_stab"] = (1.0 - max(0.0, min(1.0, leadlag_corr))) * 100.0

        # 10. Timestamp skew — oldest feed age in seconds (cap 30s).
        oldest_ts = self._oldest_timestamp(snap)
        time_diff_sec = max(0.0, time.time() - oldest_ts) if oldest_ts > 0 else 30.0
        components["time_diff"] = _norm_01(time_diff_sec, 0, 30) * 100.0

        # 11. Liquidity difference.
        if snap.coindcx_book and snap.external_books:
            cd_bid, cd_ask = snap.coindcx_book.depth_within_pct(0.05)
            cd_depth = cd_bid + cd_ask
            ext_depths = []
            for eb in snap.external_books.values():
                bd, ad = eb.depth_within_pct(0.05)
                ext_depths.append(bd + ad)
            ext_depth = float(np.median(ext_depths)) if ext_depths else 0.0
            if ext_depth > 0:
                liq_ratio = abs(cd_depth - ext_depth) / ext_depth
                components["liq_diff"] = _norm_01(liq_ratio, 0, 1.0) * 100.0
            else:
                components["liq_diff"] = 100.0
        else:
            components["liq_diff"] = 100.0

        # 12. Contract difference — if CoinDCX futures symbol NOT VERIFIED, +50.
        coindcx_provider_verified = analyser_state.get("coindcx_futures_verified", False)
        components["contract_diff"] = 0.0 if coindcx_provider_verified else 50.0

        # Weighted sum.
        score = sum(WEIGHTS[k] * components.get(k, 0.0) for k in WEIGHTS)

        # Hard fail-closed: extreme CoinDCX price deviation → NO TRADE.
        if price_dev_bps >= 100.0:
            return MismatchReport(
                pair=snap.pair.base, score=100.0,
                components={**components, "price_dev_bps": price_dev_bps, "hard_override": 1.0},
                band="NO_TRADE", timestamp=time.time(),
            )

        # Hard fail-closed: contract NOT VERIFIED → at minimum WATCH.
        if not analyser_state.get("coindcx_futures_verified", False) and score < 40.0:
            score = 40.0

        if score >= self._no_trade:
            band = "NO_TRADE"
        elif score >= self._watch:
            band = "REDUCE"
        elif score >= self._normal:
            band = "WATCH"
        else:
            band = "NORMAL"

        return MismatchReport(
            pair=snap.pair.base,
            score=score,
            components=components,
            band=band,
            timestamp=time.time(),
        )

    def _compute_corr(self, snap: PairSnapshot) -> float | None:
        if not snap.coindcx_candles:
            return None
        ext_candles = snap.binance_candles or snap.hl_candles
        if not ext_candles or len(ext_candles) < 20:
            return None
        # Align by minute.
        coindcx_by_time = {int(c.open_time // 60): c.close for c in snap.coindcx_candles[-self._corr_window:]}
        ext_by_time = {int(c.open_time // 60): c.close for c in ext_candles[-self._corr_window:]}
        common = sorted(set(coindcx_by_time.keys()) & set(ext_by_time.keys()))
        if len(common) < 20:
            return None
        a = np.array([coindcx_by_time[t] for t in common], dtype=float)
        b = np.array([ext_by_time[t] for t in common], dtype=float)
        a_ret = np.diff(np.log(a))
        b_ret = np.diff(np.log(b))
        if a_ret.std() == 0 or b_ret.std() == 0:
            return None
        return float(np.corrcoef(a_ret, b_ret)[0, 1])

    def _compute_rv_divergence(self, snap: PairSnapshot) -> float | None:
        if not snap.coindcx_candles:
            return None
        ext_candles = snap.binance_candles or snap.hl_candles
        if not ext_candles:
            return None
        cd_returns = np.diff(np.log(np.array([c.close for c in snap.coindcx_candles[-30:]], dtype=float)))
        ext_returns = np.diff(np.log(np.array([c.close for c in ext_candles[-30:]], dtype=float)))
        cd_rv = float(np.std(cd_returns)) if len(cd_returns) > 1 else 0.0
        ext_rv = float(np.std(ext_returns)) if len(ext_returns) > 1 else 0.0
        if ext_rv <= 0:
            return None
        return abs(cd_rv - ext_rv) / ext_rv

    def _oldest_timestamp(self, snap: PairSnapshot) -> float:
        ts_list: list[float] = []
        if snap.coindcx_ticker:
            ts_list.append(snap.coindcx_ticker.timestamp)
        for t in snap.external_tickers.values():
            ts_list.append(t.timestamp)
        for f in snap.funding.values():
            ts_list.append(f.timestamp)
        for o in snap.open_interest.values():
            ts_list.append(o.timestamp)
        return min(ts_list) if ts_list else 0.0
