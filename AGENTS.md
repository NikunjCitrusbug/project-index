# Project Index Agent Policy

This repository is intentionally friendly to autonomous coding agents. Default to completing the task end-to-end unless a change falls into an explicit approval-required category below.

## Allowed Without Extra Permission

- Read, search, and analyze any file in this repository.
- Run safe local verification such as `python -m py_compile`, `pytest`, `ruff`, and package builds.
- Edit source files, docs, examples, tests, and release metadata inside this repository.
- Update package versions, changelog entries, setup docs, and example commands when they are part of the task.
- Add or refine repo guidance for Claude Code, Codex, Cursor, and MCP integrations.
- Build distribution artifacts in `dist/` for release preparation.

## Ask Before Proceeding

- Publishing to PyPI or any external registry.
- Installing or upgrading dependencies from the network.
- Deleting files outside normal refactors, removing release artifacts, or rewriting git history.
- Changing public API behavior in a way that is likely to break existing users.
- Editing files in the user home directory such as `~/.claude.json`, `~/.claude/settings.json`, or `~/.codex/config.toml` directly as part of development work.
- Handling secrets, tokens, credentials, or production infrastructure settings.

## License Policy

- This repository is released under the MIT License. Preserve the `LICENSE` file and keep the copyright notice intact.
- It is fine to copy, modify, merge, publish, distribute, sublicense, and sell this software under MIT terms.
- When creating substantial copies or derived distributions of this repository, include the MIT license notice.
- Do not introduce code, assets, or documentation copied from sources with incompatible or unclear licenses.
- Prefer original code, MIT-compatible dependencies, or clearly attributed permissive-license material when reusing external work.
- Ask before adding third-party code with copyleft, commercial, source-available, or unknown licensing terms.

## Release Defaults

- Prefer patch version bumps for integration and documentation fixes unless the change is clearly user-facing and breaking.
- Keep `pyproject.toml`, `src/project_index/__init__.py`, runtime version responses, and release notes aligned.
- Update `CHANGELOG.md` for every version bump.
- Prepare artifacts locally, but stop short of publishing unless explicitly instructed.

## Verification Defaults

- Prefer the smallest useful verification first, then broaden if risk is higher.
- If full tests are not available locally, run lightweight syntax validation and report the gap clearly.
