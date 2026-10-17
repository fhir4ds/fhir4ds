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
        self._conn = self._build_connection()

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
            bundles = [
                p
                for p in self.datasets
                if p.suffix.lower() == ".json"
                and not _is_parameters_resource(p)
            ]
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
