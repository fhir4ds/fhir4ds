"""Kernel: DuckDB connection + datasets + library registry, clean per launch."""

from __future__ import annotations

import itertools
import json
import threading
from pathlib import Path
from typing import Any

from fhir4ds.operations import evaluate_library, explain_patient, run_tests, translate_cql
from fhir4ds.operations.envelopes import LibraryText

from .discovery import WorkspaceSnapshot

_kernel_counter = itertools.count(1)


def _is_parameters_resource(path: Path) -> bool:
    """True when the JSON file is a lone FHIR Parameters resource."""
    try:
        with path.open("r", encoding="utf-8-sig") as f:
            doc = json.load(f)
    except (OSError, ValueError):
        return False
    return isinstance(doc, dict) and doc.get("resourceType") == "Parameters"


class Kernel:
    """One evaluation kernel: a DuckDB connection with datasets loaded.

    The server holds the current kernel behind a lock; ``restart`` builds
    a new kernel and swaps the pointer. In-flight calls keep a reference
    to the old kernel's connection and complete against it.
    """

    def __init__(self, datasets: list[Path], valuesets: list[Path]) -> None:
        self.kernel_id = f"kernel-{next(_kernel_counter)}"
        self.datasets = list(datasets)
        self.valuesets = list(valuesets)
        self.load_diagnostics: list[dict[str, Any]] = []
        # The DuckDB connection is NOT usable concurrently (a threaded
        # HTTP server shares it across request threads; overlapping
        # executes corrupted the interpreter — CPython aborted with
        # "unknown opcode"). Every connection touch is serialized here.
        self._op_lock = threading.RLock()
        self._conn = self._build_connection()

    @property
    def lock(self) -> threading.RLock:
        """The connection-operation lock (re-entrant)."""
        return self._op_lock

    class _Locked:
        """Context manager: hold the kernel's connection lock."""

        def __init__(self, kernel: "Kernel") -> None:
            self._kernel = kernel

        def __enter__(self) -> "Kernel":
            self._kernel._op_lock.acquire()
            return self._kernel

        def __exit__(self, *exc: Any) -> None:
            self._kernel._op_lock.release()

    def locked(self) -> "Kernel._Locked":
        return Kernel._Locked(self)

    # -- lifecycle ---------------------------------------------------------

    def _build_connection(self) -> Any:
        import fhir4ds

        conn = fhir4ds.create_connection()
        self.load_diagnostics = []
        if self.datasets or self.valuesets:
            from fhir4ds.operations import load_dataset
            from fhir4ds.operations.envelopes import DatasetSpec

            # QA-002 (12d hotfix): a workspace whose data dirs contain BOTH
            # .ndjson and .json files must boot. DatasetSpec enforces a
            # one-of shape over (resources, ndjson_paths, bundle_paths), so
            # group paths by suffix into SEPARATE specs / load_dataset
            # calls — each kind loads through its dedicated loader path.
            ndjson = [p for p in self.datasets if p.suffix.lower() == ".ndjson"]
            # S22d-1: type-layout workspaces hold LONE resource JSONs
            # (Patient/<id>/<id>.json etc.), not Bundles — separate them
            # from real Bundle files; lone resources load via the
            # resources list (same loader path as load_resources).
            bundles: list[Path] = []
            lone_resources: list[dict] = []
            for p in self.datasets:
                if p.suffix.lower() != ".json" or _is_parameters_resource(p):
                    continue
                try:
                    with open(p, "r", encoding="utf-8-sig") as fh:
                        payload = json.load(fh)
                except (OSError, json.JSONDecodeError):
                    bundles.append(p)  # let the loader surface the error
                    continue
                if isinstance(payload, dict) and payload.get("resourceType") == "Bundle":
                    bundles.append(p)
                elif isinstance(payload, dict) and isinstance(
                    payload.get("resourceType"), str
                ):
                    lone_resources.append(payload)
                else:
                    bundles.append(p)
            # S16: lone Parameters resources in data dirs are NOT datasets
            # (they feed _workspace_parameter_defaults); skip them from
            # bundle loading instead of failing the whole kernel boot.
            valuesets = [str(p) for p in self.valuesets] or None
            specs: list[DatasetSpec] = []
            if ndjson:
                specs.append(
                    DatasetSpec(
                        ndjson_paths=[str(p) for p in ndjson], valueset_paths=valuesets
                    )
                )
                valuesets = None  # load valuesets with exactly one spec
            if bundles:
                specs.append(
                    DatasetSpec(
                        bundle_paths=[str(p) for p in bundles], valueset_paths=valuesets
                    )
                )
                valuesets = None
            if lone_resources:
                specs.append(DatasetSpec(resources=lone_resources))
            if valuesets:  # valuesets only, no dataset files
                specs.append(DatasetSpec(valueset_paths=valuesets))
            for spec in specs:
                result = load_dataset(spec, conn)
                if not result.ok:
                    # Per-spec atomicity (QA-004): load_dataset rolls its
                    # own transaction back on failure, so a failed batch
                    # leaves the table in its pre-spec state. Rebuild a
                    # clean connection so the kernel never serves partial
                    # data across specs; diagnostics carry the reason.
                    self.load_diagnostics = [
                        d.to_dict() for d in result.diagnostics
                    ]
                    conn.close()
                    conn = fhir4ds.create_connection()
        return conn

    # -- evaluation --------------------------------------------------------

    @property
    def conn(self) -> Any:
        return self._conn

    def libraries_for(
        self, snapshot: WorkspaceSnapshot, main_name: str
    ) -> tuple[list[LibraryText], LibraryText]:
        """Build (includes, main) LibraryText lists from the snapshot."""
        main = snapshot.library(main_name)
        if main is None:
            raise KeyError(main_name)
        others = [lib.library_text() for lib in snapshot.libraries if lib.name != main_name]
        return others, main.library_text()

    def translate(
        self,
        includes: list[LibraryText],
        main: LibraryText,
        **kwargs: Any,
    ) -> dict[str, Any]:
        kwargs.pop("emit_sql", None)  # TranslateResult always carries sql
        with self._op_lock:
            result = translate_cql(includes, main, **kwargs)
        return result.to_dict()

    def evaluate(
        self,
        includes: list[LibraryText],
        main: LibraryText,
        **kwargs: Any,
    ) -> dict[str, Any]:
        with self._op_lock:
            result = evaluate_library(includes, main, None, self._conn, **kwargs)
        return result.to_dict()

    def verify(
        self,
        includes: list[LibraryText],
        main: LibraryText,
        cases: Any,
        **kwargs: Any,
    ) -> dict[str, Any]:
        with self._op_lock:
            result = run_tests(includes, main, None, cases, self._conn, **kwargs)
        return result.to_dict()

    def explain(
        self,
        includes: list[LibraryText],
        main: LibraryText,
        patient_id: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        with self._op_lock:
            result = explain_patient(
                includes, main, None, patient_id, self._conn, **kwargs
            )
        return result.to_dict()


class KernelManager:
    """Thread-safe current-kernel holder with restart."""

    def __init__(self, snapshot: WorkspaceSnapshot) -> None:
        self._lock = threading.Lock()
        self._kernel = Kernel(snapshot.datasets, snapshot.valuesets)
        # S27: retired kernels are kept FOREVER (never closed/GC-able) —
        # see restart(); bounded leak, one connection per restart.
        self._retired: list[Kernel] = []

    def current(self) -> Kernel:
        with self._lock:
            return self._kernel

    def restart(self, snapshot: WorkspaceSnapshot) -> Kernel:
        """Build a fresh kernel; in-flight work on the old one drains.

        S27: the old kernel is RETIRED, never closed and never GC-able —
        closing raced in-flight requests that had already fetched the
        old kernel (use-after-close SEGV), and dropping it for GC
        finalized the connection on an arbitrary thread (watcher-thread
        SEGV mid-lex). A retired in-memory connection per restart is a
        bounded, harmless leak in a dev server.
        """
        with self._lock:
            old = self._kernel
            new_kernel = Kernel(snapshot.datasets, snapshot.valuesets)
            self._kernel = new_kernel
            self._retired.append(old)
        return new_kernel
