from __future__ import annotations

import json
import re
import shutil
import time
from pathlib import Path

import click

from project_index.manager import (
    BASE_DIR,
    REGISTRY_FILE,
    IndexManager,
    detect_project_root,
    get_all_projects,
    remove_project,
)


@click.group()
def cli():
    """project-index: local code indexing service for AI tools."""
    pass


def _read_json_file(path: Path) -> dict:
    """Read a JSON file, returning an empty object on parse/read failure."""
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def _write_json_file(path: Path, data: dict) -> None:
    """Write JSON with a stable format."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2))


def _upsert_toml_section(path: Path, section_name: str, body_lines: list[str]) -> None:
    """Replace or append a simple TOML section while preserving other content."""
    text = path.read_text() if path.is_file() else ""
    pattern = rf"(?ms)^\[{re.escape(section_name)}\]\n.*?(?=^\[|\Z)"
    replacement = f"[{section_name}]\n" + "\n".join(body_lines).rstrip() + "\n"

    if re.search(pattern, text):
        updated = re.sub(pattern, replacement, text)
    else:
        updated = text.rstrip()
        if updated:
            updated += "\n\n"
        updated += replacement

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(updated)


def _remove_toml_section(path: Path, section_name: str) -> bool:
    """Remove a simple TOML section if present."""
    if not path.is_file():
        return False

    text = path.read_text()
    pattern = rf"(?ms)^\[{re.escape(section_name)}\]\n.*?(?=^\[|\Z)"
    updated, count = re.subn(pattern, "", text)
    if count == 0:
        return False

    updated = re.sub(r"\n{3,}", "\n\n", updated).strip()
    if updated:
        updated += "\n"
    path.write_text(updated)
    return True


# ── setup ──────────────────────────────────────────────────────────────

@cli.command()
def setup():
    """One-time setup: auto-detect and configure all installed AI tools."""
    configured = []
    not_detected = []

    # -- Claude Code --
    claude_dir = Path.home() / ".claude"
    claude_user_config = Path.home() / ".claude.json"
    claude_detected = claude_dir.exists() or claude_user_config.exists() or shutil.which("claude") is not None
    if claude_detected:
        user_config = _read_json_file(claude_user_config)
        user_mcp_servers = user_config.get("mcpServers", {})
        user_mcp_servers["project-index"] = {
            "type": "stdio",
            "command": "project-index",
            "args": ["mcp"],
            "env": {},
        }
        user_config["mcpServers"] = user_mcp_servers
        _write_json_file(claude_user_config, user_config)

        # Older Claude Code builds stored MCP config in ~/.claude/settings.json.
        # Keep the legacy location in sync for backward compatibility.
        legacy_settings_file = claude_dir / "settings.json"
        legacy_settings = _read_json_file(legacy_settings_file)
        legacy_mcp_servers = legacy_settings.get("mcpServers", {})
        legacy_mcp_servers["project-index"] = {
            "command": "project-index",
            "args": ["mcp"],
        }
        legacy_settings["mcpServers"] = legacy_mcp_servers
        _write_json_file(legacy_settings_file, legacy_settings)

        configured.append(("Claude Code", "MCP server registered in ~/.claude.json"))
    else:
        not_detected.append("Claude Code")

    # -- Cursor --
    cursor_dir = Path.home() / ".cursor"
    if cursor_dir.exists():
        rules_dir = cursor_dir / "rules"
        rules_dir.mkdir(parents=True, exist_ok=True)
        rules_file = rules_dir / "project-index.mdc"
        rules_file.write_text(
            """---
description: Project Index - local code indexing for reduced token usage
globs: "**/*"
alwaysApply: true
---

# Project Index

This project has a local code index available via REST API at http://localhost:9120.
Before reading entire files, query the index to find relevant symbols:

1. Search: POST http://localhost:9120/search {"query": "ClassName"}
2. Context: POST http://localhost:9120/context {"symbol_id": "...", "token_budget": 4000}
3. Structure: GET http://localhost:9120/tree

Start the server with: project-index serve

Use the index to find relevant code instead of scanning directories.
"""
        )
        configured.append(("Cursor", "Rules added"))
    else:
        not_detected.append("Cursor")

    # -- Codex CLI (OpenAI) --
    codex_detected = shutil.which("codex") is not None
    if codex_detected:
        codex_config = Path.home() / ".codex" / "config.toml"
        _upsert_toml_section(
            codex_config,
            "mcp_servers.project-index",
            [
                'command = "project-index"',
                'args = ["mcp"]',
            ],
        )
        configured.append((
            "Codex CLI",
            "MCP server registered in ~/.codex/config.toml",
        ))
    else:
        not_detected.append("Codex CLI")

    # -- VS Code --
    vscode_dirs = [
        Path.home() / ".vscode",
        Path.home() / ".config" / "Code",
    ]
    vscode_found = any(d.exists() for d in vscode_dirs)
    if vscode_found:
        not_detected.append("VS Code (MCP extension needed - install manually)")
    else:
        not_detected.append("VS Code")

    # -- Print summary --
    click.echo()
    click.echo("Project Index setup complete!")
    click.echo()
    for tool, detail in configured:
        click.echo(f"  \u2713 {tool} \u2014 {detail}")
    for tool in not_detected:
        click.echo(f"  \u2717 {tool} \u2014 not detected")
    click.echo()
    click.echo("Project Index is now active. It will auto-index any project you work on.")


# ── init ───────────────────────────────────────────────────────────────

@cli.command()
@click.option("--project-root", default=None, help="Project root directory (default: current directory)")
def init(project_root: str | None):
    """Pre-index the current project (optional pre-warming)."""
    if project_root:
        root = Path(project_root).resolve()
    else:
        root = Path.cwd().resolve()

    click.echo(f"Indexing {root} ...")
    start = time.time()

    def _progress(event: dict) -> None:
        if event.get("event") == "slow_file":
            click.echo(
                f"Still indexing... slow file: {event.get('file_path')} "
                f"({event.get('file_elapsed_seconds')}s)"
            )
            return
        click.echo(
            f"Progress: seen {event.get('files_seen', 0)} supported files, "
            f"indexed {event.get('files_indexed', 0)}, "
            f"symbols {event.get('symbols', 0)}, "
            f"errors {event.get('errors', 0)} "
            f"({event.get('elapsed_seconds', 0)}s)"
        )

    manager = IndexManager(root)
    result = manager.full_index(progress_cb=_progress)
    elapsed = time.time() - start
    manager.close()

    click.echo(
        f"Indexed {result['files_indexed']} files, "
        f"{result['symbols']} symbols in {elapsed:.1f}s. Done."
    )


# ── serve ──────────────────────────────────────────────────────────────

@cli.command()
@click.option("--host", default="127.0.0.1", help="Bind host")
@click.option("--port", default=9120, type=int, help="Bind port")
@click.option("--project-root", default=None, help="Project root directory")
def serve(host: str, port: int, project_root: str | None):
    """Start the REST API server (optional, for non-MCP tools)."""
    import os
    import uvicorn

    if project_root:
        os.environ["PROJECT_INDEX_PROJECT_ROOT"] = project_root
    os.environ["PROJECT_INDEX_HOST"] = host
    os.environ["PROJECT_INDEX_PORT"] = str(port)

    uvicorn.run(
        "project_index.server:app",
        host=host,
        port=port,
        log_level="info",
    )


# ── status ─────────────────────────────────────────────────────────────

@cli.command()
def status():
    """Show all indexed projects and their stats."""
    projects = get_all_projects()

    if not projects:
        click.echo("No projects indexed yet.")
        click.echo("Run 'project-index init' in a project directory to index it.")
        return

    click.echo(f"Indexed projects ({len(projects)}):")
    click.echo()

    for project_path, info in sorted(projects.items()):
        last_indexed = time.strftime(
            "%Y-%m-%d %H:%M:%S",
            time.localtime(info.get("last_indexed", 0)),
        )
        files = info.get("files", 0)
        hash_prefix = info.get("hash", "???")[:8]
        click.echo(f"  {project_path}")
        click.echo(f"    Files: {files}  |  Last indexed: {last_indexed}  |  Hash: {hash_prefix}")
        click.echo()


# ── mcp ────────────────────────────────────────────────────────────────

@cli.command()
def mcp():
    """Start MCP stdio server (called by Claude Code, not by users)."""
    from project_index.mcp.server import run_mcp_server

    run_mcp_server()


# ── reindex ────────────────────────────────────────────────────────────

@cli.command()
@click.option("--project-root", default=None, help="Project root directory (default: current directory)")
def reindex(project_root: str | None):
    """Force full re-index of current project."""
    if project_root:
        root = Path(project_root).resolve()
    else:
        root = Path.cwd().resolve()

    click.echo(f"Re-indexing {root} ...")
    start = time.time()

    def _progress(event: dict) -> None:
        if event.get("event") == "slow_file":
            click.echo(
                f"Still indexing... slow file: {event.get('file_path')} "
                f"({event.get('file_elapsed_seconds')}s)"
            )
            return
        click.echo(
            f"Progress: seen {event.get('files_seen', 0)} supported files, "
            f"indexed {event.get('files_indexed', 0)}, "
            f"symbols {event.get('symbols', 0)}, "
            f"errors {event.get('errors', 0)} "
            f"({event.get('elapsed_seconds', 0)}s)"
        )

    manager = IndexManager(root)
    manager.db.clear_all()
    result = manager.full_index(progress_cb=_progress)
    elapsed = time.time() - start
    manager.close()

    click.echo(
        f"Re-indexed {result['files_indexed']} files, "
        f"{result['symbols']} symbols in {elapsed:.1f}s. Done."
    )


# ── export ─────────────────────────────────────────────────────────────

@cli.command()
@click.option("--format", "fmt", default="agents-md", type=click.Choice(["agents-md", "json"]),
              help="Output format")
@click.option("--port", default=9120, type=int, help="REST API port (for agents-md instructions)")
@click.option("--project-root", default=None, help="Project root directory (default: auto-detect)")
def export(fmt: str, port: int, project_root: str | None):
    """Export project index as AGENTS.md (for Codex) or JSON."""
    if project_root:
        root = Path(project_root).resolve()
    else:
        root = detect_project_root(Path.cwd())

    manager = IndexManager(root)
    manager.ensure_indexed()
    stats = manager.get_stats()
    tree = manager.get_tree()

    if fmt == "json":
        # Raw JSON export of all symbols
        all_symbols = manager.db.get_all_symbols()
        output = json.dumps({
            "project_root": str(root),
            "stats": stats,
            "symbols": all_symbols,
        }, indent=2, default=str)
        click.echo(output)
    else:
        # Generate AGENTS.md for Codex
        lines = [
            "# Project Index",
            "",
            "This project has a local code index available via REST API.",
            f"Start the server: `project-index serve --port {port}`",
            "",
            "## How to use the index",
            "",
            "Before reading entire files, query the index to find relevant symbols.",
            "This dramatically reduces the amount of code you need to read.",
            "",
            "### Search for symbols",
            "```bash",
            f'curl -s -X POST http://localhost:{port}/search \\',
            '  -H "Content-Type: application/json" \\',
            "  -d '{\"query\": \"ClassName\", \"limit\": 10}'",
            "```",
            "",
            "### Get symbol context (source + dependencies, token-budgeted)",
            "```bash",
            f'curl -s -X POST http://localhost:{port}/context \\',
            '  -H "Content-Type: application/json" \\',
            "  -d '{\"symbol_id\": \"<id from search>\", \"token_budget\": 4000}'",
            "```",
            "",
            "### See project structure",
            "```bash",
            f"curl -s http://localhost:{port}/tree",
            "```",
            "",
            "### Get all symbols in a file",
            "```bash",
            f"curl -s http://localhost:{port}/file/path/to/file.py",
            "```",
            "",
            "### Dependency graph for a symbol",
            "```bash",
            f'curl -s -X POST http://localhost:{port}/graph \\',
            '  -H "Content-Type: application/json" \\',
            "  -d '{\"symbol_id\": \"<id>\", \"max_depth\": 2}'",
            "```",
            "",
            "## Workflow",
            "",
            "1. Search the index first to find relevant symbols",
            "2. Use /context to get minimal source + dependencies instead of reading entire files",
            "3. This saves tokens and gives focused, accurate context",
            "",
            f"## Project Stats",
            "",
            f"- Files: {stats.get('files', 0)}",
            f"- Symbols: {stats.get('symbols', 0)}",
            f"- Edges: {stats.get('edges', 0)}",
            "",
            "## File Overview",
            "",
        ]

        for entry in tree.get("files", [])[:50]:
            lang = entry.get("language") or "?"
            sym_count = entry.get("symbols", 0)
            lines.append(f"- `{entry['path']}` ({lang}, {sym_count} symbols)")

        if len(tree.get("files", [])) > 50:
            remaining = len(tree["files"]) - 50
            lines.append(f"- ... and {remaining} more files")

        click.echo("\n".join(lines))

    manager.close()


# ── uninstall ──────────────────────────────────────────────────────────

@cli.command()
@click.confirmation_option(prompt="Remove all Project Index configs and data?")
def uninstall():
    """Remove all configs from AI tools and clean up data."""
    removed = []

    # -- Claude Code --
    claude_user_config = Path.home() / ".claude.json"
    if claude_user_config.is_file():
        user_config = _read_json_file(claude_user_config)
        user_mcp_servers = user_config.get("mcpServers", {})
        if "project-index" in user_mcp_servers:
            del user_mcp_servers["project-index"]
            user_config["mcpServers"] = user_mcp_servers
            _write_json_file(claude_user_config, user_config)
            removed.append("Claude Code MCP config (~/.claude.json)")

    claude_settings = Path.home() / ".claude" / "settings.json"
    if claude_settings.is_file():
        settings = _read_json_file(claude_settings)
        mcp_servers = settings.get("mcpServers", {})
        if "project-index" in mcp_servers:
            del mcp_servers["project-index"]
            settings["mcpServers"] = mcp_servers
            _write_json_file(claude_settings, settings)
            removed.append("Claude Code legacy settings (~/.claude/settings.json)")

    # -- Cursor --
    cursor_rules = Path.home() / ".cursor" / "rules" / "project-index.mdc"
    if cursor_rules.is_file():
        cursor_rules.unlink()
        removed.append("Cursor rules")

    # -- Codex CLI --
    codex_config = Path.home() / ".codex" / "config.toml"
    if _remove_toml_section(codex_config, "mcp_servers.project-index"):
        removed.append("Codex MCP config (~/.codex/config.toml)")

    # -- Codex AGENTS.md note --
    # We don't auto-delete AGENTS.md since the user may have other content in it

    # -- Data --
    if BASE_DIR.is_dir():
        shutil.rmtree(BASE_DIR)
        removed.append(f"Index data ({BASE_DIR})")

    click.echo("Project Index uninstalled.")
    for item in removed:
        click.echo(f"  \u2713 Removed: {item}")
    if not removed:
        click.echo("  Nothing to remove.")
