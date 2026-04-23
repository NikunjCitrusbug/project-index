# Setting Up Project Index with Cursor

## Step 1: Install

```bash
pip install project-index[all]
```

## Step 2: Run setup

```bash
project-index setup
```

Output:
```
Project Index setup complete!

  ✓ Cursor — Rules added

Project Index is now active. It will auto-index any project you work on.
```

Setup creates `~/.cursor/rules/project-index.mdc` with instructions that tell Cursor how to use the REST API.

## Step 3: Start the server

Cursor doesn't support MCP stdio, so it uses the REST API. Start the server for your project:

```bash
cd ~/my-project
project-index serve
```

Output:
```
INFO: Uvicorn running on http://127.0.0.1:9120
```

Leave this running in a terminal (or run with `&` to background it).

## Step 4: Verify

```bash
# Health check
curl http://localhost:9120/health
# {"status":"ok","version":"0.1.4"}

# Check what's indexed
curl http://localhost:9120/stats
# {"files":42,"symbols":387,"edges":156,"trigrams":2341}

# Search for a symbol
curl -X POST http://localhost:9120/search \
  -H "Content-Type: application/json" \
  -d '{"query": "Database", "limit": 5}'
```

## How Cursor uses it

The rules file teaches Cursor to query these endpoints:

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/search` | POST | Find symbols by name: `{"query": "ClassName", "limit": 10}` |
| `/context` | POST | Get source + dependencies: `{"symbol_id": "...", "token_budget": 4000}` |
| `/tree` | GET | Project file tree with symbol counts |
| `/file/{path}` | GET | All symbols in a specific file |
| `/graph` | POST | Dependency graph for a symbol |
| `/stats` | GET | Index statistics |

## Tips

- **Pre-index for speed:** Run `project-index init` before starting the server so the first request is instant
- **Auto-start:** Add `project-index serve &` to your shell startup or use a process manager
- **Custom port:** `project-index serve --port 8080` (update the rules file accordingly)
- **Multiple projects:** Run separate servers on different ports, or switch the `--project-root` flag
- **After big refactors:** Run `project-index reindex` or `curl -X POST http://localhost:9120/reindex`

## Uninstall

```bash
project-index uninstall
# Removes Cursor rules and deletes all index data
```
