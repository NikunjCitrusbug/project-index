"""JavaScript language extractor using tree-sitter."""

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

logger = get_logger("languages.javascript")

_parser = None
_language = None


def _get_ts():
    global _parser, _language
    if _parser is not None:
        return _parser, _language
    try:
        import tree_sitter_javascript as tsjs
        from tree_sitter import Language, Parser

        _language = Language(tsjs.language())
        _parser = Parser(_language)
        return _parser, _language
    except Exception as exc:
        logger.warning("tree-sitter-javascript unavailable: %s", exc)
        return None, None


def _node_text(node, source: bytes) -> str:
    return source[node.start_byte : node.end_byte].decode("utf-8", errors="replace")


class JavaScriptExtractor(LanguageExtractor):
    @property
    def language_name(self) -> str:
        return "javascript"

    @property
    def extensions(self) -> list[str]:
        return [".js", ".jsx", ".mjs", ".cjs"]

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
        self._walk(tree.root_node, source, file_path, "", "", symbols, imports)
        return symbols, imports

    def _walk(self, node, source, file_path, parent_id, parent_qname, symbols, imports):
        for child in node.children:
            t = child.type
            if t == "function_declaration":
                self._handle_function(child, source, file_path, parent_id, parent_qname, symbols)
            elif t == "class_declaration":
                self._handle_class(child, source, file_path, parent_id, parent_qname, symbols, imports)
            elif t == "import_statement":
                self._handle_import(child, source, file_path, imports)
            elif t == "export_statement":
                for sub in child.children:
                    if sub.type == "function_declaration":
                        self._handle_function(sub, source, file_path, parent_id, parent_qname, symbols)
                    elif sub.type == "class_declaration":
                        self._handle_class(sub, source, file_path, parent_id, parent_qname, symbols, imports)
                    elif sub.type == "lexical_declaration":
                        self._handle_variable(sub, source, file_path, parent_id, parent_qname, symbols)
            elif t == "lexical_declaration" or t == "variable_declaration":
                self._handle_variable(child, source, file_path, parent_id, parent_qname, symbols)

    def _handle_function(self, node, source, file_path, parent_id, parent_qname, symbols):
        name_node = node.child_by_field_name("name")
        if not name_node:
            return
        name = _node_text(name_node, source)
        qname = f"{parent_qname}.{name}" if parent_qname else name
        sid = f"{file_path}::{qname}"
        params = node.child_by_field_name("parameters")
        sig = f"function {name}"
        if params:
            sig += _node_text(params, source)
        symbols.append(SymbolEntry(
            symbol_id=sid, name=name, qualified_name=qname,
            kind=NodeKind.FUNCTION, file_path=file_path,
            line_start=node.start_point[0]+1, line_end=node.end_point[0]+1,
            byte_start=node.start_byte, byte_end=node.end_byte,
            signature=sig, parent_id=parent_id,
        ))

    def _handle_class(self, node, source, file_path, parent_id, parent_qname, symbols, imports):
        name_node = node.child_by_field_name("name")
        if not name_node:
            return
        name = _node_text(name_node, source)
        qname = f"{parent_qname}.{name}" if parent_qname else name
        sid = f"{file_path}::{qname}"
        sig = f"class {name}"
        heritage = node.child_by_field_name("heritage")
        if heritage:
            sig += f" {_node_text(heritage, source)}"
        symbols.append(SymbolEntry(
            symbol_id=sid, name=name, qualified_name=qname,
            kind=NodeKind.CLASS, file_path=file_path,
            line_start=node.start_point[0]+1, line_end=node.end_point[0]+1,
            byte_start=node.start_byte, byte_end=node.end_byte,
            signature=sig, parent_id=parent_id,
        ))
        body = node.child_by_field_name("body")
        if body:
            for child in body.children:
                if child.type == "method_definition":
                    mname_node = child.child_by_field_name("name")
                    if mname_node:
                        mname = _node_text(mname_node, source)
                        mqname = f"{qname}.{mname}"
                        msid = f"{file_path}::{mqname}"
                        params = child.child_by_field_name("parameters")
                        msig = f"{mname}"
                        if params:
                            msig += _node_text(params, source)
                        symbols.append(SymbolEntry(
                            symbol_id=msid, name=mname, qualified_name=mqname,
                            kind=NodeKind.METHOD, file_path=file_path,
                            line_start=child.start_point[0]+1, line_end=child.end_point[0]+1,
                            byte_start=child.start_byte, byte_end=child.end_byte,
                            signature=msig, parent_id=sid,
                        ))

    def _handle_variable(self, node, source, file_path, parent_id, parent_qname, symbols):
        for child in node.children:
            if child.type == "variable_declarator":
                name_node = child.child_by_field_name("name")
                if name_node and name_node.type == "identifier":
                    name = _node_text(name_node, source)
                    qname = f"{parent_qname}.{name}" if parent_qname else name
                    sid = f"{file_path}::{qname}"
                    symbols.append(SymbolEntry(
                        symbol_id=sid, name=name, qualified_name=qname,
                        kind=NodeKind.VARIABLE, file_path=file_path,
                        line_start=node.start_point[0]+1, line_end=node.end_point[0]+1,
                        byte_start=node.start_byte, byte_end=node.end_byte,
                        parent_id=parent_id,
                    ))

    def _handle_import(self, node, source, file_path, imports):
        src_node = node.child_by_field_name("source")
        if not src_node:
            return
        mod = _node_text(src_node, source).strip("'\"")
        for child in node.children:
            if child.type == "import_clause":
                for sub in child.children:
                    if sub.type == "identifier":
                        imports.append(RawImport(module=mod, name=_node_text(sub, source), file_path=file_path, line=node.start_point[0]+1))
                    elif sub.type == "named_imports":
                        for spec in sub.children:
                            if spec.type == "import_specifier":
                                name_node = spec.child_by_field_name("name")
                                alias_node = spec.child_by_field_name("alias")
                                if name_node:
                                    n = _node_text(name_node, source)
                                    a = _node_text(alias_node, source) if alias_node else ""
                                    imports.append(RawImport(module=mod, name=n, alias=a, file_path=file_path, line=node.start_point[0]+1))

    def _fallback_extract(self, source, file_path):
        symbols = []
        lines = source.decode("utf-8", errors="replace").splitlines()
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if stripped.startswith("function "):
                name = stripped[9:].split("(")[0].strip()
                if name:
                    sid = f"{file_path}::{name}"
                    symbols.append(SymbolEntry(
                        symbol_id=sid, name=name, qualified_name=name,
                        kind=NodeKind.FUNCTION, file_path=file_path,
                        line_start=i, line_end=i,
                    ))
            elif stripped.startswith("class "):
                name = stripped[6:].split("{")[0].split("(")[0].strip()
                if name:
                    sid = f"{file_path}::{name}"
                    symbols.append(SymbolEntry(
                        symbol_id=sid, name=name, qualified_name=name,
                        kind=NodeKind.CLASS, file_path=file_path,
                        line_start=i, line_end=i,
                    ))
        return symbols, []
