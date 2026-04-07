from __future__ import annotations

from project_index.languages.base import LanguageExtractor
from project_index.languages.python_lang import PythonExtractor
from project_index.languages.javascript_lang import JavaScriptExtractor
from project_index.languages.typescript_lang import TypeScriptExtractor
from project_index.languages.go_lang import GoExtractor
from project_index.utils.logging import get_logger

logger = get_logger("languages.registry")


class LanguageRegistry:
    """Maps file extensions to language extractors."""

    def __init__(self) -> None:
        self._extractors: dict[str, LanguageExtractor] = {}
        self._register_defaults()

    def _register_defaults(self) -> None:
        for cls in (PythonExtractor, JavaScriptExtractor, TypeScriptExtractor, GoExtractor):
            ext = cls()
            for extension in ext.extensions:
                self._extractors[extension] = ext

    def get_extractor(self, file_path: str) -> LanguageExtractor | None:
        """Return the extractor for a file based on its extension, or None."""
        import os
        _, ext = os.path.splitext(file_path)
        return self._extractors.get(ext)

    def get_language(self, file_path: str) -> str | None:
        ext = self.get_extractor(file_path)
        return ext.language_name if ext else None

    def supported_extensions(self) -> list[str]:
        return list(self._extractors.keys())
