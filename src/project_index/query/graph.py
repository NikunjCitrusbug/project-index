from __future__ import annotations

from collections import deque

from project_index.store.database import Database
from project_index.utils.logging import get_logger

logger = get_logger("query.graph")


class GraphQuery:
    """Extract a subgraph around a symbol."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def subgraph(
        self,
        symbol_id: str,
        max_depth: int = 2,
        max_nodes: int = 50,
    ) -> dict:
        """Return nodes and edges reachable from symbol_id within max_depth."""
        visited: set[str] = set()
        nodes: list[dict] = []
        edges: list[dict] = []
        queue: deque[tuple[str, int]] = deque([(symbol_id, 0)])

        while queue and len(nodes) < max_nodes:
            current_id, depth = queue.popleft()
            if current_id in visited:
                continue
            visited.add(current_id)

            sym = self.db.get_symbol(current_id)
            if sym:
                nodes.append(sym)

            if depth >= max_depth:
                continue

            out_edges = self.db.get_edges_from(current_id)
            for e in out_edges:
                edges.append(e)
                if e["target_id"] not in visited:
                    queue.append((e["target_id"], depth + 1))

            in_edges = self.db.get_edges_to(current_id)
            for e in in_edges:
                edges.append(e)
                if e["source_id"] not in visited:
                    queue.append((e["source_id"], depth + 1))

        return {"nodes": nodes, "edges": edges}
