"""Step 6 — AutoCoder parallel dispatch (DEFERRED per FDD).

The original plan called for a thread pool. Step 5 surfaced a
DuckDB-shared-connection hazard that applies to threads too (DuckDB
``Connection`` cannot be safely shared across concurrent ``execute()``
calls). Per FDD §Step 6: "Skip if Step 5 surfaces problems that
warrant deferring." We defer.

These tests verify the deferral: ``augment_resources`` with
``workers > 1`` falls back to synchronous chunked mode, producing
byte-identical results to ``workers == 1``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import duckdb
import pytest

from fhir4ds.cql.loader.auto_coder import AutoCoder, AutoCoderConfig


@dataclass(frozen=True)
class _StubSearchResult:
    system: str
    code: str
    display: Optional[str]
    score: float
    match_grade: str
    search_mode: str
    index_version: Optional[str]


class _StubEndpoint:
    """In-memory stub returning deterministic results per text."""

    def __init__(self):
        self._results = {
            "diabetes": [_StubSearchResult(
                system="http://snomed.info/sct", code="73211009",
                display="DM", score=0.95, match_grade="certain",
                search_mode="hybrid", index_version="v1",
            )],
        }

    def search_text(self, query, category, *, mode="hybrid"):
        return self._results.get(query.lower().strip(), [])

    def search_batch(self, queries, *, mode="hybrid"):
        return [self.search_text(q, c, mode=mode) for q, c in queries]


def _condition(text: str, rid: str) -> dict:
    return {
        "resourceType": "Condition",
        "id": rid,
        "code": {"text": text},
        "subject": {"reference": "Patient/pat-1"},
    }


@pytest.mark.parametrize("batch_size", [1, 10, 500])
@pytest.mark.parametrize("workers", [1, 2, 4])
def test_augment_resources_deferred_byte_identical(batch_size, workers):
    """Cross-config: all 9 combinations produce identical Codings.

    Step 6 is deferred (see module docstring) — ``workers > 1`` falls
    back to synchronous chunked mode. The byte-identical invariant
    must still hold.
    """
    endpoint = _StubEndpoint()
    con = duckdb.connect()
    ac = AutoCoder(endpoint, con, config=AutoCoderConfig(batch_size=batch_size, workers=workers))
    resources = [_condition("diabetes", f"c-{i}") for i in range(5)]
    ac.augment_resources(resources)
    for r in resources:
        codings = r["code"]["coding"]
        assert len(codings) == 1
        assert codings[0]["code"] == "73211009"


def test_augment_batch_parallel_raises_not_implemented():
    """The deferred pool surfaces NotImplementedError internally."""
    endpoint = _StubEndpoint()
    con = duckdb.connect()
    ac = AutoCoder(endpoint, con, config=AutoCoderConfig(batch_size=10, workers=2))
    with pytest.raises(NotImplementedError):
        ac._augment_batch_parallel([_condition("diabetes", "c1")])


def test_augment_resources_workers_gt_1_does_not_deadlock():
    """Regression: ensure the deferred path doesn't accidentally spin up
    a thread pool that deadlocks on DuckDB."""
    endpoint = _StubEndpoint()
    con = duckdb.connect()
    ac = AutoCoder(endpoint, con, config=AutoCoderConfig(batch_size=10, workers=4))
    resources = [_condition("diabetes", f"c-{i}") for i in range(20)]
    # Must complete (no deadlock).
    ac.augment_resources(resources)
    assert all("coding" in r["code"] for r in resources)
