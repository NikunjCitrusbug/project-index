from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from project_index.config import Settings
from project_index.store.database import Database
from project_index.indexer.core import Indexer
from project_index.watcher.handler import FileWatcher
from project_index.api.routes import router
from project_index.utils.logging import setup_logging, get_logger

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    settings: Settings = app.state.settings
    logger.info("Starting project-index server, project_root=%s", settings.project_root)

    # Ensure index directory exists
    settings.index_path.mkdir(parents=True, exist_ok=True)

    # Init DB
    db = Database(settings.index_db_path)

    # Run full index
    indexer = Indexer(settings, db)
    indexer.full_index()

    # Start file watcher
    watcher: FileWatcher | None = None
    if settings.watch_enabled:
        watcher = FileWatcher(settings, indexer)
        watcher.start()

    app.state.db = db
    app.state.indexer = indexer
    app.state.watcher = watcher

    yield

    # Shutdown
    if watcher:
        watcher.stop()
    db.close()
    logger.info("Server shut down.")


def create_app() -> FastAPI:
    settings = Settings()
    application = FastAPI(
        title="project-index",
        version="0.1.0",
        lifespan=lifespan,
    )
    application.state.settings = settings
    application.include_router(router)
    return application


app = create_app()
