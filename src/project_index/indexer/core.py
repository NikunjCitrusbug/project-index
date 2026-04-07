from __future__ import annotations

import os
import time
from pathlib import Path

from project_index.config import Settings
from project_index.store.database import Database
from project_index.indexer.parser import TreeSitterParser
from project_index.indexer.ignore import IgnoreFilter
from project_index.indexer.resolver import ReferenceResolver
from project_index.utils.hashing import hash_content
from project_index.utils.logging import get_logger

logger = get_logger("indexer.core")


class Indexer:
    """Walk directory, parse files, build symbols/edges, store in DB."""

    def __init__(self, settings: Settings, db: Database) -> None:
        self.settings = settings
        self.db = db
        self.parser = TreeSitterParser()
        self.ignore_filter = IgnoreFilter(settings.project_root, settings.exclude_patterns)
        self.resolver = ReferenceResolver(db)

    def full_index(self) -> dict[str, int]:
        """Walk the entire project and index all supported files."""
        start = time.time()
        project_root = Path(self.settings.project_root)
        max_size = self.settings.max_file_size_kb * 1024

        files_indexed = 0
        symbols_total = 0
        errors = 0

        for dirpath, dirnames, filenames in os.walk(project_root):
            # Filter out ignored directories in-place
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
                    if stat.st_size > max_size:
                        continue
                    if stat.st_size == 0:
                        continue
                except OSError:
                    continue

                lang = self.parser.get_language(full_path)
                if lang is None:
                    continue

                try:
                    rel_path = os.path.relpath(full_path, project_root)
                    count = self.index_file(full_path, rel_path, lang)
                    files_indexed += 1
                    symbols_total += count
                except Exception as exc:
                    logger.warning("Error indexing %s: %s", full_path, exc)
                    errors += 1

        elapsed = time.time() - start
        logger.info(
            "Full index complete: %d files, %d symbols, %d errors in %.2fs",
            files_indexed, symbols_total, errors, elapsed,
        )
        return {
            "files_indexed": files_indexed,
            "symbols": symbols_total,
            "errors": errors,
            "elapsed_seconds": round(elapsed, 2),
        }

    def index_file(self, abs_path: str, rel_path: str, language: str | None = None) -> int:
        """Index a single file. Returns the number of symbols extracted."""
        try:
            source = Path(abs_path).read_bytes()
        except Exception as exc:
            logger.warning("Cannot read %s: %s", abs_path, exc)
            return 0

        content_hash = hash_content(source)

        # Skip if unchanged
        if not self.db.file_needs_reindex(rel_path, content_hash):
            return 0

        if language is None:
            language = self.parser.get_language(rel_path) or "unknown"

        stat = os.stat(abs_path)

        # Delete old data for this file
        self.db.delete_symbols_for_file(rel_path)

        # Parse
        symbols, imports = self.parser.parse_file(source, rel_path)

        # Store file record
        self.db.upsert_file(
            file_path=rel_path,
            language=language,
            size_bytes=int(stat.st_size),
            modified_at=stat.st_mtime,
            content_hash=content_hash,
            parse_status="ok" if symbols or not source.strip() else "no_symbols",
        )

        # Store symbols and trigrams
        if symbols:
            self.db.bulk_upsert_symbols(symbols)
            for sym in symbols:
                self.db.build_trigrams_for_symbol(sym.symbol_id, sym.name)
            self.db.conn.commit()

        # Resolve and store edges
        if imports:
            edges = self.resolver.resolve_imports(imports, rel_path)
            if edges:
                self.db.bulk_upsert_edges(edges)

        containment_edges = self.resolver.create_containment_edges(rel_path)
        if containment_edges:
            self.db.bulk_upsert_edges(containment_edges)

        return len(symbols)

    def reindex_file(self, abs_path: str) -> int:
        """Re-index a single file (for incremental updates)."""
        project_root = Path(self.settings.project_root)
        try:
            rel_path = os.path.relpath(abs_path, project_root)
        except ValueError:
            return 0

        if self.ignore_filter.is_ignored(abs_path):
            return 0

        if not os.path.isfile(abs_path):
            # File was deleted
            self.db.delete_file(rel_path)
            return 0

        lang = self.parser.get_language(rel_path)
        if lang is None:
            return 0

        return self.index_file(abs_path, rel_path, lang)
