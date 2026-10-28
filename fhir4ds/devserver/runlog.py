"""Run-history log (parity-build item 2, c-wasm-parity-build).

Append-only ``<workspace>/.runlog.jsonl`` with a 500-event / 256 KB cap
(oldest-third prune). Events capture debug-compare context: ts, kind,
target, status, duration, row_count, summary, params, library/sql SHAs
(no bodies), and the dataset context (dataset names + patient count) per
the conductor's addition. SQL bodies live in a CURRENT sql store only;
``sql_sha`` resolves against it and reports 'sql superseded' when stale.

Doctest-style usage:
    store = RunLogStore(Path(ws)); ev = store.record(kind="measure", ...)
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Optional

MAX_EVENTS = 500
MAX_BYTES = 256 * 1024
RUNLOG_NAME = ".runlog.jsonl"

_LOCK = threading.Lock()


def _sha(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


class RunLogStore:
    """Per-workspace run-history log (thread-safe, crash-tolerant).

    Corrupt/truncated trailing lines are skipped on load; the log is
    rewritten (pruned) only when a cap is exceeded, never on plain append.
    """

    def __init__(self, root: Path) -> None:
        self._root = Path(root)
        self._path = self._root / RUNLOG_NAME

    # -- read -------------------------------------------------------------

    def load(self, kind: Optional[str] = None, limit: int = 200) -> list[dict[str, Any]]:
        """Newest-first events; ``kind`` filters, ``limit`` caps."""
        events: list[dict[str, Any]] = []
        try:
            with self._path.open("r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        ev = json.loads(line)
                    except json.JSONDecodeError:
                        continue  # truncated tail from a crash mid-write
                    if not isinstance(ev, dict) or "id" not in ev:
                        continue
                    events.append(ev)
        except OSError:
            return []
        if kind:
            events = [e for e in events if e.get("kind") == kind]
        events.reverse()  # file is oldest-first
        return events[: max(1, limit)]

    # -- write ------------------------------------------------------------

    def record(
        self,
        *,
        kind: str,
        target: str,
        status: str,
        duration_ms: int,
        row_count: int,
        summary: Optional[dict[str, Any]] = None,
        params: Optional[dict[str, Any]] = None,
        library_text: Optional[str] = None,
        sql_text: Optional[str] = None,
        error: Optional[str] = None,
        datasets: Optional[list[str]] = None,
        patient_count: Optional[int] = None,
    ) -> dict[str, Any]:
        """Append one event; returns it. Enforces the cap (oldest-third prune)."""
        event: dict[str, Any] = {
            "id": f"evt-{int(time.time() * 1000)}-{uuid.uuid4().hex[:6]}",
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime())
            + f".{int(time.time() * 1000) % 1000:03d}Z",
            "kind": kind,
            "target": target,
            "status": status,
            "duration_ms": int(duration_ms),
            "row_count": int(row_count),
        }
        if summary is not None:
            event["summary"] = summary
        if params:
            event["params"] = params
        if library_text is not None:
            event["library_sha"] = _sha(library_text)
        if sql_text is not None:
            event["sql_sha"] = _sha(sql_text)
        if error:
            event["error"] = str(error)[:300]
        event["datasets"] = list(datasets or [])
        if patient_count is not None:
            event["patient_count"] = int(patient_count)
        with _LOCK:
            self._root.mkdir(parents=True, exist_ok=True)
            self._append(event)
            self._prune_if_needed()
        return event

    def clear(self) -> None:
        with _LOCK:
            try:
                self._path.unlink()
            except OSError:
                pass

    # -- internals ----------------------------------------------------------

    def _append(self, event: dict[str, Any]) -> None:
        with self._path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(event, separators=(",", ":")) + "\n")

    def _prune_if_needed(self) -> None:
        try:
            size = self._path.stat().st_size
            lines = [ln for ln in self._path.read_text(encoding="utf-8").splitlines() if ln.strip()]
        except OSError:
            return
        if len(lines) <= MAX_EVENTS and size <= MAX_BYTES:
            return
        keep = lines[(len(lines) + 2) // 3:]  # drop the oldest third
        tmp = self._path.with_suffix(".prune.tmp")
        tmp.write_text("\n".join(keep) + ("\n" if keep else ""), encoding="utf-8")
        tmp.replace(self._path)
