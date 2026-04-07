from __future__ import annotations

from pathlib import Path

import pathspec

from project_index.utils.logging import get_logger

logger = get_logger("indexer.ignore")


class IgnoreFilter:
    """Load .gitignore + .indexignore and check if paths should be ignored."""

    def __init__(self, project_root: str, extra_patterns: list[str] | None = None) -> None:
        self.project_root = Path(project_root)
        patterns: list[str] = list(extra_patterns or [])

        for ignore_file in (".gitignore", ".indexignore"):
            path = self.project_root / ignore_file
            if path.is_file():
                try:
                    lines = path.read_text(errors="replace").splitlines()
                    patterns.extend(
                        line.strip()
                        for line in lines
                        if line.strip() and not line.strip().startswith("#")
                    )
                except Exception as exc:
                    logger.warning("Failed to read %s: %s", path, exc)

        self._spec = pathspec.PathSpec.from_lines("gitwildmatch", patterns)

    def is_ignored(self, path: str | Path) -> bool:
        """Return True if *path* should be skipped."""
        try:
            rel = str(Path(path).relative_to(self.project_root))
        except ValueError:
            rel = str(path)
        return self._spec.match_file(rel)
