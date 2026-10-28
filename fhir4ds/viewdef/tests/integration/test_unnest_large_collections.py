"""Regression: forEach/forEachOrNull unnests must be O(N), not O(N x payload).

Before the fix, the lowering extracted each element with
``json_extract(jarr, '$[' || idx || ']')`` (and, in an attempted fix,
``arr[idx + 1]``). Both are per-row full-payload operations in DuckDB:
a 20k-element collection needed ~30 GB and 15-18 s, and a 157k-element
collection could not complete at all. That made large ConceptMaps (the
OMOP mapping library) unusable without chunking.

The fix uses the one-pass form already proven by ``repeat``:

    SELECT unnest(js) AS elem, unnest(range(len(js))) AS elem__row_index
    FROM (SELECT TRY_CAST(fhirpath_json(res, path) AS JSON[]) AS js FROM ...) v

JSON[] typing keeps ``type()`` / ``$this`` semantics identical to the old
path (primitive focus elements stay JSON strings).

These tests pin a hard memory cap so a regression fails deterministically
instead of merely becoming slow.
"""

import json
import time

import pytest

import fhir4ds
from fhir4ds.viewdef.generator import SQLGenerator
from fhir4ds.viewdef.parser import parse_view_definition

BIG_N = 50_000
NESTED_M = 5_000  # per-group elements in the nested (real ConceptMap) shape
SMOKE_N = 20_000  # CI-safe: bounded runtime, still OOMs at cap if O(N*payload)
SMOKE_TIME_BUDGET_S = 10.0


def _big_resource(n=BIG_N):
    """A ConceptMap whose group.element array has n members."""
    return {
        "resourceType": "ConceptMap",
        "id": "big",
        "status": "active",
        "group": [
            {
                "source": "http://www.nlm.nih.gov/research/umls/rxnorm",
                "target": "urn:omop:concept",
                "element": [
                    {
                        "code": str(2_700_000 + i),
                        "target": [{"code": str(37_000_000 + i), "equivalence": "equal"}],
                    }
                    for i in range(n)
                ],
            }
        ],
    }


def _nested_resource(groups=4, per_group=NESTED_M):
    """The real OMOP shape: forEach group -> nested forEach element."""
    return {
        "resourceType": "ConceptMap",
        "id": "nested",
        "status": "active",
        "group": [
            {
                "source": f"http://example.org/cs-{g}",
                "target": "urn:omop:concept",
                "element": [
                    {
                        "code": str(1_000_000 * (g + 1) + i),
                        "target": [{"code": str(2_000_000 + i), "equivalence": "relatedto"}],
                    }
                    for i in range(per_group)
                ],
            }
            for g in range(groups)
        ],
    }


def _capped_connection():
    con = fhir4ds.create_connection()
    # Deterministic OOM for O(N x payload) lowerings; no disk spill.
    con.execute("SET memory_limit='1GB'")
    con.execute("SET temp_directory=''")
    con.execute("CREATE TABLE resources (resource JSON)")
    return con


def _foreach_vd():
    return parse_view_definition(
        {
            "resource": "ConceptMap",
            "select": [
                {
                    "forEach": "group.element",
                    "column": [
                        {"name": "code", "path": "code", "type": "string"},
                        {"name": "cid", "path": "target.code.first()", "type": "string"},
                        {"name": "idx", "path": "%rowIndex", "type": "integer"},
                    ],
                }
            ],
        }
    )


class TestLargeCollectionUnnest:
    def test_foreach_over_large_array_is_memory_bounded(self):
        con = _capped_connection()
        con.execute("INSERT INTO resources VALUES (?)", [json.dumps(_big_resource())])
        sql = SQLGenerator(source_table="resources").generate(_foreach_vd())
        rows = con.execute(sql).fetchall()
        assert len(rows) == BIG_N
        # first and last element (order preserved via the zipped index)
        assert rows[0] == ("2700000", "37000000", 0)
        assert rows[-1] == (str(2_700_000 + BIG_N - 1), str(37_000_000 + BIG_N - 1), BIG_N - 1)

    def test_foreachornull_over_large_array_is_memory_bounded(self):
        con = _capped_connection()
        con.execute("INSERT INTO resources VALUES (?)", [json.dumps(_big_resource())])
        vd = parse_view_definition(
            {
                "resource": "ConceptMap",
                "select": [
                    {
                        "forEachOrNull": "group.element",
                        "column": [{"name": "code", "path": "code", "type": "string"}],
                    }
                ],
            }
        )
        rows = con.execute(SQLGenerator(source_table="resources").generate(vd)).fetchall()
        assert len(rows) == BIG_N

    def test_foreachornull_empty_still_emits_null_row(self):
        con = _capped_connection()
        resource = {"resourceType": "ConceptMap", "id": "empty", "status": "active",
                    "group": [{"source": "x", "element": []}]}
        con.execute("INSERT INTO resources VALUES (?)", [json.dumps(resource)])
        vd = parse_view_definition(
            {
                "resource": "ConceptMap",
                "select": [
                    {
                        "forEachOrNull": "group.element",
                        "column": [{"name": "code", "path": "code", "type": "string"}],
                    }
                ],
            }
        )
        rows = con.execute(SQLGenerator(source_table="resources").generate(vd)).fetchall()
        assert rows == [(None,)]


class TestNestedForEachLargeCollections:
    """The real ConceptMap shape: forEach group -> nested forEach element.

    Before the fix this OOMed at a 2 GB cap even at 4 x 5k elements because
    every unnest level re-evaluated the full fhirpath expression against the
    whole resource JSON per output row (O(N x payload)).
    """

    def _vd(self):
        return parse_view_definition(
            {
                "resource": "ConceptMap",
                "select": [
                    {
                        "forEach": "group",
                        "column": [{"name": "source", "path": "source", "type": "string"}],
                        "select": [
                            {
                                "forEach": "element",
                                "column": [
                                    {"name": "code", "path": "code", "type": "string"},
                                    {"name": "cid", "path": "target.code.first()", "type": "string"},
                                ],
                            }
                        ],
                    }
                ],
            }
        )

    def test_nested_foreach_is_memory_bounded(self):
        con = _capped_connection()
        con.execute("INSERT INTO resources VALUES (?)", [json.dumps(_nested_resource())])
        rows = con.execute(
            SQLGenerator(source_table="resources").generate(self._vd())
        ).fetchall()
        assert len(rows) == 4 * NESTED_M
        # row-parity spot checks across all four groups (document order)
        assert rows[0] == ("http://example.org/cs-0", "1000000", "2000000")
        assert rows[NESTED_M - 1][1] == str(1_000_000 + NESTED_M - 1)
        assert rows[NESTED_M] == ("http://example.org/cs-1", "2000000", "2000000")
        assert rows[-1] == ("http://example.org/cs-3", str(4_000_000 + NESTED_M - 1), str(2_000_000 + NESTED_M - 1))

    def test_smoke_perf_large_foreach_under_budget(self):
        """CI-safe perf gate: bounded N, hard time budget, no full OOM wait.

        At SMOKE_N=20k the pre-fix lowering takes ~30 s / 39 GB (measured);
        with a 1 GB memory cap and no spill it OOMs instead. Either failure
        mode (OOM or exceeding the time budget) fails this test, so the
        O(N x payload) pathology cannot silently return.
        """
        con = _capped_connection()
        con.execute(
            "INSERT INTO resources VALUES (?)", [json.dumps(_big_resource(SMOKE_N))]
        )
        t0 = time.monotonic()
        rows = con.execute(
            SQLGenerator(source_table="resources").generate(_foreach_vd())
        ).fetchall()
        elapsed = time.monotonic() - t0
        assert len(rows) == SMOKE_N
        assert elapsed < SMOKE_TIME_BUDGET_S, (
            f"forEach over {SMOKE_N} elements took {elapsed:.1f}s "
            f"(budget {SMOKE_TIME_BUDGET_S}s) - O(N x payload) regression"
        )


class TestUnnestJsonTypingParity:
    """Element JSON typing must match the pre-fix json_extract semantics."""

    def _patient(self, con):
        con.execute("INSERT INTO resources VALUES (?)", [json.dumps({
            "resourceType": "Patient", "id": "p1",
            "name": [{"use": "official", "family": "Chalmers", "given": ["Peter", "James"]}],
        })])

    def test_complex_element_type_guard(self):
        con = fhir4ds.create_connection()
        con.execute("CREATE TABLE resources (resource JSON)")
        self._patient(con)
        vd = parse_view_definition({
            "resource": "Patient",
            "select": [{
                "forEach": "name",
                "column": [
                    {"name": "family", "path": "family", "type": "string"},
                    {"name": "typename", "path": "type().name", "type": "string"},
                ],
            }],
        })
        rows = con.execute(SQLGenerator(source_table="resources").generate(vd)).fetchall()
        assert rows == [("Chalmers", "object")]

    def test_primitive_element_dollar_this(self):
        con = fhir4ds.create_connection()
        con.execute("CREATE TABLE resources (resource JSON)")
        self._patient(con)
        vd = parse_view_definition({
            "resource": "Patient",
            "select": [{
                "forEach": "name.given",
                "column": [{"name": "given", "path": "$this", "type": "string"}],
            }],
        })
        rows = con.execute(SQLGenerator(source_table="resources").generate(vd)).fetchall()
        assert rows == [("Peter",), ("James",)]
