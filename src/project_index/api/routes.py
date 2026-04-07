from __future__ import annotations

from fastapi import APIRouter, Request, HTTPException

from project_index.api.schemas import (
    SearchRequest,
    SearchResponse,
    ContextRequest,
    ContextResponse,
    GraphRequest,
    GraphResponse,
    ReindexRequest,
    ReindexResponse,
    HealthResponse,
    ReadyResponse,
    StatsResponse,
    TreeResponse,
    TreeEntry,
    FileResponse,
)
from project_index.query.search import TrigramSearch
from project_index.query.context import ContextResolver
from project_index.query.graph import GraphQuery
from project_index.utils.logging import get_logger

logger = get_logger("api.routes")

router = APIRouter()


def _db(request: Request):
    return request.app.state.db


def _settings(request: Request):
    return request.app.state.settings


@router.get("/health")
def health() -> HealthResponse:
    return HealthResponse()


@router.get("/ready")
def ready(request: Request) -> ReadyResponse:
    db = _db(request)
    try:
        db.stats()
        return ReadyResponse(ready=True)
    except Exception:
        return ReadyResponse(ready=False)


@router.post("/search")
def search(body: SearchRequest, request: Request) -> SearchResponse:
    db = _db(request)
    searcher = TrigramSearch(db)
    results = searcher.search(body.query, limit=body.limit)
    return SearchResponse(results=results, total=len(results))


@router.post("/context")
def context(body: ContextRequest, request: Request) -> ContextResponse:
    db = _db(request)
    settings = _settings(request)
    resolver = ContextResolver(db, settings.project_root)
    result = resolver.resolve(
        body.symbol_id,
        token_budget=body.token_budget,
        max_depth=body.max_depth,
    )
    return ContextResponse(**result)


@router.get("/symbols")
def list_symbols(
    request: Request,
    kind: str | None = None,
    file_path: str | None = None,
    limit: int = 100,
) -> dict:
    db = _db(request)
    if file_path:
        symbols = db.get_symbols_for_file(file_path)
    elif kind:
        symbols = db.search_symbols("", kind=kind, limit=limit)
    else:
        symbols = db.get_all_symbols()[:limit]
    return {"symbols": symbols, "total": len(symbols)}


@router.get("/tree")
def tree(request: Request) -> TreeResponse:
    db = _db(request)
    files = db.get_all_files()
    entries = []
    for f in files:
        sym_count = len(db.get_symbols_for_file(f["file_path"]))
        entries.append(TreeEntry(
            path=f["file_path"],
            language=f.get("language"),
            symbols=sym_count,
        ))
    return TreeResponse(files=entries, total_files=len(entries))


@router.get("/file/{path:path}")
def get_file(path: str, request: Request) -> FileResponse:
    db = _db(request)
    file_info = db.get_file(path)
    if not file_info:
        raise HTTPException(status_code=404, detail=f"File not found: {path}")
    symbols = db.get_symbols_for_file(path)
    return FileResponse(
        file_path=path,
        language=file_info.get("language"),
        symbols=symbols,
    )


@router.post("/graph")
def graph(body: GraphRequest, request: Request) -> GraphResponse:
    db = _db(request)
    gq = GraphQuery(db)
    result = gq.subgraph(
        body.symbol_id,
        max_depth=body.max_depth,
        max_nodes=body.max_nodes,
    )
    return GraphResponse(**result)


@router.post("/reindex")
def reindex(request: Request) -> ReindexResponse:
    indexer = request.app.state.indexer
    result = indexer.full_index()
    return ReindexResponse(**result)


@router.get("/stats")
def stats(request: Request) -> StatsResponse:
    db = _db(request)
    s = db.stats()
    return StatsResponse(**s)
