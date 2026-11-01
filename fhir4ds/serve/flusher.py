"""Buffered publication: the flush loop that turns writes into dataset commits.

A write never waits for the Hub. It lands in the local log (so reads see it),
and its publish row is buffered here; a background tick flushes every
``interval`` seconds or as soon as ``batch_size`` rows are waiting, and
``POST /admin/flush`` forces one synchronously.

Failure policy (the brief's): one ``create_commit`` per flush, retry once on a
``parent_commit`` conflict inside the store, and on any remaining failure keep
the buffer, record the error on ``/health`` and try again on the next tick. Rows
keep their assigned ``_seq`` across retries, so a retry can never renumber a
version.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any

from . import bulk_publish
from .store import PublishStore

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FlushResult:
    """Outcome of one flush attempt."""

    revision: str
    committed: int


class FlushManager:
    """Owns the pending-write buffer and the publication cadence."""

    def __init__(
        self,
        store: PublishStore,
        *,
        interval: float = 30.0,
        batch_size: int = 50,
        publisher: str = bulk_publish.DEFAULT_PUBLISHER,
        repository: str | None = None,
        request_url: str = "/$bulk-publish",
        definition_provider: Callable[[], Iterable[dict]] | None = None,
        autostart: bool = True,
    ) -> None:
        self._store = store
        self._interval = max(0.0, float(interval))
        self._batch_size = max(1, int(batch_size))
        self._publisher = publisher
        self._repository = repository
        self._request_url = request_url
        self._definition_provider = definition_provider

        self._buffer: list[dict[str, Any]] = []
        self._buffer_lock = threading.Lock()

        self.last_commit: str | None = store.revision() or None
        self.last_commit_at: str | None = None
        self.last_error: str | None = None

        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        if autostart:
            self.start()

    # -- buffer ----------------------------------------------------------

    def enqueue(self, rows: Iterable[dict[str, Any]]) -> None:
        """Buffer publish rows (called from request threads)."""
        materialized = [dict(row) for row in rows]
        if not materialized:
            return
        with self._buffer_lock:
            self._buffer.extend(materialized)

    def pending(self) -> int:
        with self._buffer_lock:
            return len(self._buffer)

    def health(self) -> dict[str, Any]:
        """The publication part of ``GET /health``."""
        return {
            "pending": self.pending(),
            "last_commit": self.last_commit,
            "last_commit_at": self.last_commit_at,
            "last_error": self.last_error,
        }

    # -- cadence ---------------------------------------------------------

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run, name="fhir4ds-flush", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=5)
        self._thread = None

    def _run(self) -> None:
        while not self._stop.wait(self._interval):
            try:
                if self.pending():
                    self.flush(force=False)
            except Exception:  # noqa: BLE001 - the loop must survive one bad flush
                logger.exception("flush tick failed")

    # -- flush -----------------------------------------------------------

    def flush(self, *, force: bool = True) -> FlushResult:
        """Publish buffered rows. ``force`` takes the whole buffer, else one batch."""
        with self._buffer_lock:
            if not self._buffer:
                return self._retry_pending()
            if force:
                rows = self._buffer
                self._buffer = []
            else:
                rows = self._buffer[: self._batch_size]
                del self._buffer[: len(rows)]

        try:
            revision = self._publish(rows)
        except Exception as exc:  # noqa: BLE001 - keep the buffer, report the error
            self._handle_failure(rows, exc)
            return FlushResult(self._store.revision(), 0)

        self.last_commit = revision
        self.last_commit_at = bulk_publish.utc_timestamp()
        self.last_error = None
        return FlushResult(revision, len(rows))

    def _retry_pending(self) -> FlushResult:
        """Retry publishing files a failed flush committed but could not push."""
        if not self._store.pending_files():
            return FlushResult(self._store.revision(), 0)
        try:
            revision = self._store.retry_publish()
        except Exception as exc:  # noqa: BLE001 - keep the error visible on /health
            self.last_error = f"{type(exc).__name__}: {exc}"
            logger.warning("publish retry failed: %s", exc)
            return FlushResult(self._store.revision(), 0)
        self.last_commit = revision
        self.last_commit_at = bulk_publish.utc_timestamp()
        self.last_error = None
        return FlushResult(revision, 0)

    def _handle_failure(self, rows: list[dict[str, Any]], exc: Exception) -> None:
        """Record a flush failure, re-buffering only rows NOT already committed.

        A store whose local commit succeeded (part + state written, upload
        failed) already holds these rows: re-buffering them would write them
        into a second part and double-publish. Such rows stay committed locally
        and only the upload is retried (``_retry_pending``).
        """
        self.last_error = f"{type(exc).__name__}: {exc}"
        highest = max(int(row["_seq"]) for row in rows)
        if self._store.current_seq() >= highest:
            logger.warning(
                "flush failed after the local commit (%d row(s) committed, "
                "upload pending): %s",
                len(rows),
                exc,
            )
            return
        with self._buffer_lock:
            self._buffer[:0] = rows
        logger.warning("flush failed, %d row(s) kept: %s", len(rows), exc)

    def _publish(self, rows: list[dict[str, Any]]) -> str:
        self._store.append(rows)
        highest = max(int(row["_seq"]) for row in rows)
        definitions = (
            bulk_publish.definition_files(self._definition_provider())
            if self._definition_provider is not None
            else {}
        )
        files = bulk_publish.dataset_files(
            repository=self._repository,
            root=self._store.snapshot(),
            publisher=self._publisher,
            request_url=self._request_url,
            pending_part=bulk_publish.plan_part_path(highest),
            definitions=definitions,
        )
        for relative_path, text in files.items():
            self._store.stage_file(relative_path, text)
        return self._store.commit()

    # -- manifests -------------------------------------------------------

    def manifest(self, base_url: str) -> dict[str, Any]:
        """Live ``$bulk-publish`` document for the store's current tree."""
        return bulk_publish.build_manifest(
            repository=self._repository,
            root=self._store.snapshot(),
            request_url=f"{base_url}/$bulk-publish",
        )


__all__ = ["FlushManager", "FlushResult"]
