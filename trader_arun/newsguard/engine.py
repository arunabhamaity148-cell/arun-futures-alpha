"""NewsGuard engine.

Classifies news items into CRITICAL/HIGH/MEDIUM/LOW and outputs ALLOW/REDUCE/BLOCK.
Never generates BUY/SELL.

CRITICAL events (FOMC, CPI, NFP, exchange outage, hack, delisting):
   BLOCK new trades for ±2h around event.
HIGH events (PCE, large unlocks, SEC actions):
   REDUCE position sizing.
MEDIUM/LOW: ALLOW.

Includes source health, deduplication, cooldown, pair mapping, severity,
expiry, and fail-safe behaviour (if news provider is down → BLOCK for safety).
"""
from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass
from typing import Deque

from ..core.types import NewsAction, NewsItem, NewsState


@dataclass
class NewsRule:
    pattern: str           # substring to match in headline (case-insensitive)
    severity: str          # CRITICAL | HIGH | MEDIUM | LOW
    pair_tags: list[str]   # which pairs this applies to ("*" = all)
    block_window_sec: float = 2 * 3600   # ±2h around event


# Default rule set — calibrated to research §17.
DEFAULT_RULES: list[NewsRule] = [
    NewsRule("FOMC", "CRITICAL", ["*"], 2 * 3600),
    NewsRule("Federal Reserve", "CRITICAL", ["*"], 2 * 3600),
    NewsRule("rate decision", "CRITICAL", ["*"], 2 * 3600),
    NewsRule("CPI", "CRITICAL", ["*"], 2 * 3600),
    NewsRule("NFP", "CRITICAL", ["*"], 2 * 3600),
    NewsRule("nonfarm", "CRITICAL", ["*"], 2 * 3600),
    NewsRule("PCE", "HIGH", ["*"], 1 * 3600),
    NewsRule("SEC", "HIGH", ["*"], 1 * 3600),
    NewsRule("CFTC", "HIGH", ["*"], 1 * 3600),
    NewsRule("hack", "CRITICAL", ["*"], 3 * 3600),
    NewsRule("exploit", "CRITICAL", ["*"], 3 * 3600),
    NewsRule("delist", "CRITICAL", ["*"], 6 * 3600),
    NewsRule("outage", "HIGH", ["*"], 2 * 3600),
    NewsRule("ETF", "HIGH", ["BTC", "ETH"], 2 * 3600),
    NewsRule("unlock", "HIGH", [], 12 * 3600),
    NewsRule("lawsuit", "MEDIUM", ["*"], 0),
    NewsRule("partnership", "LOW", [], 0),
]


class NewsGuard:
    """Stateful NewsGuard with dedup + cooldown."""

    def __init__(
        self,
        rules: list[NewsRule] | None = None,
        cooldown_sec: float = 300.0,
        max_seen_items: int = 500,
    ) -> None:
        self._rules = rules if rules is not None else DEFAULT_RULES
        self._cooldown_sec = float(cooldown_sec)
        # Dedup ring: hashes of recent headlines.
        self._seen_hashes: Deque[int] = deque(maxlen=max_seen_items)
        self._seen_times: dict[int, float] = {}
        # Active news items, sorted by expiry.
        self._active: list[tuple[float, NewsItem]] = []  # (expiry_ts, item)
        self._provider_available = True

    def mark_provider_unavailable(self) -> None:
        """If news provider is down, fail-safe to BLOCK."""
        self._provider_available = False

    def mark_provider_available(self) -> None:
        self._provider_available = True

    def ingest(self, items: list[NewsItem]) -> None:
        now = time.time()
        for item in items:
            # Dedup by (source, headline) hash.
            h = hash((item.source, item.headline.lower()))
            if h in self._seen_hashes:
                continue
            self._seen_hashes.append(h)
            self._seen_times[h] = now

            # Classify.
            severity, pair_tags, block_window = self._classify(item)
            if severity == "LOW":
                continue  # don't track LOW
            effective_item = NewsItem(
                source=item.source,
                headline=item.headline,
                severity=severity,
                pair_tags=pair_tags or item.pair_tags,
                url=item.url,
                published_at=item.published_at,
                received_at=item.received_at,
            )
            expiry = now + block_window
            self._active.append((expiry, effective_item))

        # Prune expired.
        self._active = [(exp, it) for exp, it in self._active if exp > now]

    def _classify(self, item: NewsItem) -> tuple[str, list[str], float]:
        headline_lower = item.headline.lower()
        for rule in self._rules:
            if rule.pattern.lower() in headline_lower:
                # If rule specifies pair_tags, use them; else keep item's tags.
                pair_tags = rule.pair_tags if rule.pair_tags else item.pair_tags
                return rule.severity, pair_tags, rule.block_window_sec
        return "MEDIUM", item.pair_tags, 0.0

    def state(self, pair_base: str | None = None) -> NewsState:
        now = time.time()
        # Filter to items affecting this pair (or all pairs).
        relevant: list[NewsItem] = []
        for exp, item in self._active:
            if exp <= now:
                continue
            if pair_base is None or "*" in item.pair_tags or pair_base in item.pair_tags:
                relevant.append(item)

        blocking = [i for i in relevant if i.severity == "CRITICAL"]
        reduce = [i for i in relevant if i.severity == "HIGH"]

        if not self._provider_available:
            # Fail-safe: BLOCK when news provider is down.
            action = NewsAction.BLOCK
            cooldown = now + self._cooldown_sec
        elif blocking:
            action = NewsAction.BLOCK
            cooldown = now + self._cooldown_sec
        elif reduce:
            action = NewsAction.REDUCE
            cooldown = now + self._cooldown_sec
        else:
            action = NewsAction.ALLOW
            cooldown = 0.0

        return NewsState(
            action=action,
            blocking_items=blocking,
            reduce_items=reduce,
            cooldown_until=cooldown,
            timestamp=now,
        )

    def reset(self) -> None:
        self._active.clear()
        self._seen_hashes.clear()
        self._seen_times.clear()
