"""Abstract base class for language extractors."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from project_index.store.models import SymbolEntry, RawImport


class LanguageExtractor(ABC):
    """Base class every language extractor must implement."""

    @property
    @abstractmethod
    def language_name(self) -> str:
        ...

    @property
    @abstractmethod
    def extensions(self) -> list[str]:
        ...

    @abstractmethod
    def extract_symbols(
        self, source: bytes, file_path: str
    ) -> tuple[list[SymbolEntry], list[RawImport]]:
        """Parse *source* and return (symbols, raw_imports)."""
        ...

    def get_parser(self) -> Any:
        """Return a configured tree-sitter Parser, or None if grammar unavailable."""
        return None
