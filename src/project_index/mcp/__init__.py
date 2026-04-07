"""MCP (Model Context Protocol) server for Project Index.

Implements a self-contained stdio-based JSON-RPC server that directly
accesses the SQLite database. No HTTP dependency.
"""

from project_index.mcp.server import create_mcp_server, run_mcp_server

__all__ = ["create_mcp_server", "run_mcp_server"]
