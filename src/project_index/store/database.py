"""SQLite database setup, schema creation, and CRUD operations."""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any

from project_index.store.models import (
    EdgeEntry,
    EdgeKind,
    NodeKind,
    SymbolEntry,
    Visibility,
)
from project_index.utils.logging import get_logger

logger = get_logger("store.database")

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS files (
    file_path TEXT PRIMARY KEY,
    language TEXT,
    size_bytes INTEGER,
    modified_at REAL,
    content_hash TEXT,
    indexed_at REAL,
    parse_status TEXT DEFAULT 'ok',
    parse_error TEXT
);

CREATE TABLE IF NOT EXISTS symbols (
    symbol_id TEXT PRIMARY KEY,
    name TEXT,
    qualified_name TEXT,
    kind TEXT,
    file_path TEXT REFERENCES files(file_path) ON DELETE CASCADE,
    line_start INTEGER,
    line_end INTEGER,
    byte_start INTEGER,
    byte_end INTEGER,
    signature TEXT,
    docstring TEXT,
    parent_id TEXT,
    visibility TEXT DEFAULT 'public',
    decorators TEXT,
    metadata TEXT
);

CREATE TABLE IF NOT EXISTS edges (
    source_id TEXT,
    target_id TEXT,
    kind TEXT,
    target_resolved INTEGER DEFAULT 1,
    metadata TEXT,
    PRIMARY KEY (source_id, target_id, kind)
);

CREATE TABLE IF NOT EXISTS trigrams (
    trigram TEXT,
    symbol_id TEXT REFERENCES symbols(symbol_id) ON DELETE CASCADE,
    source TEXT DEFAULT 'name',
    PRIMARY KEY (trigram, symbol_id, source)
);

CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY
);

INSERT OR IGNORE INTO schema_version (version) VALUES (1);

CREATE INDEX IF NOT EXISTS idx_symbols_name ON symbols(name);
CREATE INDEX IF NOT EXISTS idx_symbols_file ON symbols(file_path);
CREATE INDEX IF NOT EXISTS idx_symbols_kind ON symbols(kind);
CREATE INDEX IF NOT EXISTS idx_edges_target ON edges(target_id);
CREATE INDEX IF NOT EXISTS idx_trigrams_trigram ON trigrams(trigram);
"""


class Database:
    """Thin wrapper around SQLite with CRUD for the index."""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._init_db()

    # ── setup ──────────────────────────────────────────────────────────

    def _init_db(self) -> None:
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.conn.execute("PRAGMA synchronous=NORMAL")
        self.conn.executescript(_SCHEMA_SQL)
        self.conn.commit()
        logger.info("Database initialised at %s", self.db_path)

    def close(self) -> None:
        self.conn.close()

    # ── files ──────────────────────────────────────────────────────────

    def upsert_file(
        self,
        file_path: str,
        language: str,
        size_bytes: int,
        modified_at: float,
        content_hash: str,
        parse_status: str = "ok",
    ) -> None:
        self.conn.execute(
            """INSERT INTO files (file_path, language, size_bytes, modified_at,
                                  content_hash, indexed_at, parse_status)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(file_path) DO UPDATE SET
                 language=excluded.language,
                 size_bytes=excluded.size_bytes,
                 modified_at=excluded.modified_at,
                 content_hash=excluded.content_hash,
                 indexed_at=excluded.indexed_at,
                 parse_status=excluded.parse_status""",
            (file_path, language, size_bytes, modified_at, content_hash, time.time(), parse_status),
        )
        self.conn.commit()

    def get_file(self, file_path: str) -> dict[str, Any] | None:
        row = self.conn.execute("SELECT * FROM files WHERE file_path=?", (file_path,)).fetchone()
        return dict(row) if row else None

    def get_all_files(self) -> list[dict[str, Any]]:
        return [dict(r) for r in self.conn.execute("SELECT * FROM files").fetchall()]

    def delete_file(self, file_path: str) -> None:
        self.conn.execute("DELETE FROM files WHERE file_path=?", (file_path,))
        self.conn.commit()

    def file_needs_reindex(self, file_path: str, content_hash: str) -> bool:
        row = self.conn.execute(
            "SELECT content_hash FROM files WHERE file_path=?", (file_path,)
        ).fetchone()
        if row is None:
            return True
        return row["content_hash"] != content_hash

    # ── symbols ────────────────────────────────────────────────────────

    def upsert_symbol(self, sym: SymbolEntry) -> None:
        self.conn.execute(
            """INSERT INTO symbols (symbol_id, name, qualified_name, kind, file_path,
                                    line_start, line_end, byte_start, byte_end,
                                    signature, docstring, parent_id, visibility,
                                    decorators, metadata)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(symbol_id) DO UPDATE SET
                 name=excluded.name, qualified_name=excluded.qualified_name,
                 kind=excluded.kind, file_path=excluded.file_path,
                 line_start=excluded.line_start, line_end=excluded.line_end,
                 byte_start=excluded.byte_start, byte_end=excluded.byte_end,
                 signature=excluded.signature, docstring=excluded.docstring,
                 parent_id=excluded.parent_id, visibility=excluded.visibility,
                 decorators=excluded.decorators, metadata=excluded.metadata""",
            (
                sym.symbol_id,
                sym.name,
                sym.qualified_name,
                sym.kind.value,
                sym.file_path,
                sym.line_start,
                sym.line_end,
                sym.byte_start,
                sym.byte_end,
                sym.signature,
                sym.docstring,
                sym.parent_id,
                sym.visibility.value,
                json.dumps(sym.decorators),
                json.dumps(sym.metadata),
            ),
        )

    def bulk_upsert_symbols(self, symbols: list[SymbolEntry]) -> None:
        for sym in symbols:
            self.upsert_symbol(sym)
        self.conn.commit()

    def delete_symbols_for_file(self, file_path: str) -> None:
        self.conn.execute("DELETE FROM symbols WHERE file_path=?", (file_path,))
        self.conn.commit()

    def get_symbol(self, symbol_id: str) -> dict[str, Any] | None:
        row = self.conn.execute("SELECT * FROM symbols WHERE symbol_id=?", (symbol_id,)).fetchone()
        return dict(row) if row else None

    def search_symbols(self, name: str, kind: str | None = None, limit: int = 50) -> list[dict]:
        if kind:
            rows = self.conn.execute(
                "SELECT * FROM symbols WHERE name LIKE ? AND kind=? LIMIT ?",
                (f"%{name}%", kind, limit),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM symbols WHERE name LIKE ? LIMIT ?",
                (f"%{name}%", limit),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_symbols_for_file(self, file_path: str) -> list[dict]:
        return [
            dict(r)
            for r in self.conn.execute(
                "SELECT * FROM symbols WHERE file_path=? ORDER BY line_start", (file_path,)
            ).fetchall()
        ]

    def get_all_symbols(self) -> list[dict]:
        return [dict(r) for r in self.conn.execute("SELECT * FROM symbols").fetchall()]

    def symbol_to_entry(self, row: dict) -> SymbolEntry:
        return SymbolEntry(
            symbol_id=row["symbol_id"],
            name=row["name"],
            qualified_name=row["qualified_name"],
            kind=NodeKind(row["kind"]),
            file_path=row["file_path"],
            line_start=row["line_start"],
            line_end=row["line_end"],
            byte_start=row["byte_start"],
            byte_end=row["byte_end"],
            signature=row["signature"],
            docstring=row["docstring"],
            parent_id=row["parent_id"],
            visibility=Visibility(row["visibility"]),
            decorators=json.loads(row["decorators"]) if isinstance(row["decorators"], str) else row["decorators"],
            metadata=json.loads(row["metadata"]) if isinstance(row["metadata"], str) else row["metadata"],
        )

    # ── edges ──────────────────────────────────────────────────────────

    def upsert_edge(self, edge: EdgeEntry) -> None:
        self.conn.execute(
            """INSERT INTO edges (source_id, target_id, kind, target_resolved, metadata)
               VALUES (?,?,?,?,?)
               ON CONFLICT(source_id, target_id, kind) DO UPDATE SET
                 target_resolved=excluded.target_resolved,
                 metadata=excluded.metadata""",
            (
                edge.source_id,
                edge.target_id,
                edge.kind.value,
                int(edge.target_resolved),
                json.dumps(edge.metadata),
            ),
        )

    def bulk_upsert_edges(self, edges: list[EdgeEntry]) -> None:
        for e in edges:
            self.upsert_edge(e)
        self.conn.commit()

    def delete_edges_for_source(self, source_id: str) -> None:
        self.conn.execute("DELETE FROM edges WHERE source_id=?", (source_id,))

    def get_edges_from(self, source_id: str) -> list[dict]:
        return [
            dict(r)
            for r in self.conn.execute(
                "SELECT * FROM edges WHERE source_id=?", (source_id,)
            ).fetchall()
        ]

    def get_edges_to(self, target_id: str) -> list[dict]:
        return [
            dict(r)
            for r in self.conn.execute(
                "SELECT * FROM edges WHERE target_id=?", (target_id,)
            ).fetchall()
        ]

    def get_all_edges(self) -> list[dict]:
        return [dict(r) for r in self.conn.execute("SELECT * FROM edges").fetchall()]

    # ── trigrams ───────────────────────────────────────────────────────

    def build_trigrams_for_symbol(self, symbol_id: str, name: str) -> None:
        """Generate and store trigrams for a symbol name."""
        padded = f"  {name.lower()}  "
        trigrams = {padded[i : i + 3] for i in range(len(padded) - 2)}
        for tri in trigrams:
            self.conn.execute(
                """INSERT OR IGNORE INTO trigrams (trigram, symbol_id, source)
                   VALUES (?, ?, 'name')""",
                (tri, symbol_id),
            )

    def delete_trigrams_for_symbol(self, symbol_id: str) -> None:
        self.conn.execute("DELETE FROM trigrams WHERE symbol_id=?", (symbol_id,))

    def search_trigrams(self, query: str, limit: int = 50) -> list[str]:
        """Return symbol_ids matching the trigram query, ranked by match count."""
        padded = f"  {query.lower()}  "
        trigrams = [padded[i : i + 3] for i in range(len(padded) - 2)]
        if not trigrams:
            return []
        placeholders = ",".join("?" for _ in trigrams)
        rows = self.conn.execute(
            f"""SELECT symbol_id, COUNT(*) as cnt
                FROM trigrams
                WHERE trigram IN ({placeholders})
                GROUP BY symbol_id
                ORDER BY cnt DESC
                LIMIT ?""",
            (*trigrams, limit),
        ).fetchall()
        return [r["symbol_id"] for r in rows]

    # ── stats ──────────────────────────────────────────────────────────

    def stats(self) -> dict[str, int]:
        return {
            "files": self.conn.execute("SELECT COUNT(*) FROM files").fetchone()[0],
            "symbols": self.conn.execute("SELECT COUNT(*) FROM symbols").fetchone()[0],
            "edges": self.conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0],
            "trigrams": self.conn.execute("SELECT COUNT(*) FROM trigrams").fetchone()[0],
        }

    # ── clear ──────────────────────────────────────────────────────────

    def clear_all(self) -> None:
        for table in ("trigrams", "edges", "symbols", "files"):
            self.conn.execute(f"DELETE FROM {table}")
        self.conn.commit()
