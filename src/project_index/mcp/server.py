"""
Self-contained stdio-based MCP server for Project Index.

Implements the Model Context Protocol over stdin/stdout using JSON-RPC 2.0.
Directly accesses SQLite database -- NO HTTP calls to a running server.
Auto-detects project root, auto-indexes on first query, auto-syncs on each query.

Usage (called by Claude Code, not by users directly):
    project-index mcp
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from project_index import __version__
from project_index.manager import IndexManager, detect_project_root


# ---------------------------------------------------------------------------
# MCP Tool definitions
# ---------------------------------------------------------------------------

MCP_TOOLS = [
    {
        "name": "search_codebase",
        "description": (
            "Search the indexed codebase for symbols (functions, classes, variables) "
            "matching a query string. Uses trigram matching for fast fuzzy search."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query (symbol name, partial name, or keyword)",
                },
                "kinds": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Filter by symbol kinds: function, class, method, variable, module",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max results to return (default 20)",
                    "default": 20,
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_symbol_context",
        "description": (
            "Get minimal context for a symbol including its source code and related "
            "dependencies via BFS graph traversal. Uses token budgeting to return only "
            "what's needed. First use search_codebase to find the symbol_id."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "The symbol_id to get context for",
                },
                "depth": {
                    "type": "integer",
                    "description": "BFS traversal depth for dependencies (default 1)",
                    "default": 1,
                },
                "max_tokens": {
                    "type": "integer",
                    "description": "Token budget for the returned context (default 4000)",
                    "default": 4000,
                },
            },
            "required": ["symbol"],
        },
    },
    {
        "name": "get_project_structure",
        "description": (
            "Get the project file tree with symbol counts per file. "
            "Useful for understanding overall project layout."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "depth": {
                    "type": "integer",
                    "description": "Directory depth limit (default 3)",
                    "default": 3,
                },
            },
        },
    },
    {
        "name": "find_references",
        "description": (
            "Find all references to/from a symbol in the dependency graph. "
            "Shows what calls this symbol and what this symbol depends on."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "The symbol_id to find references for",
                },
            },
            "required": ["symbol"],
        },
    },
    {
        "name": "get_file_symbols",
        "description": (
            "List all symbols (functions, classes, etc.) defined in a specific file."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Relative file path within the project",
                },
            },
            "required": ["file_path"],
        },
    },
    {
        "name": "reindex",
        "description": (
            "Trigger a full re-index of the project. Use when files have changed "
            "and the index may be stale."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
    },
]

# ---------------------------------------------------------------------------
# MCP Resource definitions
# ---------------------------------------------------------------------------

MCP_RESOURCES = [
    {
        "uri": "project-index://stats",
        "name": "Project Index Stats",
        "description": "Index statistics: file count, symbol count, edge count, trigram count",
        "mimeType": "application/json",
    },
]


# ---------------------------------------------------------------------------
# MCP Server
# ---------------------------------------------------------------------------

class MCPServer:
    """Self-contained stdio-based MCP server implementing JSON-RPC 2.0.

    Directly accesses the SQLite database through IndexManager.
    No HTTP dependency.
    """

    def __init__(self, project_root: Path | None = None) -> None:
        if project_root is None:
            project_root = detect_project_root(Path.cwd())
        self.project_root = project_root
        self._manager: IndexManager | None = None
        self._running = False

    @property
    def manager(self) -> IndexManager:
        """Lazy-init the IndexManager."""
        if self._manager is None:
            self._manager = IndexManager(self.project_root)
        return self._manager

    def _ensure_indexed(self) -> None:
        """Ensure the project is indexed and synced."""
        self.manager.ensure_indexed()

    # -- JSON-RPC helpers --------------------------------------------------

    def _respond(self, id: Any, result: Any) -> None:
        """Send a JSON-RPC success response."""
        msg = {"jsonrpc": "2.0", "id": id, "result": result}
        self._write_message(msg)

    def _error(self, id: Any, code: int, message: str, data: Any = None) -> None:
        """Send a JSON-RPC error response."""
        err: dict[str, Any] = {"code": code, "message": message}
        if data is not None:
            err["data"] = data
        msg = {"jsonrpc": "2.0", "id": id, "error": err}
        self._write_message(msg)

    def _notify(self, method: str, params: dict | None = None) -> None:
        """Send a JSON-RPC notification (no id)."""
        msg: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
        if params:
            msg["params"] = params
        self._write_message(msg)

    def _write_message(self, msg: dict) -> None:
        """Write a JSON-RPC message to stdout with Content-Length header."""
        body = json.dumps(msg)
        header = f"Content-Length: {len(body)}\r\n\r\n"
        sys.stdout.write(header)
        sys.stdout.write(body)
        sys.stdout.flush()

    def _read_message(self) -> dict | None:
        """Read a JSON-RPC message from stdin with Content-Length header."""
        content_length = 0
        while True:
            line = sys.stdin.readline()
            if not line:
                return None  # EOF
            line = line.strip()
            if not line:
                break  # End of headers
            if line.lower().startswith("content-length:"):
                content_length = int(line.split(":", 1)[1].strip())

        if content_length == 0:
            return None

        body = sys.stdin.read(content_length)
        if not body:
            return None
        return json.loads(body)

    # -- MCP protocol handlers ---------------------------------------------

    def handle_initialize(self, id: Any, params: dict) -> None:
        """Handle initialize request."""
        self._respond(id, {
            "protocolVersion": "2024-11-05",
            "capabilities": {
                "tools": {"listChanged": False},
                "resources": {"subscribe": False, "listChanged": False},
            },
            "serverInfo": {
                "name": "project-index",
                "version": __version__,
            },
        })

    def handle_initialized(self, params: dict) -> None:
        """Handle initialized notification."""
        pass

    def handle_tools_list(self, id: Any, params: dict) -> None:
        """Handle tools/list request."""
        self._respond(id, {"tools": MCP_TOOLS})

    def handle_tools_call(self, id: Any, params: dict) -> None:
        """Handle tools/call request -- dispatch directly to IndexManager."""
        tool_name = params.get("name", "")
        arguments = params.get("arguments", {})

        try:
            # Auto-sync before handling request
            self._ensure_indexed()

            result = self._execute_tool(tool_name, arguments)
            self._respond(id, {
                "content": [{"type": "text", "text": json.dumps(result, indent=2, default=str)}],
                "isError": False,
            })
        except Exception as exc:
            self._respond(id, {
                "content": [{"type": "text", "text": f"Error: {exc}"}],
                "isError": True,
            })

    def handle_resources_list(self, id: Any, params: dict) -> None:
        """Handle resources/list request."""
        self._respond(id, {"resources": MCP_RESOURCES})

    def handle_resources_read(self, id: Any, params: dict) -> None:
        """Handle resources/read request."""
        uri = params.get("uri", "")
        try:
            self._ensure_indexed()
            result = self._read_resource(uri)
            self._respond(id, {
                "contents": [{
                    "uri": uri,
                    "mimeType": "application/json",
                    "text": json.dumps(result, indent=2),
                }],
            })
        except Exception as exc:
            self._error(id, -32000, f"Resource read failed: {exc}")

    def handle_ping(self, id: Any, params: dict) -> None:
        """Handle ping request."""
        self._respond(id, {})

    # -- Tool execution (direct DB access) ---------------------------------

    def _execute_tool(self, name: str, args: dict) -> dict:
        """Execute a tool by directly querying the IndexManager."""
        mgr = self.manager

        if name == "search_codebase":
            query = args["query"]
            kinds = args.get("kinds")
            limit = args.get("limit", 20)
            results = mgr.search(query, kinds=kinds, limit=limit)
            return {"results": results, "total": len(results)}

        elif name == "get_symbol_context":
            symbol_id = args["symbol"]
            depth = args.get("depth", 1)
            max_tokens = args.get("max_tokens", 4000)
            return mgr.get_context(symbol_id, depth=depth, max_tokens=max_tokens)

        elif name == "get_project_structure":
            return mgr.get_tree()

        elif name == "find_references":
            symbol_id = args["symbol"]
            return mgr.get_graph(symbol_id, max_depth=2, max_nodes=50)

        elif name == "get_file_symbols":
            file_path = args["file_path"]
            return mgr.get_file_symbols(file_path)

        elif name == "reindex":
            return mgr.full_index()

        else:
            raise ValueError(f"Unknown tool: {name}")

    def _read_resource(self, uri: str) -> dict:
        """Read a resource directly from the database."""
        if uri == "project-index://stats":
            return self.manager.get_stats()
        else:
            raise ValueError(f"Unknown resource: {uri}")

    # -- Main loop ---------------------------------------------------------

    def run(self) -> None:
        """Run the MCP server, reading from stdin and writing to stdout."""
        self._running = True
        _log(f"MCP server started, project_root={self.project_root}")

        while self._running:
            msg = self._read_message()
            if msg is None:
                break  # EOF

            method = msg.get("method", "")
            msg_id = msg.get("id")
            params = msg.get("params", {})

            _log(f"Received: method={method}, id={msg_id}")

            # Dispatch
            handlers = {
                "initialize": self.handle_initialize,
                "notifications/initialized": lambda id, p: self.handle_initialized(p),
                "tools/list": self.handle_tools_list,
                "tools/call": self.handle_tools_call,
                "resources/list": self.handle_resources_list,
                "resources/read": self.handle_resources_read,
                "ping": self.handle_ping,
            }

            handler = handlers.get(method)
            if handler:
                if msg_id is not None:
                    handler(msg_id, params)
                else:
                    handler(None, params)
            elif msg_id is not None:
                self._error(msg_id, -32601, f"Method not found: {method}")

        if self._manager:
            self._manager.close()
        _log("MCP server shutting down.")


def _log(msg: str) -> None:
    """Log to stderr (stdout is reserved for JSON-RPC)."""
    print(f"[project-index-mcp] {msg}", file=sys.stderr, flush=True)


def create_mcp_server(project_root: Path | None = None) -> MCPServer:
    """Create an MCP server instance."""
    return MCPServer(project_root=project_root)


def run_mcp_server(project_root: Path | None = None) -> None:
    """Create and run the MCP server."""
    server = create_mcp_server(project_root=project_root)
    server.run()
