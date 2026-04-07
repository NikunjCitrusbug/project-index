"""TypeScript language extractor using tree-sitter."""

from __future__ import annotations

from typing import Any

from project_index.languages.base import LanguageExtractor
from project_index.languages.javascript_lang import JavaScriptExtractor, _node_text
from project_index.store.models import (
    NodeKind,
    RawImport,
    SymbolEntry,
)
from project_index.utils.logging import get_logger

logger = get_logger("languages.typescript")

_parser = None
_language = None


def _get_ts():
    global _parser, _language
    if _parser is not None:
        return _parser, _language
    try:
        import tree_sitter_typescript as tsts
        from tree_sitter import Language, Parser

        _language = Language(tsts.language_typescript())
        _parser = Parser(_language)
        return _parser, _language
    except Exception as exc:
        logger.warning("tree-sitter-typescript unavailable: %s", exc)
        return None, None


class TypeScriptExtractor(JavaScriptExtractor):
    """Extends JS extractor with TS-specific features."""

    @property
    def language_name(self) -> str:
        return "typescript"

    @property
    def extensions(self) -> list[str]:
        return [".ts", ".tsx"]

    def get_parser(self) -> Any:
        p, _ = _get_ts()
        return p

    def extract_symbols(
        self, source: bytes, file_path: str
    ) -> tuple[list[SymbolEntry], list[RawImport]]:
        parser, lang = _get_ts()
        if parser is None:
            return self._fallback_extract(source, file_path)

        tree = parser.parse(source)
        symbols: list[SymbolEntry] = []
        imports: list[RawImport] = []
        self._walk_ts(tree.root_node, source, file_path, "", "", symbols, imports)
        return symbols, imports

    def _walk_ts(self, node, source, file_path, parent_id, parent_qname, symbols, imports):
        for child in node.children:
            t = child.type
            if t == "function_declaration":
                self._handle_function(child, source, file_path, parent_id, parent_qname, symbols)
            elif t == "class_declaration":
                self._handle_class(child, source, file_path, parent_id, parent_qname, symbols, imports)
            elif t == "interface_declaration":
                self._handle_interface(child, source, file_path, parent_id, parent_qname, symbols)
            elif t == "type_alias_declaration":
                self._handle_type_alias(child, source, file_path, parent_id, parent_qname, symbols)
            elif t == "import_statement":
                self._handle_import(child, source, file_path, imports)
            elif t == "export_statement":
                for sub in child.children:
                    if sub.type == "function_declaration":
                        self._handle_function(sub, source, file_path, parent_id, parent_qname, symbols)
                    elif sub.type == "class_declaration":
                        self._handle_class(sub, source, file_path, parent_id, parent_qname, symbols, imports)
                    elif sub.type == "interface_declaration":
                        self._handle_interface(sub, source, file_path, parent_id, parent_qname, symbols)
                    elif sub.type == "type_alias_declaration":
                        self._handle_type_alias(sub, source, file_path, parent_id, parent_qname, symbols)
                    elif sub.type == "lexical_declaration":
                        self._handle_variable(sub, source, file_path, parent_id, parent_qname, symbols)
            elif t in ("lexical_declaration", "variable_declaration"):
                self._handle_variable(child, source, file_path, parent_id, parent_qname, symbols)

    def _handle_interface(self, node, source, file_path, parent_id, parent_qname, symbols):
        name_node = node.child_by_field_name("name")
        if not name_node:
            return
        name = _node_text(name_node, source)
        qname = f"{parent_qname}.{name}" if parent_qname else name
        sid = f"{file_path}::{qname}"
        symbols.append(SymbolEntry(
            symbol_id=sid, name=name, qualified_name=qname,
            kind=NodeKind.INTERFACE, file_path=file_path,
            line_start=node.start_point[0]+1, line_end=node.end_point[0]+1,
            byte_start=node.start_byte, byte_end=node.end_byte,
            signature=f"interface {name}", parent_id=parent_id,
        ))

    def _handle_type_alias(self, node, source, file_path, parent_id, parent_qname, symbols):
        name_node = node.child_by_field_name("name")
        if not name_node:
            return
        name = _node_text(name_node, source)
        qname = f"{parent_qname}.{name}" if parent_qname else name
        sid = f"{file_path}::{qname}"
        symbols.append(SymbolEntry(
            symbol_id=sid, name=name, qualified_name=qname,
            kind=NodeKind.TYPE_ALIAS, file_path=file_path,
            line_start=node.start_point[0]+1, line_end=node.end_point[0]+1,
            byte_start=node.start_byte, byte_end=node.end_byte,
            signature=f"type {name}", parent_id=parent_id,
        ))
