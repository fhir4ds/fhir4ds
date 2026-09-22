"""load_dataset capability: DatasetSpec -> FHIRDataLoader -> per-type counts."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from ..envelopes import DatasetSpec, _EnvelopeFields
from ..errors import diagnostic_from_exception


@dataclass(frozen=True)
class DatasetResult(_EnvelopeFields):
    ok: bool = True
    passed: object = None
    diagnostics: tuple = ()
    resource_counts: dict[str, int] = None  # type: ignore[assignment]
    total: int = 0

    def __post_init__(self) -> None:
        if self.resource_counts is None:
            object.__setattr__(self, "resource_counts", {})

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"schema": self.schema, "ok": self.ok}
        if self.passed is not None:
            out["passed"] = self.passed
        if self.diagnostics:
            out["diagnostics"] = [d.to_dict() for d in self.diagnostics]
        out["resource_counts"] = dict(self.resource_counts or {})
        out["total"] = self.total
        return out


def _count_from_conn(conn: Any) -> dict[str, int]:
    rows = conn.execute(
        "SELECT resourceType, COUNT(*) FROM resources GROUP BY resourceType ORDER BY resourceType"
    ).fetchall()
    return {r[0]: int(r[1]) for r in rows}


def load_dataset(dataset: DatasetSpec, conn: Any) -> DatasetResult:
    """Load a DatasetSpec through FHIRDataLoader; return per-type counts.

    Valueset-only specs still produce counts of the resources table as
    it exists (terminology loading without resetting data).
    """
    from fhir4ds.cql.loader import FHIRDataLoader

    try:
        loader = FHIRDataLoader(conn)
        if dataset.resources is not None:
            loader.load_resources(dataset.resources)
        elif dataset.ndjson_paths:
            for path in dataset.ndjson_paths:
                loader.load_ndjson(path, strict=True)
        elif dataset.bundle_paths:
            for path in dataset.bundle_paths:
                with open(path, encoding="utf-8-sig") as fh:
                    bundle = json.load(fh)
                loader.load_bundle(bundle)
        if dataset.valueset_paths:
            for path in dataset.valueset_paths:
                loader.load_valuesets(path)
        if dataset.valueset_resources:
            for vs in dataset.valueset_resources:
                loader.load_valuesets([vs])
        counts = _count_from_conn(conn)
    except Exception as exc:
        return DatasetResult(
            ok=False,
            diagnostics=(diagnostic_from_exception(exc, context="load_dataset"),),
        )
    return DatasetResult(
        resource_counts=counts,
        total=sum(counts.values()),
    )
