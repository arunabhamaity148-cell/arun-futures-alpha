"""GDELT news provider — free, no key — RSS-style headline retrieval.

GDELT DOC 2.0 API: https://api.gdeltproject.org/api/v2/doc/doc?query=...&format=json
"""
from __future__ import annotations

from typing import Any

from ..core.exceptions import ProviderError, ProviderUnavailable, SchemaError
from ..core.time_utils import now_ts
from ..core.types import NewsItem
from .base import Provider


class GDELTProvider(Provider):
    name = "gdelt"

    def __init__(self, base_url: str, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._base_url = base_url.rstrip("/")

    async def search(
        self,
        query: str,
        max_records: int = 25,
        pair_tags: list[str] | None = None,
    ) -> list[NewsItem]:
        try:
            payload = await self._request_with_retry(
                "GET", f"{self._base_url}/doc/doc",
                params={
                    "query": query,
                    "format": "json",
                    "maxrecords": str(max_records),
                    "sort": "datedesc",
                },
            )
        except (ProviderError, ProviderUnavailable, SchemaError):
            return []
        if not isinstance(payload, dict):
            return []
        articles = payload.get("articles", [])
        if not isinstance(articles, list):
            return []
        out: list[NewsItem] = []
        tags = pair_tags or []
        for art in articles[:max_records]:
            try:
                published = float(art.get("seendate_unix", 0) or 0)
                if published == 0:
                    published = now_ts()
                out.append(NewsItem(
                    source="gdelt",
                    headline=str(art.get("title", ""))[:200],
                    severity="MEDIUM",
                    pair_tags=tags,
                    url=str(art.get("url", "")),
                    published_at=published,
                    received_at=now_ts(),
                ))
            except (TypeError, ValueError):
                continue
        return out
