from __future__ import annotations

import os
from pathlib import Path
from typing import List

from pydantic_settings import BaseSettings
from pydantic import Field


# Global base directory for all project-index data
BASE_DIR = Path.home() / ".project-index"


class Settings(BaseSettings):
    """Application settings loaded from environment or defaults."""

    host: str = "127.0.0.1"
    port: int = 9120
    project_root: str = Field(default_factory=lambda: os.getcwd())
    index_dir: str = ".project-index"
    max_file_size_kb: int = 512
    exclude_patterns: List[str] = Field(default_factory=lambda: [
        "node_modules", ".git", "__pycache__", ".venv", "venv",
        "dist", "build", ".tox", ".mypy_cache", ".pytest_cache",
        "*.pyc", "*.pyo", "*.so", "*.dylib",
    ])

    # Watch settings
    watch_enabled: bool = True
    watch_debounce_ms: int = 500

    # Query settings
    query_max_results: int = 20
    query_token_budget: int = 8000
    query_context_lines: int = 5

    model_config = {"env_prefix": "PROJECT_INDEX_"}

    @property
    def index_path(self) -> Path:
        """Return the index directory path.

        If index_dir is an absolute path (e.g. from IndexManager), use it directly.
        Otherwise treat it as relative to project_root (legacy behavior for REST API).
        """
        idx = Path(self.index_dir)
        if idx.is_absolute():
            return idx
        return Path(self.project_root) / self.index_dir

    @property
    def index_db_path(self) -> Path:
        return self.index_path / "index.db"
