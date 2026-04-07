"""Python language extractor using tree-sitter."""

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

logger = get_logger("languages.python")

_parser = None
_language = None


def _get_ts():
    global _parser, _language
    if _parser is not None:
        return _parser, _language
    try:
        import tree_sitter_python as tspython
        from tree_sitter import Language, Parser

        _language = Language(tspython.language())
        _parser = Parser(_language)
        return _parser, _language
    except Exception as exc:
        logger.warning("tree-sitter-python unavailable: %s", exc)
        return None, None


def _node_text(node, source: bytes) -> str:
    return source[node.start_byte : node.end_byte].decode("utf-8", errors="replace")


def _extract_docstring(body_node, source: bytes) -> str:
    """Extract docstring from the first statement if it's a string expression."""
    if body_node is None:
        return ""
    for child in body_node.children:
        if child.type == "expression_statement":
            for sub in child.children:
                if sub.type == "string":
                    raw = _node_text(sub, source)
                    # Strip triple quotes
                    for q in ('"""', "'''", '"', "'"):
                        if raw.startswith(q) and raw.endswith(q):
                            return raw[len(q) : -len(q)].strip()
                    return raw
            break
        elif child.type == "comment":
            continue
        else:
            break
    return ""


class PythonExtractor(LanguageExtractor):
    @property
    def language_name(self) -> str:
        return "python"

    @property
    def extensions(self) -> list[str]:
        return [".py", ".pyi"]

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

    def _walk(
        self,
        node,
        source: bytes,
        file_path: str,
        parent_id: str,
        parent_qname: str,
        symbols: list[SymbolEntry],
        imports: list[RawImport],
    ) -> None:
        for child in node.children:
            if child.type == "function_definition":
                self._handle_function(child, source, file_path, parent_id, parent_qname, symbols, imports)
            elif child.type == "class_definition":
                self._handle_class(child, source, file_path, parent_id, parent_qname, symbols, imports)
            elif child.type == "import_statement":
                self._handle_import(child, source, file_path, imports)
            elif child.type == "import_from_statement":
                self._handle_from_import(child, source, file_path, imports)
            elif child.type == "decorated_definition":
                # Process the actual definition inside
                for sub in child.children:
                    if sub.type in ("function_definition", "class_definition"):
                        decorators = [
                            _node_text(d, source)
                            for d in child.children
                            if d.type == "decorator"
                        ]
                        if sub.type == "function_definition":
                            self._handle_function(
                                sub, source, file_path, parent_id, parent_qname,
                                symbols, imports, decorators=decorators
                            )
                        else:
                            self._handle_class(
                                sub, source, file_path, parent_id, parent_qname,
                                symbols, imports, decorators=decorators
                            )

    def _handle_function(
        self,
        node,
        source: bytes,
        file_path: str,
        parent_id: str,
        parent_qname: str,
        symbols: list[SymbolEntry],
        imports: list[RawImport],
        decorators: list[str] | None = None,
    ) -> None:
        name_node = node.child_by_field_name("name")
        if name_node is None:
            return
        name = _node_text(name_node, source)

        qname = f"{parent_qname}.{name}" if parent_qname else name
        sid = f"{file_path}::{qname}"

        is_method = parent_id and any(
            s.kind == NodeKind.CLASS for s in symbols if s.symbol_id == parent_id
        )
        kind = NodeKind.METHOD if is_method else NodeKind.FUNCTION

        # Signature
        params_node = node.child_by_field_name("parameters")
        ret_node = node.child_by_field_name("return_type")
        sig = f"def {name}"
        if params_node:
            sig += _node_text(params_node, source)
        if ret_node:
            sig += f" -> {_node_text(ret_node, source)}"

        # Docstring
        body = node.child_by_field_name("body")
        docstring = _extract_docstring(body, source) if body else ""

        visibility = Visibility.PRIVATE if name.startswith("_") else Visibility.PUBLIC

        symbols.append(
            SymbolEntry(
                symbol_id=sid,
                name=name,
                qualified_name=qname,
                kind=kind,
                file_path=file_path,
                line_start=node.start_point[0] + 1,
                line_end=node.end_point[0] + 1,
                byte_start=node.start_byte,
                byte_end=node.end_byte,
                signature=sig,
                docstring=docstring,
                parent_id=parent_id,
                visibility=visibility,
                decorators=decorators or [],
            )
        )

    def _handle_class(
        self,
        node,
        source: bytes,
        file_path: str,
        parent_id: str,
        parent_qname: str,
        symbols: list[SymbolEntry],
        imports: list[RawImport],
        decorators: list[str] | None = None,
    ) -> None:
        name_node = node.child_by_field_name("name")
        if name_node is None:
            return
        name = _node_text(name_node, source)

        qname = f"{parent_qname}.{name}" if parent_qname else name
        sid = f"{file_path}::{qname}"

        # Signature with bases
        bases_node = node.child_by_field_name("superclasses")
        sig = f"class {name}"
        if bases_node:
            sig += _node_text(bases_node, source)

        body = node.child_by_field_name("body")
        docstring = _extract_docstring(body, source) if body else ""

        symbols.append(
            SymbolEntry(
                symbol_id=sid,
                name=name,
                qualified_name=qname,
                kind=NodeKind.CLASS,
                file_path=file_path,
                line_start=node.start_point[0] + 1,
                line_end=node.end_point[0] + 1,
                byte_start=node.start_byte,
                byte_end=node.end_byte,
                signature=sig,
                docstring=docstring,
                parent_id=parent_id,
                visibility=Visibility.PUBLIC,
                decorators=decorators or [],
            )
        )

        # Recurse into class body for methods
        if body:
            self._walk(body, source, file_path, sid, qname, symbols, imports)

    def _handle_import(self, node, source: bytes, file_path: str, imports: list[RawImport]) -> None:
        for child in node.children:
            if child.type == "dotted_name":
                mod = _node_text(child, source)
                imports.append(RawImport(module=mod, name=mod, is_from=False, file_path=file_path, line=node.start_point[0] + 1))
            elif child.type == "aliased_import":
                parts = [_node_text(c, source) for c in child.children if c.type == "dotted_name" or c.type == "identifier"]
                mod = parts[0] if parts else ""
                alias = parts[-1] if len(parts) > 1 else ""
                imports.append(RawImport(module=mod, name=mod, alias=alias, is_from=False, file_path=file_path, line=node.start_point[0] + 1))

    def _handle_from_import(self, node, source: bytes, file_path: str, imports: list[RawImport]) -> None:
        mod = ""
        names: list[tuple[str, str]] = []
        for child in node.children:
            if child.type == "dotted_name" and not mod:
                mod = _node_text(child, source)
            elif child.type == "relative_import":
                mod = _node_text(child, source)
            elif child.type == "dotted_name" and mod:
                names.append((_node_text(child, source), ""))
            elif child.type == "identifier" and child != node.children[0]:
                names.append((_node_text(child, source), ""))
            elif child.type == "aliased_import":
                parts = [_node_text(c, source) for c in child.children if c.type in ("dotted_name", "identifier")]
                n = parts[0] if parts else ""
                a = parts[-1] if len(parts) > 1 else ""
                names.append((n, a))
            elif child.type == "import_prefix":
                mod = _node_text(child, source)

        for n, a in names:
            imports.append(RawImport(module=mod, name=n, alias=a, is_from=True, file_path=file_path, line=node.start_point[0] + 1))
        if not names and mod:
            imports.append(RawImport(module=mod, name="*", is_from=True, file_path=file_path, line=node.start_point[0] + 1))

    def _fallback_extract(
        self, source: bytes, file_path: str
    ) -> tuple[list[SymbolEntry], list[RawImport]]:
        """Very basic regex-less fallback when tree-sitter is unavailable."""
        symbols: list[SymbolEntry] = []
        imports: list[RawImport] = []
        lines = source.decode("utf-8", errors="replace").splitlines()
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if stripped.startswith("def "):
                name = stripped[4:].split("(")[0].strip()
                if name:
                    sid = f"{file_path}::{name}"
                    symbols.append(
                        SymbolEntry(
                            symbol_id=sid, name=name, qualified_name=name,
                            kind=NodeKind.FUNCTION, file_path=file_path,
                            line_start=i, line_end=i, signature=stripped.rstrip(":"),
                        )
                    )
            elif stripped.startswith("class "):
                name = stripped[6:].split("(")[0].split(":")[0].strip()
                if name:
                    sid = f"{file_path}::{name}"
                    symbols.append(
                        SymbolEntry(
                            symbol_id=sid, name=name, qualified_name=name,
                            kind=NodeKind.CLASS, file_path=file_path,
                            line_start=i, line_end=i, signature=stripped.rstrip(":"),
                        )
                    )
        return symbols, imports
