"""Kernel: DuckDB connection + datasets + library registry, clean per launch."""

from __future__ import annotations

import itertools
import threading
from pathlib import Path
from typing import Any

from fhir4ds.operations import evaluate_library, explain_patient, run_tests, translate_cql
from fhir4ds.operations.envelopes import LibraryText

from .discovery import WorkspaceSnapshot

_kernel_counter = itertools.count(1)


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
        self._conn = self._build_connection()

    # -- lifecycle ---------------------------------------------------------

    def _build_connection(self) -> Any:
        import fhir4ds

        conn = fhir4ds.create_connection()
        self.load_diagnostics = []
        if self.datasets or self.valuesets:
            from fhir4ds.operations import load_dataset
            from fhir4ds.operations.envelopes import DatasetSpec

            ndjson = [p for p in self.datasets if p.suffix.lower() == ".ndjson"]
            bundles = [p for p in self.datasets if p.suffix.lower() == ".json"]
            spec = DatasetSpec(
                ndjson_paths=[str(p) for p in ndjson] or None,
                bundle_paths=[str(p) for p in bundles] or None,
                valueset_paths=[str(p) for p in self.valuesets] or None,
            )
            result = load_dataset(spec, conn)
            if not result.ok:
                self.load_diagnostics = [
                    d.to_dict() for d in result.diagnostics
                ]
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
        result = translate_cql(includes, main, **kwargs)
        return result.to_dict()

    def evaluate(
        self,
        includes: list[LibraryText],
        main: LibraryText,
        **kwargs: Any,
    ) -> dict[str, Any]:
        result = evaluate_library(includes, main, None, self._conn, **kwargs)
        return result.to_dict()

    def verify(
        self,
        includes: list[LibraryText],
        main: LibraryText,
        cases: Any,
        **kwargs: Any,
    ) -> dict[str, Any]:
        result = run_tests(includes, main, None, cases, self._conn, **kwargs)
        return result.to_dict()

    def explain(
        self,
        includes: list[LibraryText],
        main: LibraryText,
        patient_id: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        result = explain_patient(
            includes, main, None, patient_id, self._conn, **kwargs
        )
        return result.to_dict()


class KernelManager:
    """Thread-safe current-kernel holder with restart."""

    def __init__(self, snapshot: WorkspaceSnapshot) -> None:
        self._lock = threading.Lock()
        self._kernel = Kernel(snapshot.datasets, snapshot.valuesets)

    def current(self) -> Kernel:
        with self._lock:
            return self._kernel

    def restart(self, snapshot: WorkspaceSnapshot) -> Kernel:
        """Build a fresh kernel; in-flight work on the old one drains."""
        new_kernel = Kernel(snapshot.datasets, snapshot.valuesets)
        with self._lock:
            self._kernel = new_kernel
        return new_kernel
