"""Alpha strategy base class."""
from __future__ import annotations

import abc
import math
from dataclasses import dataclass, field
from typing import Any

from ..core.types import Regime, Side
from ..data.manager import PairSnapshot


@dataclass
class AlphaSignal:
    """Output of a single alpha strategy."""

    strategy_id: str
    pair: str                       # BASE/QUOTE
    side: Side
    confidence: float               # 0–100
    edge_estimate_bps: float        # expected gross edge before costs
    primary_alpha: str              # human-readable label
    regime: Regime = Regime.UNKNOWN
    holding_estimate_sec: float = 0.0
    audit: dict[str, Any] = field(default_factory=dict)

    @property
    def is_actionable(self) -> bool:
        return self.side != Side.FLAT and self.confidence >= 30.0


class AlphaStrategy(abc.ABC):
    """Abstract alpha strategy."""

    strategy_id: str = "abstract"
    description: str = ""

    @abc.abstractmethod
    def evaluate(self, snap: PairSnapshot, analyser_state: dict[str, Any]) -> AlphaSignal:
        """Return an AlphaSignal. Side=FLAT if no edge."""
        raise NotImplementedError

    @staticmethod
    def _require(snap: PairSnapshot, *fields: str) -> bool:
        for f in fields:
            v = getattr(snap, f, None)
            if v is None or (hasattr(v, "__len__") and len(v) == 0):
                return False
        return True
