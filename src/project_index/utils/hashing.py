"""File content hashing utilities."""

from __future__ import annotations

import hashlib
from pathlib import Path


def hash_content(data: bytes) -> str:
    """Return the SHA-256 hex digest of *data*."""
    return hashlib.sha256(data).hexdigest()


def hash_file(path: Path) -> str:
    """Return the SHA-256 hex digest of a file's contents."""
    return hash_content(path.read_bytes())
