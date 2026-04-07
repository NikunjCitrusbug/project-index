"""Core data models: enums and dataclasses for symbols, edges, imports."""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any


class NodeKind(str, enum.Enum):
    FILE = "file"
    MODULE = "module"
    CLASS = "class"
    FUNCTION = "function"
    METHOD = "method"
    VARIABLE = "variable"
    CONSTANT = "constant"
    INTERFACE = "interface"
    TYPE_ALIAS = "type_alias"
    STRUCT = "struct"
    PACKAGE = "package"
    ENUM = "enum"
    PROPERTY = "property"
    DECORATOR = "decorator"


class EdgeKind(str, enum.Enum):
    CONTAINS = "contains"
    IMPORTS = "imports"
    CALLS = "calls"
    INHERITS = "inherits"
    USES_TYPE = "uses_type"
    DECORATES = "decorates"
    EXPORTS = "exports"


class Visibility(str, enum.Enum):
    PUBLIC = "public"
    PRIVATE = "private"
    PROTECTED = "protected"
    INTERNAL = "internal"


@dataclass
class SymbolEntry:
    symbol_id: str
    name: str
    qualified_name: str
    kind: NodeKind
    file_path: str
    line_start: int
    line_end: int
    byte_start: int = 0
    byte_end: int = 0
    signature: str = ""
    docstring: str = ""
    parent_id: str = ""
    visibility: Visibility = Visibility.PUBLIC
    decorators: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class RawImport:
    module: str
    name: str
    alias: str = ""
    is_from: bool = True
    file_path: str = ""
    line: int = 0


@dataclass
class EdgeEntry:
    source_id: str
    target_id: str
    kind: EdgeKind
    target_resolved: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)
