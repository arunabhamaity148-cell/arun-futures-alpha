"""Alpha strategies S1–S5.

Each strategy is original / microstructure- or derivatives-driven — NOT generic
RSI/MACD/EMA-crossover. Each strategy:
- takes a PairSnapshot + per-pair analyser state
- returns an AlphaSignal with side, confidence (0–100), edge_estimate_bps,
  primary_alpha label, and audit trail
- never fabricates data: if required inputs are missing, returns no signal.
"""
from .base import AlphaStrategy, AlphaSignal
from .s1_cascade import S1CascadeExhaustion
from .s2_leadlag import S2LeadLag
from .s3_funding_oi import S3FundingOIUnwind
from .s4_absorption import S4AbsorptionCVD
from .s5_basis import S5BasisConvergence
from .engine import AlphaEngine

__all__ = [
    "AlphaStrategy",
    "AlphaSignal",
    "S1CascadeExhaustion",
    "S2LeadLag",
    "S3FundingOIUnwind",
    "S4AbsorptionCVD",
    "S5BasisConvergence",
    "AlphaEngine",
]
