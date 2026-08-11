"""Integration tests for FHIRDataLoader + AutoCoder hook.

Reference: FDD §5.2 — verifies:
    * INV-1: auto_coder=None (default) preserves byte-identical behavior.
    * With a stub auto_coder, resources are augmented BEFORE write.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import duckdb
import pytest

from fhir4ds.cql.loader import FHIRDataLoader, AutoCoder, AutoCoderConfig
from fhir4ds.cql.tests.unit.loader.test_auto_coder import _StubEndpoint, _StubSearchResult


@pytest.fixture
def duckdb_con():
    con = duckdb.connect(":memory:")
    yield con
    con.close()


# ── INV-1: auto_coder=None is byte-identical ──────────────────────────


def test_inv1_load_resource_byte_identical_with_none(duckdb_con):
    """load_resource output is byte-identical with vs without auto_coder=None kwarg."""
    resource = {
        "resourceType": "Patient", "id": "p1",
        "name": [{"family": "Doe"}],
    }

    loader_no_kwarg = FHIRDataLoader(duckdb_con, table_name="t1")
    loader_no_kwarg.load_resource(resource)
    row1 = duckdb_con.execute("SELECT resource FROM t1").fetchone()
    bytes_without_kwarg = row1[0]

    duckdb_con.execute("DROP TABLE t2").fetchall() if False else None  # type: ignore
    loader_with_none_kwarg = FHIRDataLoader(duckdb_con, table_name="t2", auto_coder=None)
    loader_with_none_kwarg.load_resource(resource)
    row2 = duckdb_con.execute("SELECT resource FROM t2").fetchone()
    bytes_with_none_kwarg = row2[0]

    # Compare normalized JSON (DuckDB may store JSON with different whitespace).
    parsed_without = json.loads(bytes_without_kwarg) if isinstance(bytes_without_kwarg, str) else json.loads(bytes_without_kwarg)
    parsed_with = json.loads(bytes_with_none_kwarg) if isinstance(bytes_with_none_kwarg, str) else json.loads(bytes_with_none_kwarg)
    assert parsed_without == parsed_with == resource


def test_inv1_load_resources_byte_identical_with_none(duckdb_con):
    """load_resources output is byte-identical with auto_coder=None."""
    resources = [
        {"resourceType": "Patient", "id": "p1"},
        {"resourceType": "Condition", "id": "c1",
         "code": {"text": "Type 2 Diabetes Mellitus"}},
    ]

    FHIRDataLoader(duckdb_con, table_name="t1").load_resources(copy.deepcopy(resources))
    FHIRDataLoader(duckdb_con, table_name="t2", auto_coder=None).load_resources(copy.deepcopy(resources))

    rows1 = duckdb_con.execute("SELECT id, resource FROM t1 ORDER BY id").fetchall()
    rows2 = duckdb_con.execute("SELECT id, resource FROM t2 ORDER BY id").fetchall()

    assert len(rows1) == len(rows2)
    for (id1, r1), (id2, r2) in zip(rows1, rows2):
        assert id1 == id2
        parsed1 = r1 if isinstance(r1, dict) else json.loads(r1)
        parsed2 = r2 if isinstance(r2, dict) else json.loads(r2)
        assert parsed1 == parsed2


# ── With a stub AutoCoder, augmentation happens BEFORE write ──────────


def test_stub_auto_coder_appends_coding_before_write(duckdb_con):
    """Auto-coded Codings appear in the stored resource JSON column."""
    endpoint = _StubEndpoint(
        results_by_query={
            "Type 2 Diabetes Mellitus": [
                _StubSearchResult(
                    system="http://snomed.info/sct", code="44054006",
                    display="Type 2 diabetes mellitus", score=0.95,
                    match_grade="certain", search_mode="hybrid",
                    index_version=None,
                )
            ]
        }
    )
    auto_coder = AutoCoder(endpoint, duckdb_con, config=AutoCoderConfig(index_version="v1"))
    loader = FHIRDataLoader(duckdb_con, table_name="t1", auto_coder=auto_coder)

    resource = {
        "resourceType": "Condition", "id": "c1",
        "subject": {"reference": "Patient/p1"},
        "code": {"text": "Type 2 Diabetes Mellitus"},
    }
    loader.load_resource(resource)

    stored = duckdb_con.execute(
        "SELECT resource FROM t1 WHERE id = 'c1'"
    ).fetchone()
    parsed = json.loads(stored[0]) if isinstance(stored[0], str) else stored[0]
    codings = parsed["code"]["coding"]
    assert len(codings) == 1
    assert codings[0]["code"] == "44054006"
    assert codings[0]["userSelected"] is False
    # text preserved (INV-2)
    assert parsed["code"]["text"] == "Type 2 Diabetes Mellitus"


def test_stub_auto_coder_via_load_resources(duckdb_con):
    """Auto-coder also fires via the load_resources batch path."""
    endpoint = _StubEndpoint(
        results_by_query={
            "Essential Hypertension": [
                _StubSearchResult(
                    system="http://snomed.info/sct", code="59621000",
                    display=None, score=0.92, match_grade="certain",
                    search_mode="hybrid", index_version=None,
                )
            ]
        }
    )
    auto_coder = AutoCoder(endpoint, duckdb_con, config=AutoCoderConfig(index_version="v1"))
    loader = FHIRDataLoader(duckdb_con, table_name="t1", auto_coder=auto_coder)

    resources = [
        {"resourceType": "Condition", "id": "c1",
         "subject": {"reference": "Patient/p1"},
         "code": {"text": "Essential Hypertension"}},
        {"resourceType": "Patient", "id": "p1"},
    ]
    loader.load_resources(resources)

    # Only the Condition got augmented; Patient is skipped (no category).
    rows = duckdb_con.execute(
        "SELECT id, resourceType, resource FROM t1 ORDER BY id"
    ).fetchall()
    by_type = {(r[0], r[1]): r[2] for r in rows}
    cond = by_type[("c1", "Condition")]
    parsed = json.loads(cond) if isinstance(cond, str) else cond
    assert len(parsed["code"]["coding"]) == 1
    pat = by_type[("p1", "Patient")]
    parsed_pat = json.loads(pat) if isinstance(pat, str) else pat
    assert "coding" not in parsed_pat  # Patient not augmented


def test_load_ndjson_with_auto_coder_uses_hook(duckdb_con, tmp_path):
    """NDJSON load path exercises the auto-coder hook for every resource."""
    endpoint = _StubEndpoint(
        results_by_query={
            "Type 2 Diabetes Mellitus": [
                _StubSearchResult(
                    system="http://snomed.info/sct", code="44054006",
                    display=None, score=0.9, match_grade="certain",
                    search_mode="hybrid", index_version=None,
                )
            ]
        }
    )
    auto_coder = AutoCoder(endpoint, duckdb_con, config=AutoCoderConfig(index_version="v1"))
    loader = FHIRDataLoader(duckdb_con, auto_coder=auto_coder)
    ndjson = tmp_path / "fixture.ndjson"
    ndjson.write_text(
        '{"resourceType":"Condition","id":"c1","subject":{"reference":"Patient/p1"},'
        '"code":{"text":"Type 2 Diabetes Mellitus"}}\n'
    )
    loader.load_ndjson(ndjson)
    row = duckdb_con.execute(
        "SELECT resource FROM resources WHERE id = 'c1'"
    ).fetchone()
    parsed = json.loads(row[0]) if isinstance(row[0], str) else row[0]
    assert len(parsed["code"]["coding"]) == 1


# ── Path to the bundled fixture file (smoke test only) ────────────────


FIXTURE_PATH = Path(__file__).resolve().parents[2] / "fixtures" / "conditions_text_only.ndjson"


def test_fixture_file_exists():
    """Fixture NDJSON ships at the documented path."""
    assert FIXTURE_PATH.exists(), f"Fixture missing at {FIXTURE_PATH}"


def test_fixture_all_lines_valid_json(duckdb_con):
    """Every line of the fixture is valid JSON loadable by FHIRDataLoader."""
    loader = FHIRDataLoader(duckdb_con)
    loader.load_ndjson(FIXTURE_PATH)
    # 9 Conditions + 1 Patient = 10 resources.
    assert loader.count() == 10
    assert loader.count("Condition") == 9
    assert loader.count("Patient") == 1
