from __future__ import annotations

from project_index.store.database import Database
from project_index.store.models import EdgeKind, RawImport, EdgeEntry
from project_index.utils.logging import get_logger

logger = get_logger("indexer.resolver")


class ReferenceResolver:
    """Resolve imports across files and create edges."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def resolve_imports(self, imports: list[RawImport], source_file: str) -> list[EdgeEntry]:
        """Try to resolve raw imports to existing symbols and create IMPORTS edges."""
        edges: list[EdgeEntry] = []
        file_symbol_id = f"{source_file}::__file__"

        for imp in imports:
            # Try to find the target symbol
            target_name = imp.name
            candidates = self.db.search_symbols(target_name, limit=5)

            resolved = False
            for cand in candidates:
                if cand["name"] == target_name:
                    edges.append(EdgeEntry(
                        source_id=file_symbol_id,
                        target_id=cand["symbol_id"],
                        kind=EdgeKind.IMPORTS,
                        target_resolved=True,
                        metadata={"module": imp.module, "line": imp.line},
                    ))
                    resolved = True
                    break

            if not resolved:
                # Create an unresolved edge
                target_id = f"unresolved::{imp.module}.{imp.name}"
                edges.append(EdgeEntry(
                    source_id=file_symbol_id,
                    target_id=target_id,
                    kind=EdgeKind.IMPORTS,
                    target_resolved=False,
                    metadata={"module": imp.module, "line": imp.line},
                ))

        return edges

    def create_containment_edges(self, file_path: str) -> list[EdgeEntry]:
        """Create CONTAINS edges from file to its top-level symbols."""
        edges: list[EdgeEntry] = []
        symbols = self.db.get_symbols_for_file(file_path)
        file_id = f"{file_path}::__file__"
        for sym in symbols:
            if not sym.get("parent_id"):
                edges.append(EdgeEntry(
                    source_id=file_id,
                    target_id=sym["symbol_id"],
                    kind=EdgeKind.CONTAINS,
                    target_resolved=True,
                ))
        return edges
