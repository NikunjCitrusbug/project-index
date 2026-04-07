# CLAUDE.md

## Project Overview
Project Index is a local code indexing service that reduces AI tool token usage by 70-90%. It parses codebases with tree-sitter, stores symbols in SQLite, and serves minimal context via MCP (stdio) and REST API.

## Quick Commands
- Setup (one-time): `project-index setup`
- Pre-index: `project-index init`
- Show indexed projects: `project-index status`
- Start REST API server: `project-index serve`
- Force re-index: `project-index reindex`
- Run MCP server: `project-index mcp`
- Run tests: `pytest tests/`
- Install dev: `pip install -e ".[all,dev]"`

## Architecture

### Multi-project indexing
- Each project gets its own index at `~/.project-index/indexes/<hash>/index.db`
- Global registry at `~/.project-index/projects.json` tracks all projects
- Hash is SHA-256 of the absolute project path (first 16 chars)
- Nothing is stored inside the project directory

### Key components
- `src/project_index/`
  - `manager.py` -- **IndexManager**: central orchestrator for multi-project indexing, auto-sync, lazy indexing
  - `store/` -- SQLite database, models
  - `indexer/` -- Tree-sitter parsing, file walking, reference resolution
  - `languages/` -- Language-specific extractors (Python, JS, TS, Go)
  - `query/` -- Search, context resolution, graph traversal
  - `api/` -- FastAPI REST endpoints
  - `mcp/` -- Self-contained stdio MCP server (no HTTP dependency, uses IndexManager directly)
  - `watcher/` -- File change detection (watchdog, used by REST API server)
  - `cli.py` -- Click CLI: setup, init, serve, status, mcp, reindex, uninstall
  - `server.py` -- FastAPI app with lifespan management (for REST API)
  - `config.py` -- pydantic-settings configuration

### MCP Server (mcp/server.py)
- Stdio JSON-RPC 2.0 server (reads stdin, writes stdout)
- Directly accesses SQLite via IndexManager -- NO HTTP calls
- Auto-detects project root from CWD (walks up to find .git, pyproject.toml, etc.)
- Auto-indexes on first query if project not yet indexed
- Auto-syncs on each query: checks file mtimes, re-indexes only changed files
- Tools: search_codebase, get_symbol_context, get_project_structure, find_references, get_file_symbols, reindex
- Resources: project-index://stats

### IndexManager (manager.py)
- Central class managing per-project indexes
- `ensure_indexed()` -- full index if new, sync if existing
- `sync()` -- smart sync: stat files, re-index only changed/new/deleted
- `full_index()` -- complete re-index via Indexer
- Query methods: `search()`, `get_context()`, `get_graph()`, `get_tree()`, `get_file_symbols()`

### REST API (api/routes.py)
- GET /health, /ready, /stats, /tree, /symbols, /file/{path}
- POST /search, /context, /graph, /reindex
- All endpoints use Pydantic schemas from api/schemas.py

## Database Schema (SQLite)
Four tables: `files`, `symbols`, `edges`, `trigrams`.
- `files`: file_path (PK), language, size_bytes, modified_at, content_hash, indexed_at, parse_status, parse_error
- `symbols`: symbol_id (PK), name, qualified_name, kind, file_path (FK), line_start, line_end, byte_start, byte_end, signature, docstring, parent_id, visibility, decorators (JSON), metadata (JSON)
- `edges`: source_id, target_id, kind -- composite PK (source_id, target_id, kind), target_resolved flag
- `trigrams`: trigram, symbol_id (FK), source -- composite PK, for fast fuzzy search on symbol names
- Indexes on: symbols(name), symbols(file_path), symbols(kind), edges(target_id), trigrams(trigram)

## Indexing Pipeline
1. Walk directory (respect .gitignore via pathspec)
2. For each file: detect language via registry, parse with tree-sitter
3. Run language-specific queries to extract symbols (functions, classes, imports)
4. Resolve cross-file references: imports → IMPORTS edges, calls → CALLS edges
5. Build trigram index from symbol names for fast search
6. Store in SQLite with WAL mode

## Key Design Decisions
- SQLite with WAL mode for persistence and concurrent read/write
- Tree-sitter for multi-language parsing (Python, JS, TS, Go)
- Trigram index for fast fuzzy symbol search
- BFS graph traversal for context resolution with token budgeting
- MCP server is self-contained (no HTTP dependency)
- Indexes stored in ~/.project-index/ (not in project directories)
- 127.0.0.1 only binding for REST API (security)
- Smart sync: stat file mtimes, re-index only changed files

## Code Style
- Ruff for linting, line length 100
- Type hints throughout (Python 3.10+ with `from __future__ import annotations`)
- Pydantic models for API request/response schemas
- Logging via `project_index.utils.logging.get_logger(__name__)`
- All enums inherit from (str, Enum) for JSON serialization
