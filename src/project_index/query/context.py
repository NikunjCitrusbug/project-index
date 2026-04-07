from __future__ import annotations

from collections import deque
from pathlib import Path

from project_index.store.database import Database
from project_index.query.tokens import estimate_tokens
from project_index.utils.logging import get_logger

logger = get_logger("query.context")


class ContextResolver:
    """BFS dependency traversal with token budget enforcement."""

    def __init__(self, db: Database, project_root: str) -> None:
        self.db = db
        self.project_root = Path(project_root)

    def resolve(
        self,
        symbol_id: str,
        token_budget: int = 8000,
        max_depth: int = 3,
    ) -> dict:
        """Gather context for a symbol via BFS, staying within token budget."""
        root_sym = self.db.get_symbol(symbol_id)
        if not root_sym:
            return {"symbol": None, "context": [], "tokens_used": 0}

        visited: set[str] = set()
        context_items: list[dict] = []
        tokens_used = 0
        queue: deque[tuple[str, int]] = deque([(symbol_id, 0)])

        while queue and tokens_used < token_budget:
            current_id, depth = queue.popleft()
            if current_id in visited:
                continue
            visited.add(current_id)

            sym = self.db.get_symbol(current_id)
            if not sym:
                continue

            # Read source snippet
            snippet = self._read_snippet(sym)
            snippet_tokens = estimate_tokens(snippet)

            if tokens_used + snippet_tokens > token_budget and context_items:
                break

            context_items.append({
                "symbol_id": sym["symbol_id"],
                "name": sym["name"],
                "kind": sym["kind"],
                "file_path": sym["file_path"],
                "line_start": sym["line_start"],
                "line_end": sym["line_end"],
                "signature": sym["signature"],
                "snippet": snippet,
                "tokens": snippet_tokens,
                "depth": depth,
            })
            tokens_used += snippet_tokens

            # BFS neighbors
            if depth < max_depth:
                edges = self.db.get_edges_from(current_id)
                for edge in edges:
                    if edge["target_id"] not in visited:
                        queue.append((edge["target_id"], depth + 1))
                edges_to = self.db.get_edges_to(current_id)
                for edge in edges_to:
                    if edge["source_id"] not in visited:
                        queue.append((edge["source_id"], depth + 1))

        return {
            "symbol": root_sym,
            "context": context_items,
            "tokens_used": tokens_used,
        }

    def _read_snippet(self, sym: dict) -> str:
        """Read the source lines for a symbol."""
        try:
            file_path = self.project_root / sym["file_path"]
            if not file_path.is_file():
                return sym.get("signature", "")

            lines = file_path.read_text(errors="replace").splitlines()
            start = max(0, sym["line_start"] - 1)
            end = min(len(lines), sym["line_end"])
            return "\n".join(lines[start:end])
        except Exception:
            return sym.get("signature", "")
