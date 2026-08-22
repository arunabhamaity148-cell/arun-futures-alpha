"""Monotonic + wallclock time helpers."""
from __future__ import annotations

import time


def now_ts() -> float:
    """Wallclock unix seconds."""
    return time.time()


def now_mono() -> float:
    """Monotonic seconds (for elapsed measurement)."""
    return time.monotonic()


def age_sec(timestamp_wallclock: float) -> float:
    """Age of a wallclock timestamp in seconds."""
    return max(0.0, time.time() - timestamp_wallclock)


def is_fresh(timestamp_wallclock: float, max_age_sec: float) -> bool:
    return age_sec(timestamp_wallclock) <= max_age_sec
