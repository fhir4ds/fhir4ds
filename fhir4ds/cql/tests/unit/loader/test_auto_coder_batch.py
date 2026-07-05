"""Step 2 + Step 3 — AutoCoder.augment_resources + loader integration.

Verifies that batch and per-resource augmentation produce byte-identical
Coding attachments for any ``batch_size`` × ``workers`` combination.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Optional

import duckdb
import pytest

from fhir4ds.cql.loader.auto_coder import AutoCoder, AutoCoderConfig
from fhir4ds.cql.loader.fhir_loader import FHIRDataLoader


# ── Stub endpoint (mirrors test_auto_coder.py) ────────────────────────


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
    """In-memory stub. Returns deterministic results per query text."""

    def __init__(self):
        self._results = {
            "diabetes": [_StubSearchResult(
                system="http://snomed.info/sct",
                code="73211009",
                display="Diabetes mellitus",
                score=0.95,
                match_grade="certain",
                search_mode="hybrid",
                index_version="2026AA",
            )],
            "hypertension": [_StubSearchResult(
                system="http://snomed.info/sct",
                code="38341003",
                display="Hypertension",
                score=0.92,
                match_grade="certain",
                search_mode="hybrid",
                index_version="2026AA",
            )],
        }

    def search_text(self, query, category, *, mode="hybrid"):
        return self._results.get(query.lower().strip(), [])

    def search_batch(self, queries, *, mode="hybrid"):
        return [self.search_text(q, c, mode=mode) for q, c in queries]


def _condition(text: str, rid: str = "cond-1") -> dict:
    return {
        "resourceType": "Condition",
        "id": rid,
        "code": {"text": text},
        "subject": {"reference": "Patient/pat-1"},
    }


# ── Step 2: augment_resources correctness ────────────────────────────


@pytest.fixture
def auto_coder():
    cfg = AutoCoderConfig(batch_size=1, workers=1)
    con = duckdb.connect()
    return AutoCoder(_StubEndpoint(), con, config=cfg)


@pytest.mark.parametrize("batch_size", [1, 10, 500])
@pytest.mark.parametrize("workers", [1, 2, 4])
def test_augment_resources_byte_identical_per_resource(batch_size, workers):
    """augment_resources with any (batch_size, workers) produces the
    same Coding attachments as the per-resource path."""
    endpoint = _StubEndpoint()
    con = duckdb.connect()

    # Per-resource baseline
    baseline_resources = [_condition("diabetes", "c1"), _condition("hypertension", "c2")]
    ac_baseline = AutoCoder(endpoint, con, config=AutoCoderConfig(batch_size=1, workers=1))
    for r in baseline_resources:
        ac_baseline.augment_resource(r)

    # Batch path with all 9 combinations
    cfg = AutoCoderConfig(batch_size=batch_size, workers=workers)
    test_resources = [_condition("diabetes", "c1"), _condition("hypertension", "c2")]
    ac_batch = AutoCoder(endpoint, con, config=cfg)
    ac_batch.augment_resources(test_resources)

    # Codings must match
    for baseline_r, test_r in zip(baseline_resources, test_resources):
        baseline_codings = baseline_r["code"]["coding"]
        test_codings = test_r["code"]["coding"]
        assert baseline_codings == test_codings, (
            f"Mismatch at batch_size={batch_size}, workers={workers}: "
            f"{baseline_codings} vs {test_codings}"
        )


def test_augment_resources_empty_list_is_noop(auto_coder):
    auto_coder.augment_resources([])
    # No assertion needed — must not raise.


def test_augment_resources_does_not_double_augment():
    """Existing Codings are preserved (INV-4 — no double-coding)."""
    endpoint = _StubEndpoint()
    con = duckdb.connect()
    cfg = AutoCoderConfig(batch_size=10, workers=1)
    ac = AutoCoder(endpoint, con, config=cfg)
    resource = _condition("diabetes", "c1")
    # First augmentation
    ac.augment_resources([resource])
    initial_count = len(resource["code"]["coding"])
    # Second augmentation on same resource — should NOT add more
    ac.augment_resources([resource])
    assert len(resource["code"]["coding"]) == initial_count


# ── Step 3: FHIRDataLoader integration ────────────────────────────────


@pytest.mark.parametrize("batch_size", [1, 10, 500])
def test_load_ndjson_byte_identical_resources_table(batch_size, tmp_path):
    """load_ndjson with auto_coder.batch_size=N produces identical
    resources table to batch_size=1."""
    fixtures = [
        _condition("diabetes", "c1"),
        _condition("hypertension", "c2"),
        _condition("diabetes", "c3"),
    ]
    ndjson = tmp_path / "conditions.ndjson"
    ndjson.write_text("\n".join(
        __import__("json").dumps(r) for r in fixtures
    ))

    # Baseline: batch_size=1
    con_baseline = duckdb.connect()
    loader_baseline = FHIRDataLoader(
        con_baseline,
        auto_coder=AutoCoder(
            _StubEndpoint(), con_baseline,
            config=AutoCoderConfig(batch_size=1, workers=1),
        ),
    )
    loader_baseline.load_ndjson(str(ndjson))
    baseline_rows = con_baseline.execute(
        "SELECT id, resourceType, resource FROM resources ORDER BY id"
    ).fetchall()

    # Test: batch_size=N
    con_test = duckdb.connect()
    loader_test = FHIRDataLoader(
        con_test,
        auto_coder=AutoCoder(
            _StubEndpoint(), con_test,
            config=AutoCoderConfig(batch_size=batch_size, workers=1),
        ),
    )
    loader_test.load_ndjson(str(ndjson))
    test_rows = con_test.execute(
        "SELECT id, resourceType, resource FROM resources ORDER BY id"
    ).fetchall()

    assert len(baseline_rows) == len(test_rows)
    for baseline_row, test_row in zip(baseline_rows, test_rows):
        # id and resourceType must match exactly
        assert baseline_row[0] == test_row[0], f"id mismatch: {baseline_row[0]} vs {test_row[0]}"
        assert baseline_row[1] == test_row[1]
        # resource JSON must be byte-identical
        assert baseline_row[2] == test_row[2], (
            f"resource JSON mismatch at id={baseline_row[0]}:\n"
            f"  baseline: {baseline_row[2]}\n  test:      {test_row[2]}"
        )
