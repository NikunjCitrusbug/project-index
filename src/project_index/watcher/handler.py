from __future__ import annotations

import threading
import time

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileSystemEvent

from project_index.indexer.core import Indexer
from project_index.config import Settings
from project_index.utils.logging import get_logger

logger = get_logger("watcher.handler")


class _DebouncedHandler(FileSystemEventHandler):
    """Debounce file system events and trigger re-indexing."""

    def __init__(self, indexer: Indexer, debounce_seconds: float) -> None:
        super().__init__()
        self.indexer = indexer
        self.debounce_seconds = debounce_seconds
        self._pending: dict[str, float] = {}
        self._lock = threading.Lock()
        self._timer: threading.Timer | None = None

    def on_any_event(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return
        src = getattr(event, "src_path", None)
        if not src:
            return

        with self._lock:
            self._pending[src] = time.time()

        # Reset debounce timer
        if self._timer:
            self._timer.cancel()
        self._timer = threading.Timer(self.debounce_seconds, self._flush)
        self._timer.daemon = True
        self._timer.start()

    def _flush(self) -> None:
        with self._lock:
            paths = list(self._pending.keys())
            self._pending.clear()

        for path in paths:
            try:
                self.indexer.reindex_file(path)
            except Exception as exc:
                logger.warning("Error re-indexing %s: %s", path, exc)


class FileWatcher:
    """Watch project directory for changes and trigger incremental re-index."""

    def __init__(self, settings: Settings, indexer: Indexer) -> None:
        self.settings = settings
        self.indexer = indexer
        self._observer: Observer | None = None

    def start(self) -> None:
        debounce_s = self.settings.watch_debounce_ms / 1000.0
        handler = _DebouncedHandler(self.indexer, debounce_s)
        self._observer = Observer()
        self._observer.schedule(handler, self.settings.project_root, recursive=True)
        self._observer.daemon = True
        self._observer.start()
        logger.info("File watcher started for %s", self.settings.project_root)

    def stop(self) -> None:
        if self._observer:
            self._observer.stop()
            self._observer.join(timeout=5)
            logger.info("File watcher stopped")
