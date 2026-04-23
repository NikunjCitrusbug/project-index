# Setting Up Project Index with Claude Code

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

  ✓ Claude Code — MCP server registered in ~/.claude.json

Project Index is now active. It will auto-index any project you work on.
```

That's it. You're done.

## What happens behind the scenes

`project-index setup` adds a user-scoped MCP server to `~/.claude.json`:

```json
{
    "mcpServers": {
        "project-index": {
            "type": "stdio",
            "command": "project-index",
            "args": ["mcp"],
            "env": {}
        }
    }
}
```

For backward compatibility, it also mirrors the same server to legacy `~/.claude/settings.json`.

This registers globally — it works for **every project** you open in Claude Code, not just one.

## How it works when you use Claude Code

1. You open Claude Code in any project directory
2. Claude Code spawns `project-index mcp` as a stdio process
3. The MCP server detects your project root (looks for `.git`, `pyproject.toml`, etc.)
4. On the first tool call, it indexes the project (1-3 seconds, one-time)
5. On subsequent queries, it checks file mtimes and re-indexes only changed files (<100ms)
6. Claude Code uses the index to answer questions with 70-90% fewer tokens

No HTTP server needed. No per-project config. No manual re-indexing.

## What Claude Code sees

Claude Code discovers these tools automatically:

| Tool                    | What it does                                                  |
| ----------------------- | ------------------------------------------------------------- |
| `search_codebase`       | Find symbols by name (fuzzy trigram search)                   |
| `get_symbol_context`    | Get source code + dependency signatures within a token budget |
| `get_project_structure` | File tree with symbol counts per file                         |
| `find_references`       | Who calls this symbol, what does it depend on                 |
| `get_file_symbols`      | All symbols defined in a specific file                        |
| `reindex`               | Force a full re-index                                         |

## Example: what happens when you ask a question

**You:** "How does the Database class handle connections?"

**Claude Code internally does:**

```
1. search_codebase(query="Database")
   → Returns: [{symbol_id: "src/store/database.py::Database", kind: "class",
                 signature: "class Database:", line_start: 15}]

2. get_symbol_context(symbol="src/store/database.py::Database", max_tokens=4000)
   → Returns: full source of Database class + signatures of its dependencies
   → ~280 tokens instead of ~3,500 from reading entire files
```

**You:** "What calls the process_payment function?"

```
1. search_codebase(query="process_payment")
   → Returns: [{symbol_id: "src/billing/payments.py::process_payment", ...}]

2. find_references(symbol="src/billing/payments.py::process_payment")
   → Returns: {nodes: [...], edges: [{source: "routes.py::checkout", target: "process_payment", kind: "calls"}]}
```

**You:** "Show me the project structure"

```
1. get_project_structure()
   → Returns: {files: [{path: "src/auth/handler.py", symbols: 8}, ...], total_files: 42}
```

## Optional: pre-index for instant first query

```bash
cd ~/my-project
project-index init
# Indexed 342 files, 1,847 symbols in 1.2s. Done.
```

This is optional — the MCP server auto-indexes on first query anyway. But pre-indexing means the first query is instant instead of waiting 1-3 seconds.

## Multiple projects

Each project gets a separate, isolated index. No configuration needed — the MCP server detects which project you're in from Claude Code's working directory.

```bash
project-index status
# Indexed projects (3):
#   /home/user/webapp
#     Files: 342  |  Last indexed: 2025-03-25 14:30:00
#   /home/user/api-service
#     Files: 89   |  Last indexed: 2025-03-25 12:15:00
#   /home/user/data-pipeline
#     Files: 156  |  Last indexed: 2025-03-24 09:00:00
```

Indexes are stored at `~/.project-index/indexes/<hash>/` — nothing is added to your project directories.

## Uninstall

```bash
project-index uninstall
# Removes MCP config from Claude Code settings and deletes all index data
```
