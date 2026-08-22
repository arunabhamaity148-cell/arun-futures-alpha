"""Cost model — fees, slippage, funding, latency, partial fills, missing data."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class CostModel:
    """Realistic cost model for backtests and forward tests."""
    taker_fee_bps: float = 5.0           # 0.05% per side
    maker_fee_bps: float = 2.0           # 0.02% per side
    slippage_bps: float = 3.0            # market-order slippage estimate
    funding_8h_bps: float = 0.5          # 0.005% per 8h cycle (avg)
    latency_sec: float = 15.0            # signal → manual execution delay
    partial_fill_rate: float = 0.10      # 10% of trades have partial fills
    outage_drop_rate: float = 0.02       # 2% of trades dropped due to outage

    def round_trip_cost_bps(self, holding_periods_8h: float = 1.0) -> float:
        """Total round-trip cost in bps (entry + exit + funding)."""
        return (
            2 * (self.taker_fee_bps + self.slippage_bps)
            + self.funding_8h_bps * holding_periods_8h
        )

    def net_edge_bps(self, gross_edge_bps: float, holding_periods_8h: float = 1.0) -> float:
        return gross_edge_bps - self.round_trip_cost_bps(holding_periods_8h)
