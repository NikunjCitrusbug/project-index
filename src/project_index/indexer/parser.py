from __future__ import annotations

from project_index.languages.registry import LanguageRegistry
from project_index.store.models import SymbolEntry, RawImport
from project_index.utils.logging import get_logger

logger = get_logger("indexer.parser")


class TreeSitterParser:
    """Wraps tree-sitter via language extractors. Gracefully handles missing grammars."""

    def __init__(self) -> None:
        self.registry = LanguageRegistry()

    def parse_file(
        self, source: bytes, file_path: str
    ) -> tuple[list[SymbolEntry], list[RawImport]]:
        extractor = self.registry.get_extractor(file_path)
        if extractor is None:
            return [], []
        try:
            return extractor.extract_symbols(source, file_path)
        except Exception as exc:
            logger.warning("Failed to parse %s: %s", file_path, exc)
            return [], []

    def get_language(self, file_path: str) -> str | None:
        return self.registry.get_language(file_path)
