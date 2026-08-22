"""Veto base classes."""
from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Any

from ..core.types import Side, VetoReport, VetoSeverity
from ..data.manager import PairSnapshot


@dataclass
class VetoContext:
    """Inputs shared by all vetoes."""

    snap: PairSnapshot
    analyser_state: dict[str, Any] = field(default_factory=dict)
    cfg: Any = None
    signal_side: Side = Side.FLAT


class Veto(abc.ABC):
    """Abstract veto."""

    veto_id: str = "V?"
    description: str = ""

    @abc.abstractmethod
    def evaluate(self, ctx: VetoContext) -> VetoReport:
        raise NotImplementedError
