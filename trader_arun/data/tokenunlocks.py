"""TokenUnlocks provider — calendar-based event detection.

The public TokenUnlocks site exposes JSON-ish endpoints via its Next.js app.
If scraping fails, returns empty list — never fabricates unlock dates.
"""
from __future__ import annotations

from typing import Any

from ..core.exceptions import ProviderError, ProviderUnavailable, SchemaError
from ..core.time_utils import now_ts
from ..core.types import NewsItem
from .base import Provider


class TokenUnlocksProvider(Provider):
    name = "tokenunlocks"

    def __init__(self, base_url: str, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._base_url = base_url.rstrip("/")

    async def fetch_upcoming(self, days_ahead: int = 14) -> list[NewsItem]:
        """Returns upcoming token-unlock events as NewsItems.

        Marks severity HIGH for unlocks >1% of supply, MEDIUM otherwise.
        """
        try:
            payload = await self._request_with_retry(
                "GET", f"{self._base_url}/api/unlocks",
                params={"days": str(days_ahead)},
            )
        except (ProviderError, ProviderUnavailable, SchemaError):
            return []
        if not isinstance(payload, list):
            return []
        out: list[NewsItem] = []
        cutoff = now_ts() + days_ahead * 86400
        for row in payload:
            try:
                ts = float(row.get("date", row.get("timestamp", 0)))
                if ts > 1e12:
                    ts /= 1000.0
                if ts < now_ts() or ts > cutoff:
                    continue
                token = str(row.get("token", "")).upper()
                pct = float(row.get("percent_of_supply", 0.0) or 0.0)
                severity = "HIGH" if pct >= 1.0 else "MEDIUM"
                out.append(NewsItem(
                    source="tokenunlocks",
                    headline=f"{token} unlock {pct:.2f}% of supply",
                    severity=severity,
                    pair_tags=[token],
                    url=str(row.get("url", "")),
                    published_at=ts,
                    received_at=now_ts(),
                ))
            except (TypeError, ValueError):
                continue
        return out
