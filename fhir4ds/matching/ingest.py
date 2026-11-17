"""Ingest-time patient matching hook (AMUX-134 slice 3).

Standalone API — NOT yet wired into ``FHIRDataLoader`` (gated on Joel's
default decision in a later slice). For each Patient resource in the batch:
index it, match it against the corpus indexed so far (self excluded), record
the audit row(s), and upsert a Linkage resource on approved matches.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Iterable

import duckdb

from .audit import record_match_audit
from .engine import match_patient
from .linkage import upsert_linkage
from .store import index_patient

__all__ = [
    "IngestReport",
    "VALID_OUTCOMES",
    "match_on_ingest",
    "maybe_match_on_ingest",
]

VALID_OUTCOMES = frozenset({"match", "ambiguous", "no_match"})


@dataclass
class IngestReport:
    indexed: int = 0
    matched: int = 0
    ambiguous: int = 0
    no_match: int = 0
    links_created: int = 0

    @property
    def counts(self) -> dict[str, int]:
        return asdict(self)


def match_on_ingest(
    conn: duckdb.DuckDBPyConnection,
    resources: list[dict],
    run_id: str,
    link_threshold: Iterable[str] = frozenset({"match"}),
) -> IngestReport:
    """Match every Patient in ``resources`` against the corpus as it grows.

    Patients are matched BEFORE being indexed (new patient vs existing
    corpus), with their own id excluded so re-running an ingest against an
    already-indexed corpus never self-matches. Linkage resources are
    created for every outcome in ``link_threshold`` (default: approved
    matches only; ``{"match", "ambiguous"}`` also links ambiguous pairs for
    human-review workflows).
    """
    if not isinstance(run_id, str) or not run_id:
        raise ValueError("run_id must be a non-empty string")
    threshold = frozenset(link_threshold)
    invalid = threshold - VALID_OUTCOMES
    if invalid:
        raise ValueError(
            f"link_threshold entries must be outcomes {sorted(VALID_OUTCOMES)}, got {sorted(invalid)}"
        )
    report = IngestReport()
    for resource in resources:
        if not isinstance(resource, dict) or resource.get("resourceType") != "Patient":
            continue
        patient_id = resource.get("id")
        if not isinstance(patient_id, str) or not patient_id:
            raise ValueError("Patient resource must carry a non-empty string 'id'")
        result = match_patient(conn, resource, exclude={patient_id})
        index_patient(conn, resource)
        report.indexed += 1
        record_match_audit(conn, run_id, patient_id, result)
        if result.outcome == "match":
            report.matched += 1
        elif result.outcome == "ambiguous":
            report.ambiguous += 1
        else:
            report.no_match += 1
        if result.outcome in threshold:
            for candidate_id in result.matched_ids:
                outcome = upsert_linkage(conn, result, patient_id, candidate_id)
                if outcome["action"] == "created":
                    report.links_created += 1
    return report


def maybe_match_on_ingest(
    conn: duckdb.DuckDBPyConnection,
    resources: list[dict],
    *,
    enabled: bool,
    run_id: str,
) -> IngestReport:
    """Flag-gated wrapper; ``enabled=False`` is a strict no-op."""
    if not enabled:
        return IngestReport()
    return match_on_ingest(conn, resources, run_id)
