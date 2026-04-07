"""IndexManager: central orchestrator for multi-project indexing.

Manages per-project indexes stored at ~/.project-index/indexes/<hash>/index.db
with a global registry at ~/.project-index/projects.json.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any, Callable

from project_index.config import Settings
from project_index.store.database import Database
from project_index.indexer.core import Indexer
from project_index.indexer.parser import TreeSitterParser
from project_index.indexer.ignore import IgnoreFilter
from project_index.query.search import TrigramSearch
from project_index.query.context import ContextResolver
from project_index.query.graph import GraphQuery
from project_index.utils.logging import get_logger

logger = get_logger("manager")

BASE_DIR = Path.home() / ".project-index"
REGISTRY_FILE = BASE_DIR / "projects.json"

# Project root marker files
PROJECT_MARKERS = [
    ".git",
    "pyproject.toml",
    "package.json",
    "Cargo.toml",
    "go.mod",
    "pom.xml",
    "build.gradle",
    "Makefile",
    ".project-index-root",
    "setup.py",
    "setup.cfg",
    "composer.json",
    "Gemfile",
    ".hg",
]


def detect_project_root(start: Path) -> Path:
    """Walk up from start to find project root markers."""
    current = start.resolve()
    while current != current.parent:
        for marker in PROJECT_MARKERS:
            if (current / marker).exists():
                return current
        current = current.parent
    return start.resolve()  # fallback to CWD


def project_hash(project_root: Path) -> str:
    """Compute a stable hash for a project path."""
    return hashlib.sha256(str(project_root.resolve()).encode()).hexdigest()[:16]


def _load_registry() -> dict[str, Any]:
    """Load the global project registry."""
    if REGISTRY_FILE.is_file():
        try:
            return json.loads(REGISTRY_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _save_registry(registry: dict[str, Any]) -> None:
    """Save the global project registry."""
    BASE_DIR.mkdir(parents=True, exist_ok=True)
    REGISTRY_FILE.write_text(json.dumps(registry, indent=2))


class IndexManager:
    """Manages a single project's index with lazy indexing and smart sync."""

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root.resolve()
        self.index_hash = project_hash(self.project_root)
        self.index_dir = BASE_DIR / "indexes" / self.index_hash
        self.index_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.index_dir / "index.db"

        # Create settings for this project
        self.settings = Settings(
            project_root=str(self.project_root),
            index_dir=str(self.index_dir),
        )

        # Init database
        self.db = Database(self.db_path)

        # Lazy-init indexer
        self._indexer: Indexer | None = None
        self._parser: TreeSitterParser | None = None
        self._ignore_filter: IgnoreFilter | None = None

    @property
    def indexer(self) -> Indexer:
        if self._indexer is None:
            self._indexer = Indexer(self.settings, self.db)
        return self._indexer

    @property
    def parser(self) -> TreeSitterParser:
        if self._parser is None:
            self._parser = TreeSitterParser()
        return self._parser

    @property
    def ignore_filter(self) -> IgnoreFilter:
        if self._ignore_filter is None:
            self._ignore_filter = IgnoreFilter(
                str(self.project_root), self.settings.exclude_patterns
            )
        return self._ignore_filter

    def ensure_indexed(self) -> None:
        """Ensure the project is indexed. Full index if never indexed, sync otherwise."""
        stats = self.db.stats()
        if stats["files"] == 0:
            self.full_index()
        else:
            self.sync()

    def full_index(
        self,
        progress_cb: Callable[[dict[str, Any]], None] | None = None,
        heartbeat_seconds: float = 2.0,
        slow_file_seconds: float = 5.0,
    ) -> dict[str, int]:
        """Full index of the project."""
        result = self.indexer.full_index(
            progress_cb=progress_cb,
            heartbeat_seconds=heartbeat_seconds,
            slow_file_seconds=slow_file_seconds,
        )
        self._update_registry(result.get("files_indexed", 0))
        return result

    def sync(self) -> dict[str, int]:
        """Smart sync: check mtimes, re-index only changed files."""
        indexed_files = {
            f["file_path"]: f for f in self.db.get_all_files()
        }

        current_files = self._scan_current_files()

        changed = []
        new_files = []
        deleted = []

        for rel_path, mtime in current_files.items():
            if rel_path not in indexed_files:
                new_files.append(rel_path)
            elif mtime > indexed_files[rel_path]["modified_at"]:
                changed.append(rel_path)

        for rel_path in indexed_files:
            if rel_path not in current_files:
                deleted.append(rel_path)

        if not (changed or new_files or deleted):
            return {"changed": 0, "new": 0, "deleted": 0}

        # Process deletions
        for rel_path in deleted:
            self.db.delete_symbols_for_file(rel_path)
            self.db.delete_file(rel_path)

        # Process changed and new files
        symbols_total = 0
        for rel_path in changed + new_files:
            abs_path = str(self.project_root / rel_path)
            try:
                count = self.indexer.index_file(abs_path, rel_path)
                symbols_total += count
            except Exception as exc:
                logger.warning("Error syncing %s: %s", rel_path, exc)

        result = {
            "changed": len(changed),
            "new": len(new_files),
            "deleted": len(deleted),
            "symbols": symbols_total,
        }

        if changed or new_files or deleted:
            total_files = self.db.stats()["files"]
            self._update_registry(total_files)

        return result

    def _scan_current_files(self) -> dict[str, float]:
        """Scan the project directory and return {rel_path: mtime}."""
        result: dict[str, float] = {}
        max_size = self.settings.max_file_size_kb * 1024

        for dirpath, dirnames, filenames in os.walk(self.project_root):
            dirnames[:] = [
                d for d in dirnames
                if not self.ignore_filter.is_ignored(os.path.join(dirpath, d))
            ]

            for fname in filenames:
                full_path = os.path.join(dirpath, fname)

                if self.ignore_filter.is_ignored(full_path):
                    continue

                try:
                    stat = os.stat(full_path)
                    if stat.st_size > max_size or stat.st_size == 0:
                        continue
                except OSError:
                    continue

                lang = self.parser.get_language(full_path)
                if lang is None:
                    continue

                try:
                    rel_path = os.path.relpath(full_path, self.project_root)
                    result[rel_path] = stat.st_mtime
                except ValueError:
                    continue

        return result

    def _update_registry(self, file_count: int) -> None:
        """Update the global project registry."""
        try:
            registry = _load_registry()
            registry[str(self.project_root)] = {
                "hash": self.index_hash,
                "last_indexed": time.time(),
                "files": file_count,
            }
            _save_registry(registry)
        except Exception as exc:
            logger.warning("Failed to update registry: %s", exc)

    # -- Query methods -------------------------------------------------

    def search(self, query: str, kinds: list[str] | None = None, limit: int = 20) -> list[dict]:
        """Search symbols."""
        searcher = TrigramSearch(self.db)
        results = searcher.search(query, limit=limit)
        if kinds:
            results = [r for r in results if r.get("kind") in kinds]
        return results

    def get_context(
        self, symbol_id: str, depth: int = 1, max_tokens: int = 4000
    ) -> dict:
        """Get symbol context with dependencies."""
        resolver = ContextResolver(self.db, str(self.project_root))
        return resolver.resolve(symbol_id, token_budget=max_tokens, max_depth=depth)

    def get_graph(
        self, symbol_id: str, max_depth: int = 2, max_nodes: int = 50
    ) -> dict:
        """Get dependency subgraph."""
        gq = GraphQuery(self.db)
        return gq.subgraph(symbol_id, max_depth=max_depth, max_nodes=max_nodes)

    def get_tree(self) -> dict:
        """Get project file tree with symbol counts."""
        files = self.db.get_all_files()
        entries = []
        for f in files:
            sym_count = len(self.db.get_symbols_for_file(f["file_path"]))
            entries.append({
                "path": f["file_path"],
                "language": f.get("language"),
                "symbols": sym_count,
            })
        return {"files": entries, "total_files": len(entries)}

    def get_file_symbols(self, file_path: str) -> dict:
        """List all symbols in a specific file."""
        file_info = self.db.get_file(file_path)
        if not file_info:
            return {"file_path": file_path, "language": None, "symbols": []}
        symbols = self.db.get_symbols_for_file(file_path)
        return {
            "file_path": file_path,
            "language": file_info.get("language"),
            "symbols": symbols,
        }

    def get_stats(self) -> dict:
        """Get index statistics."""
        return self.db.stats()

    def close(self) -> None:
        """Close database connection."""
        self.db.close()


def get_all_projects() -> dict[str, Any]:
    """Return the global project registry."""
    return _load_registry()


def remove_project(project_root: str) -> None:
    """Remove a project from the registry and delete its index."""
    import shutil

    registry = _load_registry()
    if project_root in registry:
        index_hash = registry[project_root]["hash"]
        index_dir = BASE_DIR / "indexes" / index_hash
        if index_dir.is_dir():
            shutil.rmtree(index_dir)
        del registry[project_root]
        _save_registry(registry)
