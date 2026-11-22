"""A single cached value that is reloaded once it is older than its time-to-live."""
from __future__ import annotations

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

    def get(self, *, refresh: bool = False) -> T:
        now = self._clock()
        if refresh or self._loaded_at is None or now - self._loaded_at >= self._ttl:
            self._value = self._load()
            self._loaded_at = now
        return self._value  # type: ignore[return-value]
