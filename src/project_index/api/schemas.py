from __future__ import annotations

from typing import Any, List, Optional

from pydantic import BaseModel, Field

from project_index import __version__


# ── Request models ──────────────────────────────────────────────────

class SearchRequest(BaseModel):
    query: str
    kind: Optional[str] = None
    limit: int = Field(default=20, ge=1, le=200)


class ContextRequest(BaseModel):
    symbol_id: str
    token_budget: int = Field(default=8000, ge=100, le=100000)
    max_depth: int = Field(default=3, ge=1, le=10)


class GraphRequest(BaseModel):
    symbol_id: str
    max_depth: int = Field(default=2, ge=1, le=5)
    max_nodes: int = Field(default=50, ge=1, le=500)


class ReindexRequest(BaseModel):
    full: bool = True


# ── Response models ─────────────────────────────────────────────────

class HealthResponse(BaseModel):
    status: str = "ok"
    version: str = __version__


class ReadyResponse(BaseModel):
    ready: bool = True


class StatsResponse(BaseModel):
    files: int = 0
    symbols: int = 0
    edges: int = 0
    trigrams: int = 0


class SymbolResponse(BaseModel):
    symbol_id: str
    name: str
    qualified_name: str
    kind: str
    file_path: str
    line_start: int
    line_end: int
    signature: str = ""
    docstring: str = ""
    visibility: str = "public"


class SearchResponse(BaseModel):
    results: List[dict] = []
    total: int = 0


class ContextResponse(BaseModel):
    symbol: Optional[dict] = None
    context: List[dict] = []
    tokens_used: int = 0


class GraphResponse(BaseModel):
    nodes: List[dict] = []
    edges: List[dict] = []


class TreeEntry(BaseModel):
    path: str
    language: Optional[str] = None
    symbols: int = 0


class TreeResponse(BaseModel):
    files: List[TreeEntry] = []
    total_files: int = 0


class FileResponse(BaseModel):
    file_path: str
    language: Optional[str] = None
    symbols: List[dict] = []


class ReindexResponse(BaseModel):
    files_indexed: int = 0
    symbols: int = 0
    errors: int = 0
    elapsed_seconds: float = 0.0
