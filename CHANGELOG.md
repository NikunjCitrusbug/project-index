# Changelog

## 0.1.4 - 2026-04-23

- Fixed Claude Code setup to register the MCP server in the current user-scoped config at `~/.claude.json` and mirror to legacy `~/.claude/settings.json`.
- Added Codex MCP auto-registration in `~/.codex/config.toml` so Codex can launch `project-index mcp` directly.
- Updated setup documentation for Claude Code and Codex to reflect current MCP integration paths.
- Unified package and runtime version reporting so the package metadata, REST health response, and MCP server info stay in sync.
- Added repo-level agent policies in `AGENTS.md` and `CLAUDE.md` to support low-friction autonomous maintenance with clear safety boundaries.
