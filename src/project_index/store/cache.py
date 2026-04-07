"""LRU cache for hot symbol lookups."""

from __future__ import annotations

from functools import lru_cache
from typing import Any


class SymbolCache:
    """Simple LRU cache wrapping database symbol lookups."""

    def __init__(self, db, maxsize: int = 2048):
        self._db = db
        self._maxsize = maxsize
        # Create a cached lookup function
        @lru_cache(maxsize=maxsize)
        def _get(symbol_id: str) -> dict[str, Any] | None:
            return self._db.get_symbol(symbol_id)

        self._get = _get

    def get(self, symbol_id: str) -> dict[str, Any] | None:
        return self._get(symbol_id)

    def invalidate(self, symbol_id: str) -> None:
        self._get.cache_clear()

    def clear(self) -> None:
        self._get.cache_clear()

    def info(self) -> dict:
        ci = self._get.cache_info()
        return {"hits": ci.hits, "misses": ci.misses, "size": ci.currsize, "maxsize": ci.maxsize}
