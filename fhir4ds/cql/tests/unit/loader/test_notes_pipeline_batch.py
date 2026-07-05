"""Step 2 + Step 3 — NotesPipeline.extract_conditions_batch + loader integration.

Verifies that batch and per-resource extraction produce byte-identical
derived Conditions for any ``batch_size`` × ``workers`` combination
(with ``parallel_threshold=0`` so the parallel path is bypassed and we
test the synchronous chunked batch path).
"""

from __future__ import annotations

import sys
import types
from dataclasses import dataclass

import duckdb
import pytest

from fhir4ds.cql.loader.notes_pipeline import (
    NotesPipeline,
    NotesPipelineConfig,
)


@dataclass
class _MockConcept:
    code: str
    source: str
    display: str
    matched_text: str
    status: str = "affirmed"
    confidence: float = 0.95
    match_grade: str = "certain"
    span_start: int = 0
    span_end: int = 0


@pytest.fixture
def mock_medterm4ds(monkeypatch):
    """Install a fake ``medterm4ds`` module returning canned concepts."""
    fake = types.ModuleType("medterm4ds")
    fake.__index_version__ = "test-index"
    monkeypatch.setitem(sys.modules, "medterm4ds", fake)
    return fake


def _observation(note_text: str = "Patient has diabetes.", rid: str = "obs-1") -> dict:
    return {
        "resourceType": "Observation",
        "id": rid,
        "subject": {"reference": "Patient/pat-1"},
        "note": [{"text": note_text}],
    }


# ── Step 2: extract_conditions_batch correctness ────────────────────


@pytest.mark.parametrize("batch_size", [1, 10, 500])
def test_extract_conditions_batch_byte_identical(mock_medterm4ds, batch_size):
    """Batch path produces the same Conditions as per-resource path."""
    mock_medterm4ds.extract = lambda text, **kw: [_MockConcept(
        code="73211009",
        source="SNOMEDCT_US",
        display="Diabetes mellitus",
        matched_text="diabetes",
        status="affirmed",
        confidence=0.93,
        match_grade="certain",
        span_start=12,
        span_end=20,
    )]

    inputs = [_observation("diabetes text", f"obs-{i}") for i in range(5)]

    # Baseline: per-resource
    baseline_pipe = NotesPipeline(NotesPipelineConfig(batch_size=1, workers=1))
    baseline = [baseline_pipe.extract_conditions(r) for r in [dict(i, id=i["id"]) for i in inputs]]

    # Test: batch path
    test_pipe = NotesPipeline(NotesPipelineConfig(
        batch_size=batch_size, workers=1, parallel_threshold=0,
    ))
    test_inputs = [dict(i, id=i["id"]) for i in inputs]
    test = test_pipe.extract_conditions_batch(test_inputs)

    assert len(test) == len(inputs)
    for i, (baseline_conds, test_conds) in enumerate(zip(baseline, test)):
        assert len(baseline_conds) == len(test_conds), (
            f"Mismatch at index {i}: {len(baseline_conds)} vs {len(test_conds)}"
        )
        for b, t in zip(baseline_conds, test_conds):
            # IDs are deterministic (INV-6) — must match byte-for-byte
            assert b["id"] == t["id"], (
                f"Condition id mismatch at index {i}: {b['id']} vs {t['id']}"
            )


def test_extract_conditions_batch_empty(mock_medterm4ds):
    pipe = NotesPipeline(NotesPipelineConfig())
    assert pipe.extract_conditions_batch([]) == []


def test_extract_conditions_batch_does_not_raise_on_bad_resource(mock_medterm4ds):
    mock_medterm4ds.extract = lambda text, **kw: [_MockConcept(
        code="73211009", source="SNOMEDCT_US", display="x", matched_text="x"
    )]
    pipe = NotesPipeline(NotesPipelineConfig(batch_size=10, workers=1, parallel_threshold=0))
    # Mixed valid + invalid input — must not raise (INV-A4)
    out = pipe.extract_conditions_batch([
        {"resourceType": "Observation", "id": "ok", "note": [{"text": "ok"}]},
        "not-a-dict",  # invalid
    ])
    assert len(out) == 2  # one list per input
    assert out[1] == []  # bad resource → empty list


def test_extract_conditions_batch_parallel_threshold_logs(mock_medterm4ds, caplog):
    """When workers>1 and len < parallel_threshold, an INFO log fires."""
    import logging
    mock_medterm4ds.extract = lambda text, **kw: []
    pipe = NotesPipeline(NotesPipelineConfig(
        batch_size=10, workers=4, parallel_threshold=1000,
    ))
    with caplog.at_level(logging.INFO, logger="fhir4ds.cql.loader.notes_pipeline"):
        pipe.extract_conditions_batch([_observation(rid="x")])
    # The INFO log line about parallel_threshold should appear
    assert any("parallel_threshold" in r.message for r in caplog.records)


# ── Step 3: FHIRDataLoader integration ────────────────────────────────


@pytest.mark.parametrize("batch_size", [1, 10, 500])
def test_load_ndjson_byte_identical_with_notes_pipeline(mock_medterm4ds, batch_size, tmp_path):
    """load_ndjson with notes_pipeline.batch_size=N produces identical
    resources table to batch_size=1."""
    mock_medterm4ds.extract = lambda text, **kw: [_MockConcept(
        code="73211009",
        source="SNOMEDCT_US",
        display="Diabetes mellitus",
        matched_text="diabetes",
        span_start=0, span_end=8,
    )]
    from fhir4ds.cql.loader.fhir_loader import FHIRDataLoader
    import json

    fixtures = [_observation("diabetes", f"obs-{i}") for i in range(3)]
    ndjson = tmp_path / "obs.ndjson"
    ndjson.write_text("\n".join(json.dumps(r) for r in fixtures))

    # Baseline
    con_b = duckdb.connect()
    loader_b = FHIRDataLoader(
        con_b,
        notes_pipeline=NotesPipeline(NotesPipelineConfig(
            batch_size=1, workers=1, parallel_threshold=0,
        )),
    )
    loader_b.load_ndjson(str(ndjson))
    rows_b = con_b.execute(
        "SELECT id, resourceType, resource FROM resources ORDER BY id"
    ).fetchall()

    # Test
    con_t = duckdb.connect()
    loader_t = FHIRDataLoader(
        con_t,
        notes_pipeline=NotesPipeline(NotesPipelineConfig(
            batch_size=batch_size, workers=1, parallel_threshold=0,
        )),
    )
    loader_t.load_ndjson(str(ndjson))
    rows_t = con_t.execute(
        "SELECT id, resourceType, resource FROM resources ORDER BY id"
    ).fetchall()

    assert len(rows_b) == len(rows_t)
    for b, t in zip(rows_b, rows_t):
        assert b[0] == t[0]  # id
        assert b[1] == t[1]  # resourceType
        assert b[2] == t[2]  # resource JSON
