from __future__ import annotations

from typing import Any

from project_index.languages.base import LanguageExtractor
from project_index.store.models import (
    NodeKind,
    RawImport,
    SymbolEntry,
    Visibility,
)
from project_index.utils.logging import get_logger

logger = get_logger("languages.go")

_parser = None
_language = None


def _get_ts():
    global _parser, _language
    if _parser is not None:
        return _parser, _language
    try:
        import tree_sitter_go as tsgo
        from tree_sitter import Language, Parser

        _language = Language(tsgo.language())
        _parser = Parser(_language)
        return _parser, _language
    except Exception as exc:
        logger.warning("tree-sitter-go unavailable: %s", exc)
        return None, None


def _node_text(node, source: bytes) -> str:
    return source[node.start_byte : node.end_byte].decode("utf-8", errors="replace")


class GoExtractor(LanguageExtractor):
    @property
    def language_name(self) -> str:
        return "go"

    @property
    def extensions(self) -> list[str]:
        return [".go"]

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
        self._walk(tree.root_node, source, file_path, symbols, imports)
        return symbols, imports

    def _walk(self, node, source, file_path, symbols, imports):
        for child in node.children:
            t = child.type
            if t == "function_declaration":
                name_node = child.child_by_field_name("name")
                if name_node:
                    name = _node_text(name_node, source)
                    sid = f"{file_path}::{name}"
                    params = child.child_by_field_name("parameters")
                    sig = f"func {name}"
                    if params:
                        sig += _node_text(params, source)
                    vis = Visibility.PUBLIC if name[0].isupper() else Visibility.PRIVATE
                    symbols.append(SymbolEntry(
                        symbol_id=sid, name=name, qualified_name=name,
                        kind=NodeKind.FUNCTION, file_path=file_path,
                        line_start=child.start_point[0] + 1,
                        line_end=child.end_point[0] + 1,
                        byte_start=child.start_byte, byte_end=child.end_byte,
                        signature=sig, visibility=vis,
                    ))
            elif t == "method_declaration":
                name_node = child.child_by_field_name("name")
                if name_node:
                    name = _node_text(name_node, source)
                    sid = f"{file_path}::{name}"
                    sig = f"func {name}"
                    symbols.append(SymbolEntry(
                        symbol_id=sid, name=name, qualified_name=name,
                        kind=NodeKind.METHOD, file_path=file_path,
                        line_start=child.start_point[0] + 1,
                        line_end=child.end_point[0] + 1,
                        byte_start=child.start_byte, byte_end=child.end_byte,
                        signature=sig,
                    ))
            elif t == "type_declaration":
                for spec in child.children:
                    if spec.type == "type_spec":
                        tname = spec.child_by_field_name("name")
                        if tname:
                            name = _node_text(tname, source)
                            sid = f"{file_path}::{name}"
                            kind = NodeKind.STRUCT
                            ttype = spec.child_by_field_name("type")
                            if ttype and ttype.type == "interface_type":
                                kind = NodeKind.INTERFACE
                            symbols.append(SymbolEntry(
                                symbol_id=sid, name=name, qualified_name=name,
                                kind=kind, file_path=file_path,
                                line_start=spec.start_point[0] + 1,
                                line_end=spec.end_point[0] + 1,
                                byte_start=spec.start_byte, byte_end=spec.end_byte,
                                signature=f"type {name}",
                            ))
            elif t == "import_declaration":
                for spec in child.children:
                    if spec.type == "import_spec":
                        path_node = spec.child_by_field_name("path")
                        if path_node:
                            mod = _node_text(path_node, source).strip('"')
                            imports.append(RawImport(
                                module=mod, name=mod.split("/")[-1],
                                file_path=file_path, line=spec.start_point[0] + 1,
                            ))
                    elif spec.type == "import_spec_list":
                        for sub in spec.children:
                            if sub.type == "import_spec":
                                path_node = sub.child_by_field_name("path")
                                if path_node:
                                    mod = _node_text(path_node, source).strip('"')
                                    imports.append(RawImport(
                                        module=mod, name=mod.split("/")[-1],
                                        file_path=file_path, line=sub.start_point[0] + 1,
                                    ))

    def _fallback_extract(self, source, file_path):
        symbols = []
        lines = source.decode("utf-8", errors="replace").splitlines()
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if stripped.startswith("func "):
                parts = stripped[5:].split("(")
                name = parts[0].strip()
                if name:
                    sid = f"{file_path}::{name}"
                    symbols.append(SymbolEntry(
                        symbol_id=sid, name=name, qualified_name=name,
                        kind=NodeKind.FUNCTION, file_path=file_path,
                        line_start=i, line_end=i,
                    ))
            elif stripped.startswith("type ") and ("struct" in stripped or "interface" in stripped):
                name = stripped.split()[1] if len(stripped.split()) > 1 else ""
                if name:
                    sid = f"{file_path}::{name}"
                    kind = NodeKind.INTERFACE if "interface" in stripped else NodeKind.STRUCT
                    symbols.append(SymbolEntry(
                        symbol_id=sid, name=name, qualified_name=name,
                        kind=kind, file_path=file_path,
                        line_start=i, line_end=i,
                    ))
        return symbols, []
