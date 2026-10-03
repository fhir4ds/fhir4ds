"""Polling watcher + SSE event bus for workspace changes."""

from __future__ import annotations

import json
import queue
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from .config import DevServerConfig
from .discovery import WorkspaceSnapshot, scan_workspace

POLL_INTERVAL = 0.5  # seconds
DEBOUNCE = 0.25  # seconds per file


@dataclass
class WorkspaceEvent:
    """One watcher event pushed to SSE subscribers."""

    kind: str  # "changed" | "removed" | "data-hint"
    paths: list[str] = field(default_factory=list)
    snapshot: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "paths": self.paths, "workspace": self.snapshot}

    def sse(self) -> str:
        return f"data: {json.dumps(self.to_dict())}\n\n"


class EventBus:
    """Fan-out event queue registry for SSE subscribers."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._subs: list[queue.Queue[WorkspaceEvent]] = []

    def subscribe(self) -> "queue.Queue[WorkspaceEvent]":
        q: "queue.Queue[WorkspaceEvent]" = queue.Queue(maxsize=256)
        with self._lock:
            self._subs.append(q)
        return q

    def unsubscribe(self, q: "queue.Queue[WorkspaceEvent]") -> None:
        with self._lock:
            if q in self._subs:
                self._subs.remove(q)

    def publish(self, event: WorkspaceEvent) -> None:
        with self._lock:
            subs = list(self._subs)
        for q in subs:
            try:
                q.put_nowait(event)
            except queue.Full:  # pragma: no cover - slow client
                pass


def _snapshot_files(snap: WorkspaceSnapshot) -> set[str]:
    out = {str(lib.path) for lib in snap.libraries}
    out.update(str(p) for p in snap.valuesets)
    out.update(str(p) for p in snap.measures)
    out.update(str(p) for p in snap.datasets)
    return out


class Watcher:
    """Polling watcher over the workspace dirs.

    CQL/valueset/measure changes trigger a fresh workspace snapshot and a
    ``changed`` event. New/removed DATA files never auto-reload the
    kernel (locked decision): they emit a ``data-hint`` event so the UI
    can offer a restart.
    """

    def __init__(
        self,
        cfg: DevServerConfig,
        bus: EventBus,
        on_rescan: Callable[[WorkspaceSnapshot], None] | None = None,
    ) -> None:
        self._cfg = cfg
        self._bus = bus
        self.bus = bus  # public alias for API/SSE subscribers
        self._on_rescan = on_rescan
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.snapshot: WorkspaceSnapshot = scan_workspace(cfg)
        self._files = _snapshot_files(self.snapshot)
        self.files = self._files
        self._mtimes: dict[str, tuple[float, int]] = self._stat_all()

    # -- snapshots ---------------------------------------------------------

    def _stat_all(self) -> dict[str, tuple[float, int]]:
        out: dict[str, tuple[float, int]] = {}
        for path_str in self._files:
            try:
                st = Path(path_str).stat()
                out[path_str] = (st.st_mtime_ns / 1e9, st.st_size)
            except OSError:
                continue
        return out

    def rescan(self) -> WorkspaceSnapshot:
        """Take a fresh snapshot, diff, publish events; never raises."""
        try:
            snap = scan_workspace(self._cfg)
        except Exception:  # pragma: no cover - discovery guards internally
            return self.snapshot
        new_files = _snapshot_files(snap)
        old_files = self._files

        changed: list[str] = []
        for path_str in sorted(new_files - old_files):
            changed.append(path_str)
        for path_str in sorted(old_files - new_files):
            changed.append(path_str)
        for path_str in sorted(new_files & old_files):
            try:
                st = Path(path_str).stat()
                if (st.st_mtime_ns / 1e9, st.st_size) != self._mtimes.get(path_str):
                    changed.append(path_str)
            except OSError:
                changed.append(path_str)

        self.snapshot = snap
        self._files = new_files
        self.files = new_files
        self._mtimes = self._stat_all()

        if changed:
            data_dirs = {str(d) for d in self._cfg.data_dirs}
            data_changes = [
                p for p in changed if any(p.startswith(d) for d in data_dirs)
            ]
            code_changes = [p for p in changed if p not in set(data_changes)]
            if code_changes:
                self._bus.publish(
                    WorkspaceEvent(
                        kind="changed", paths=code_changes, snapshot=snap.to_dict()
                    )
                )
            if data_changes:
                # Locked decision 4: data changes NEVER auto-reload.
                self._bus.publish(
                    WorkspaceEvent(kind="data-hint", paths=data_changes)
                )
            if self._on_rescan is not None:
                try:
                    self._on_rescan(snap)
                except Exception:  # pragma: no cover - defensive
                    pass
        return snap

    # -- lifecycle ---------------------------------------------------------

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(
            target=self._run, name="devserver-watcher", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None

    def _run(self) -> None:
        while not self._stop.wait(POLL_INTERVAL):
            self.rescan()
