"""A single cached value that is reloaded once it is older than its time-to-live."""
from __future__ import annotations

import threading
import time
from typing import Callable, Generic, TypeVar

T = TypeVar("T")

DEFAULT_TTL = 10.0


class TtlCache(Generic[T]):
    """Holds the result of ``load`` for ``ttl`` seconds; ``refresh=True`` reloads now."""

    def __init__(
        self,
        load: Callable[[], T],
        ttl: float = DEFAULT_TTL,
        clock: Callable[[], float] = time.monotonic,
    ):
        self._load = load
        self._ttl = ttl
        self._clock = clock
        self._value: T | None = None
        self._loaded_at: float | None = None
        self._lock = threading.Lock()

    def get(self, *, refresh: bool = False) -> T:
        if not refresh and not self._expired(self._clock()):
            return self._value  # type: ignore[return-value]
        with self._lock:
            now = self._clock()
            if refresh or self._expired(now):
                self._value = self._load()
                self._loaded_at = now
            return self._value  # type: ignore[return-value]

    def _expired(self, now: float) -> bool:
        return self._loaded_at is None or now - self._loaded_at >= self._ttl
