"""Bounded ring buffer backed by collections.deque(maxlen=N).

Used everywhere to enforce strict RAM bounds. Never grows beyond capacity.
"""
from __future__ import annotations

from collections import deque
from threading import Lock
from typing import Iterator, Iterable, TypeVar

T = TypeVar("T")


class RingBuffer:
    """Thread-safe bounded ring buffer."""

    __slots__ = ("_buf", "_lock", "_maxlen")

    def __init__(self, maxlen: int = 1024) -> None:
        if maxlen <= 0:
            raise ValueError("maxlen must be positive")
        self._maxlen = int(maxlen)
        self._buf: deque[T] = deque(maxlen=self._maxlen)
        self._lock = Lock()

    def append(self, item: T) -> None:
        with self._lock:
            self._buf.append(item)

    def extend(self, items: Iterable[T]) -> None:
        with self._lock:
            self._buf.extend(items)

    def __len__(self) -> int:
        with self._lock:
            return len(self._buf)

    def __iter__(self) -> Iterator[T]:
        with self._lock:
            # Snapshot to make iteration safe outside the lock.
            return iter(list(self._buf))

    @property
    def maxlen(self) -> int:
        return self._maxlen

    def latest(self, n: int = 1) -> list[T]:
        with self._lock:
            if n <= 0:
                return []
            return list(self._buf)[-n:]

    def last(self) -> T | None:
        with self._lock:
            return self._buf[-1] if self._buf else None

    def snapshot(self) -> list[T]:
        with self._lock:
            return list(self._buf)

    def clear(self) -> None:
        with self._lock:
            self._buf.clear()
