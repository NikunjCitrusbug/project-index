from __future__ import annotations

from project_index.store.database import Database
from project_index.utils.logging import get_logger

logger = get_logger("query.search")


class TrigramSearch:
    """Build trigrams from symbol names and search with ranking."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def search(self, query: str, limit: int = 20) -> list[dict]:
        """Search symbols by trigram matching, then fall back to LIKE."""
        # First try trigram search
        symbol_ids = self.db.search_trigrams(query, limit=limit)

        results = []
        seen = set()
        for sid in symbol_ids:
            if sid in seen:
                continue
            seen.add(sid)
            sym = self.db.get_symbol(sid)
            if sym:
                results.append(sym)

        # If trigram search yielded few results, supplement with LIKE
        if len(results) < limit:
            like_results = self.db.search_symbols(query, limit=limit)
            for sym in like_results:
                if sym["symbol_id"] not in seen:
                    seen.add(sym["symbol_id"])
                    results.append(sym)
                    if len(results) >= limit:
                        break

        return results[:limit]
