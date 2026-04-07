# Project Index

Local code indexing service that reduces AI coding tool token usage by 70-90%.

Parses your codebase with tree-sitter, stores symbols and relationships in SQLite, and serves minimal context to AI tools (Claude Code, Cursor, etc.) instead of entire files.

## Install

```bash
pip install project-index[all]
project-index setup
```

That's it. Project Index is now active for every project you work on.

## What happens after setup

1. **`project-index setup`** auto-detects your AI tools (Claude Code, Cursor) and configures them globally
2. When you open any project in Claude Code, the MCP server auto-starts
3. It detects your project root (finds `.git`, `pyproject.toml`, `package.json`, etc.)
4. On first query, it indexes the project (1-3 seconds for typical codebases)
5. On subsequent queries, it syncs only changed files (<100ms)
6. Each project gets a separate, isolated index at `~/.project-index/indexes/<hash>/`
7. Nothing is stored inside your project directories

## How it reduces tokens

**Without Project Index:**
```
You ask:    "How does user authentication work?"
AI reads:   auth/handler.py (400 lines) + models/user.py (150 lines) +
            api/routes.py (500 lines) + auth/tokens.py (100 lines) + ...
Tokens:     ~25,000
Relevant:   ~2,000
Waste:      92%
```

**With Project Index:**
```
You ask:    "How does user authentication work?"
AI calls:   search_codebase("authentication") → 8 symbol signatures (400 tokens)
AI calls:   get_symbol_context("AuthHandler.login") → source + deps (730 tokens)
Tokens:     ~1,130
Waste:      <12%
Savings:    92%
```

Instead of reading entire files, AI tools query the index and receive only the specific functions, classes, and dependency signatures they need.

## Supported languages

| Language | Symbols extracted |
|----------|------------------|
| Python | functions, classes, methods, decorators, imports, variables |
| JavaScript | functions, classes, arrow functions, imports/exports |
| TypeScript | functions, classes, interfaces, type aliases, imports/exports |
| Go | functions, structs, interfaces, methods, imports |

Install only the languages you need:
```bash
pip install project-index[python]          # Python only
pip install project-index[languages]       # All languages
```

## CLI commands

| Command | Purpose |
|---------|---------|
| `project-index setup` | One-time: configure all detected AI tools globally |
| `project-index init` | Pre-index current project (optional, makes first query instant) |
| `project-index status` | Show all indexed projects with stats |
| `project-index serve` | Start REST API server (for non-MCP tools) |
| `project-index reindex` | Force full re-index of current project |
| `project-index mcp` | Start MCP stdio server (called by AI tools, not by users) |
| `project-index uninstall` | Remove all configs and index data |

### Examples

```bash
# Pre-index your project before starting work
cd ~/my-project
project-index init
# → Indexed 342 files, 1,847 symbols in 1.2s. Done.

# Check what's indexed
project-index status
# → Indexed projects (3):
# →   /home/user/project-a
# →     Files: 342  |  Last indexed: 2025-03-25 14:30:00  |  Hash: a1b2c3d4
# →   /home/user/project-b
# →     Files: 89   |  Last indexed: 2025-03-25 12:15:00  |  Hash: e5f6a7b8

# Force re-index after major refactor
project-index reindex
```

## How it works with Claude Code

After `project-index setup`, Claude Code auto-discovers the MCP server. No per-project config needed.

**What `setup` does:**
- Adds to `~/.claude/settings.json`:
  ```json
  {
    "mcpServers": {
      "project-index": {
        "command": "project-index",
        "args": ["mcp"]
      }
    }
  }
  ```
- Claude Code spawns `project-index mcp` as a stdio process when needed
- The MCP server detects your project root from Claude Code's working directory
- Auto-indexes on first query, auto-syncs on subsequent queries
- No HTTP server needed — direct SQLite access

**MCP tools available to Claude Code:**

| Tool | What it does |
|------|-------------|
| `search_codebase` | Find symbols by name (trigram fuzzy search) |
| `get_symbol_context` | Get a symbol's source code + dependency signatures within a token budget |
| `get_project_structure` | File tree with symbol counts per file |
| `find_references` | Dependency graph: who calls this, what does it call |
| `get_file_symbols` | List all symbols in a specific file |
| `reindex` | Force full re-index |

**Example flow when you ask Claude Code a question:**

```
You: "How does the Database class handle connections?"

Claude Code internally:
  1. search_codebase(query="Database")
     → finds Database class in store/database.py (symbol_id, signature, line numbers)

  2. get_symbol_context(symbol="store/database.py::Database", max_tokens=4000)
     → returns:
        - Full source of Database.__init__ and connect methods
        - Signatures of methods it calls
        - Type definitions it depends on
        - Estimated ~280 tokens (vs ~3,500 from reading entire files)

  3. Claude answers using only the relevant context
```

## How it works with Cursor

After `project-index setup`, Cursor gets rules at `~/.cursor/rules/project-index.mdc` that instruct it to query the REST API.

For Cursor, you need the REST server running:
```bash
project-index serve
```

Cursor will use `http://localhost:9120` to search and get context.

## REST API reference

Start with `project-index serve` (default: `http://127.0.0.1:9120`).

### GET /health
```bash
curl http://localhost:9120/health
# {"status":"ok","version":"0.1.0"}
```

### GET /stats
```bash
curl http://localhost:9120/stats
# {"files":34,"symbols":175,"edges":217,"trigrams":2361}
```

### POST /search
Find symbols by name or keyword.
```bash
curl -X POST http://localhost:9120/search \
  -H "Content-Type: application/json" \
  -d '{"query": "Database", "limit": 5}'
```
```json
{
  "results": [
    {
      "symbol_id": "src/store/database.py::Database",
      "name": "Database",
      "kind": "class",
      "file_path": "src/store/database.py",
      "line_start": 15,
      "signature": "class Database:",
      "score": 18.5
    }
  ],
  "total": 1
}
```

### POST /context
Get a symbol's source code and dependency signatures within a token budget. This is the key endpoint for token reduction.
```bash
curl -X POST http://localhost:9120/context \
  -H "Content-Type: application/json" \
  -d '{"symbol_id": "src/store/database.py::Database", "token_budget": 4000, "max_depth": 2}'
```
```json
{
  "symbol": {
    "symbol_id": "src/store/database.py::Database",
    "name": "Database",
    "kind": "class",
    "source": "class Database:\n    def __init__(self, db_path):\n        ...",
    "file_path": "src/store/database.py",
    "line_start": 15,
    "line_end": 95
  },
  "context": [
    {
      "symbol_id": "src/store/models.py::NodeKind",
      "name": "NodeKind",
      "kind": "class",
      "signature": "class NodeKind(str, Enum):",
      "relationship": "uses_type"
    }
  ],
  "tokens_used": 850
}
```

### GET /tree
Project file tree with symbol counts.
```bash
curl http://localhost:9120/tree
```
```json
{
  "files": [
    {"path": "src/store/database.py", "language": "python", "symbols": 12},
    {"path": "src/api/routes.py", "language": "python", "symbols": 10}
  ],
  "total_files": 34
}
```

### GET /symbols
List symbols, optionally filtered.
```bash
# All classes
curl "http://localhost:9120/symbols?kind=class"

# All symbols in a file
curl "http://localhost:9120/symbols?file_path=src/store/database.py"
```

### GET /file/{path}
All symbols in a specific file.
```bash
curl http://localhost:9120/file/src/store/database.py
```

### POST /graph
Dependency subgraph around a symbol.
```bash
curl -X POST http://localhost:9120/graph \
  -H "Content-Type: application/json" \
  -d '{"symbol_id": "src/store/database.py::Database", "max_depth": 2}'
```

### POST /reindex
Force full re-index.
```bash
curl -X POST http://localhost:9120/reindex
```

## Multi-project support

Each project is independently indexed. Indexes are isolated and stored outside your project:

```
~/.project-index/
  projects.json                           # Global registry of all projects
  indexes/
    a1b2c3d4e5f6a7b8/index.db            # /home/user/project-a
    d4e5f6a7b8c9d0e1/index.db            # /home/user/project-b
    f8a9b0c1d2e3f4a5/index.db            # /home/user/project-c
```

- The hash is SHA-256 of the absolute project path (first 16 chars)
- When Claude Code opens in `/project-b/`, the MCP server automatically uses that project's index
- No cross-contamination between projects
- `project-index status` shows all indexed projects

## Configuration

Environment variables (prefix `PROJECT_INDEX_`):

| Variable | Default | Description |
|----------|---------|-------------|
| `PROJECT_INDEX_HOST` | `127.0.0.1` | REST API bind address (always localhost) |
| `PROJECT_INDEX_PORT` | `9120` | REST API port |
| `PROJECT_INDEX_MAX_FILE_SIZE_KB` | `512` | Skip files larger than this |
| `PROJECT_INDEX_WATCH_DEBOUNCE_MS` | `500` | File watcher debounce (REST mode) |

## How indexing works

1. **Discovery** — Walk the project directory, respect `.gitignore`, skip binary/large files
2. **Parsing** — Parse each file with tree-sitter into a Concrete Syntax Tree
3. **Extraction** — Run language-specific queries to extract functions, classes, imports, etc.
4. **Reference resolution** — Resolve imports and call sites across files to build a dependency graph
5. **Trigram indexing** — Build an inverted index of 3-character substrings for fast fuzzy search
6. **Storage** — Store everything in SQLite (WAL mode) with proper indexes

On file changes:
- **MCP mode**: Checks file mtimes on each query, re-indexes only changed files
- **REST mode**: Uses watchdog file watcher with 500ms debounce for real-time updates

## Architecture

```
src/project_index/
  manager.py          # IndexManager: multi-project orchestrator, auto-sync
  cli.py              # Click CLI: setup, init, serve, status, mcp, reindex, uninstall
  server.py           # FastAPI app with lifespan (REST API mode)
  config.py           # Pydantic Settings
  store/
    database.py       # SQLite: tables, CRUD, WAL mode
    models.py         # NodeKind, EdgeKind, SymbolEntry enums/dataclasses
    cache.py          # LRU cache for hot symbols
  indexer/
    core.py           # File walker, indexing orchestration
    parser.py         # Tree-sitter parsing wrapper
    resolver.py       # Cross-file import/call resolution
    incremental.py    # Single-file re-index
    ignore.py         # .gitignore support via pathspec
  languages/
    base.py           # Abstract LanguageExtractor
    python_lang.py    # Python extractor
    javascript_lang.py
    typescript_lang.py
    go_lang.py
    registry.py       # Extension → extractor mapping
  query/
    search.py         # Trigram search + ranking
    context.py        # BFS dependency traversal + token budgeting
    graph.py          # Subgraph extraction
    tokens.py         # Token estimation
  api/
    routes.py         # FastAPI endpoints
    schemas.py        # Pydantic request/response models
  mcp/
    server.py         # Self-contained stdio MCP server (JSON-RPC 2.0)
  watcher/
    handler.py        # Watchdog file watcher (REST mode only)
```

## License

MIT
