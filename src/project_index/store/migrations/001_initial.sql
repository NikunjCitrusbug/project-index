-- Initial schema for project-index SQLite database

CREATE TABLE IF NOT EXISTS files (
    file_path   TEXT PRIMARY KEY,
    language    TEXT NOT NULL DEFAULT '',
    size_bytes  INTEGER NOT NULL DEFAULT 0,
    modified_at REAL NOT NULL DEFAULT 0,
    content_hash TEXT NOT NULL DEFAULT '',
    indexed_at  REAL NOT NULL DEFAULT 0,
    parse_status TEXT NOT NULL DEFAULT 'pending'
);

CREATE TABLE IF NOT EXISTS symbols (
    symbol_id      TEXT PRIMARY KEY,
    name           TEXT NOT NULL,
    qualified_name TEXT NOT NULL,
    kind           TEXT NOT NULL,
    file_path      TEXT NOT NULL REFERENCES files(file_path) ON DELETE CASCADE,
    line_start     INTEGER NOT NULL DEFAULT 0,
    line_end       INTEGER NOT NULL DEFAULT 0,
    byte_start     INTEGER NOT NULL DEFAULT 0,
    byte_end       INTEGER NOT NULL DEFAULT 0,
    signature      TEXT NOT NULL DEFAULT '',
    docstring      TEXT NOT NULL DEFAULT '',
    parent_id      TEXT NOT NULL DEFAULT '',
    visibility     TEXT NOT NULL DEFAULT 'public',
    decorators     TEXT NOT NULL DEFAULT '[]',
    metadata       TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_symbols_name ON symbols(name);
CREATE INDEX IF NOT EXISTS idx_symbols_file ON symbols(file_path);
CREATE INDEX IF NOT EXISTS idx_symbols_kind ON symbols(kind);
CREATE INDEX IF NOT EXISTS idx_symbols_qualified ON symbols(qualified_name);

CREATE TABLE IF NOT EXISTS edges (
    source_id       TEXT NOT NULL,
    target_id       TEXT NOT NULL,
    kind            TEXT NOT NULL,
    target_resolved INTEGER NOT NULL DEFAULT 0,
    metadata        TEXT NOT NULL DEFAULT '{}',
    PRIMARY KEY (source_id, target_id, kind)
);

CREATE INDEX IF NOT EXISTS idx_edges_source ON edges(source_id);
CREATE INDEX IF NOT EXISTS idx_edges_target ON edges(target_id);

CREATE TABLE IF NOT EXISTS trigrams (
    trigram   TEXT NOT NULL,
    symbol_id TEXT NOT NULL REFERENCES symbols(symbol_id) ON DELETE CASCADE,
    source    TEXT NOT NULL DEFAULT 'name',
    PRIMARY KEY (trigram, symbol_id)
);

CREATE INDEX IF NOT EXISTS idx_trigrams_trigram ON trigrams(trigram);
