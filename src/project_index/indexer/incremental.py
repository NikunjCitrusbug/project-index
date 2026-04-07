from __future__ import annotations

from project_index.indexer.core import Indexer
from project_index.utils.logging import get_logger

logger = get_logger("indexer.incremental")


class IncrementalIndexer:
    """Re-index a single file: delete old data, re-parse, re-resolve."""

    def __init__(self, indexer: Indexer) -> None:
        self.indexer = indexer

    def on_file_changed(self, abs_path: str) -> None:
        """Called when a file is created or modified."""
        try:
            count = self.indexer.reindex_file(abs_path)
            if count > 0:
                logger.info("Re-indexed %s: %d symbols", abs_path, count)
        except Exception as exc:
            logger.warning("Failed to re-index %s: %s", abs_path, exc)

    def on_file_deleted(self, abs_path: str) -> None:
        """Called when a file is deleted."""
        try:
            self.indexer.reindex_file(abs_path)
            logger.info("Removed index data for deleted file %s", abs_path)
        except Exception as exc:
            logger.warning("Failed to clean up %s: %s", abs_path, exc)
