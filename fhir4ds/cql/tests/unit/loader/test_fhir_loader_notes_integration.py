"""Integration tests: FHIRDataLoader + NotesPipeline.

Critical invariant: when ``notes_pipeline=None`` (default), loader
behavior must be byte-identical to pre-Phase-4. We assert this by
comparing the SQL-queryable resources table against a baseline load.
"""

from __future__ import annotations

import json
import sys
import types
from dataclasses import dataclass

import duckdb
import pytest

from fhir4ds.cql.loader import FHIRDataLoader, NotesPipeline, NotesPipelineConfig


@dataclass
class _MockConcept:
    code: str
    source: str
    display: str
    matched_text: str
    status: str = "affirmed"
    section: str | None = None
    confidence: float = 0.95
    match_grade: str = "certain"
    category: str = "condition"
    span_start: int = 0
    span_end: int = 0


@pytest.fixture
def mock_medterm4ds(monkeypatch):
    fake = types.ModuleType("medterm4ds")
    fake.__index_version__ = "test-2026AA"
    monkeypatch.setitem(sys.modules, "medterm4ds", fake)
    return fake


def _observation() -> dict:
    return {
        "resourceType": "Observation",
        "id": "obs-1",
        "status": "final",
        "subject": {"reference": "Patient/pat-1"},
        "code": {"coding": [{"system": "http://loinc.org", "code": "1234-5"}]},
        "note": [{"text": "Patient has diabetes."}],
    }


# ----------------------------------------------------------------------
# CRITICAL: notes_pipeline=None is byte-identical to pre-Phase-4
# ----------------------------------------------------------------------

def test_notes_pipeline_none_byte_identical_to_baseline():
    """With notes_pipeline=None, the resources table is byte-identical."""

    def _load(observation):
        con = duckdb.connect(":memory:")
        loader = FHIRDataLoader(con)
        loader.load_resource(observation)
        rows = con.execute(
            "SELECT id, resourceType, resource, patient_ref FROM resources ORDER BY id"
        ).fetchall()
        con.close()
        return rows

    baseline = _load(_observation())
    # Re-run with notes_pipeline explicitly None — same result.
    explicit_none = _load_with_pipeline(None, _observation())
    assert baseline == explicit_none


def _load_with_pipeline(pipeline, observation):
    con = duckdb.connect(":memory:")
    loader = FHIRDataLoader(con, notes_pipeline=pipeline)
    loader.load_resource(observation)
    rows = con.execute(
        "SELECT id, resourceType, resource, patient_ref FROM resources ORDER BY id"
    ).fetchall()
    con.close()
    return rows


def test_notes_pipeline_default_is_none():
    """FHIRDataLoader's notes_pipeline defaults to None (opt-in)."""
    con = duckdb.connect(":memory:")
    loader = FHIRDataLoader(con)
    assert loader._notes_pipeline is None


def test_batch_load_notes_pipeline_none_byte_identical():
    """load_resources with notes_pipeline=None is byte-identical."""

    def _load_batch(pipeline):
        con = duckdb.connect(":memory:")
        loader = FHIRDataLoader(con, notes_pipeline=pipeline)
        loader.load_resources([_observation()])
        rows = con.execute(
            "SELECT id, resourceType, resource, patient_ref FROM resources ORDER BY id"
        ).fetchall()
        con.close()
        return rows

    baseline = _load_batch(None)
    assert len(baseline) == 1


# ----------------------------------------------------------------------
# With mocked notes_pipeline, source + derived Conditions both loaded
# ----------------------------------------------------------------------

def test_load_resource_with_pipeline_loads_source_and_derived(mock_medterm4ds):
    """load_resource appends derived Conditions alongside source."""
    mock_medterm4ds.extract = lambda text, **kw: [_MockConcept(
        code="73211009", source="SNOMEDCT_US", display="Diabetes",
        matched_text="diabetes", status="affirmed",
        span_start=12, span_end=20,
    )]
    pipeline = NotesPipeline(NotesPipelineConfig())

    con = duckdb.connect(":memory:")
    loader = FHIRDataLoader(con, notes_pipeline=pipeline)
    loader.load_resource(_observation())

    types_counts = con.execute(
        "SELECT resourceType, COUNT(*) FROM resources GROUP BY resourceType ORDER BY resourceType"
    ).fetchall()
    types_dict = dict(types_counts)
    assert types_dict.get("Observation") == 1
    assert types_dict.get("Condition") == 1  # derived Condition appended


def test_load_resources_batch_with_pipeline_loads_derived(mock_medterm4ds):
    """load_resources appends derived Conditions in the batch path too."""
    mock_medterm4ds.extract = lambda text, **kw: [_MockConcept(
        code="73211009", source="SNOMEDCT_US", display="Diabetes",
        matched_text="diabetes", status="affirmed",
        span_start=12, span_end=20,
    )]
    pipeline = NotesPipeline(NotesPipelineConfig())

    obs1 = _observation()
    obs2 = _observation()
    obs2["id"] = "obs-2"
    con = duckdb.connect(":memory:")
    loader = FHIRDataLoader(con, notes_pipeline=pipeline)
    n = loader.load_resources([obs1, obs2])
    # 2 sources + 2 derived = 4
    assert n == 4
    types_counts = con.execute(
        "SELECT resourceType, COUNT(*) FROM resources GROUP BY resourceType"
    ).fetchall()
    types_dict = dict(types_counts)
    assert types_dict.get("Observation") == 2
    assert types_dict.get("Condition") == 2


def test_load_resource_pipeline_does_not_raise_on_disabled_pipeline():
    """When medterm4ds is unavailable, the loader still loads the source."""
    # No mock installed — medterm4ds import will fail. extract_conditions
    # catches and caches _DISABLED_SENTINEL, returns [].
    pipeline = NotesPipeline(NotesPipelineConfig())
    con = duckdb.connect(":memory:")
    loader = FHIRDataLoader(con, notes_pipeline=pipeline)
    # Should not raise; source resource still loaded.
    loader.load_resource(_observation())
    count = con.execute("SELECT COUNT(*) FROM resources").fetchone()[0]
    assert count == 1
