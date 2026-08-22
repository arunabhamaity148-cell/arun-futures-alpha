"""FRED macro provider — fetches DGS series (risk-on/off)."""
from __future__ import annotations

from typing import Any

from ..core.exceptions import ProviderError, ProviderUnavailable, SchemaError
from ..core.time_utils import now_ts
from .base import Provider


class FREDProvider(Provider):
    name = "fred"

    def __init__(self, base_url: str, api_key: str = "", **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key

    async def get_series(self, series_id: str) -> dict[str, float]:
        """Fetch latest observations for a FRED series."""
        if not self._api_key:
            return {}
        params = {"series_id": series_id, "api_key": self._api_key, "file_type": "json"}
        try:
            payload = await self._request_with_retry(
                "GET", f"https://api.stlouisfed.org/fred/series/observations", params=params,
            )
        except (ProviderError, ProviderUnavailable, SchemaError):
            return {}
        if not isinstance(payload, dict):
            return {}
        observations = payload.get("observations", [])
        out: dict[str, float] = {}
        for obs in observations[-30:]:  # last 30 days
            try:
                out[str(obs.get("date"))] = float(obs.get("value", "nan"))
            except (TypeError, ValueError):
                continue
        return out
