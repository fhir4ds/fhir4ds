"""Regression tests for SQL-on-FHIR v2 Select.repeat (SOF-VD-07).

SOF-VD-07 EXPLORER QA-001: genuine elements whose only content is an
``extension`` (valid FHIR: backbone elements / nested Extensions without
``url``) must survive FHIRPath navigation so ``repeat`` emits one row per
recursively collected node. Previously a top-level post-filter dropped any
ResourceNode whose data keys were exactly ``['extension']``, which silently
dropped rows from repeat (and repeat->forEach stacks).
"""

import json
import re

import pytest

from ... import parse_view_definition, SQLGenerator

try:
    import duckdb
    from fhir4ds.fhirpath.duckdb import register_fhirpath
    from fhir4ds import fhirpath
    HAS_DUCKDB = True
except ImportError:
    HAS_DUCKDB = False
    pytestmark = pytest.mark.skip(reason="duckdb or fhirpath not available")


@pytest.fixture(scope="module")
def con():
    connection = duckdb.connect()
    register_fhirpath(connection)
    yield connection
    connection.close()


def _run_view(con, view, resources, resource_type="Patient"):
    vd = parse_view_definition(json.dumps(view))
    sql = SQLGenerator(strict_collection=True).generate(vd)
    con.execute("CREATE OR REPLACE TABLE resources (resource JSON)")
    for r in resources:
        con.execute("INSERT INTO resources VALUES (?)", [json.dumps(r)])
    sql = re.sub(
        r"FROM\s+\w+\s+t\b",
        "FROM (SELECT resource FROM resources "
        f"WHERE resource->>'resourceType' = '{resource_type}') t",
        sql,
    )
    return con.execute(sql).fetchall()


class TestRepeatExtensionOnlyElements:
    """QA-001: extension-only elements must not be dropped from repeat rows."""

    def test_fhirpath_navigation_keeps_extension_only_element(self):
        resource = {
            "resourceType": "Patient",
            "extension": [{"url": "a"}, {"extension": [{"url": "c"}]}],
        }
        result = fhirpath.evaluate(resource, "extension")
        assert json.dumps(result) == json.dumps(
            [{"url": "a"}, {"extension": [{"url": "c"}]}]
        )

    def test_fhirpath_navigation_shadow_primitive_extension_still_hidden(self):
        resource = {
            "resourceType": "Patient",
            "_birthDate": {"extension": [{"url": "http://example.org/x"}]},
        }
        assert fhirpath.evaluate(resource, "birthDate") == []

    def test_repeat_collects_extension_only_wrapper_and_children(self, con):
        resource = {
            "resourceType": "Patient",
            "extension": [{"url": "a"}, {"url": "b"},
                          {"extension": [{"url": "c"}]}],
        }
        view = {
            "resource": "Patient",
            "select": [{
                "repeat": ["extension"],
                "column": [{"name": "u", "path": "url"}],
            }],
        }
        rows = _run_view(con, view, [resource])
        urls = [r[0] for r in rows]
        # Depth-first: a, b, wrapper (no url), then nested c.
        assert urls == ["a", "b", None, "c"]

    def test_repeat_foreach_stack_reaches_nested_extension(self, con):
        resource = {
            "resourceType": "Patient",
            "extension": [{"url": "a"}, {"url": "b"},
                          {"extension": [{"url": "c"}]}],
        }
        view = {
            "resource": "Patient",
            "select": [{
                "repeat": ["extension"],
                "select": [{
                    "forEach": "extension",
                    "column": [{"name": "u", "path": "url"}],
                }],
            }],
        }
        rows = _run_view(con, view, [resource])
        # Only the extension-only wrapper has a nested extension to iterate.
        assert rows == [("c",)]


class TestRepeatUnionSemantics:
    """Multiple repeat paths combine with union (dedup) semantics."""

    def test_multiple_paths_union_no_duplicates(self, con):
        resource = {
            "resourceType": "Patient",
            "extension": [
                {"url": "outer", "extension": [{"url": "inner"}]},
            ],
        }
        # Both paths reach the inner extension: "extension" recursively, and
        # "extension.extension" at the root. Union dedup must emit it once.
        view = {
            "resource": "Patient",
            "select": [{
                "repeat": ["extension", "extension.extension"],
                "column": [{"name": "u", "path": "url"}],
            }],
        }
        rows = _run_view(con, view, [resource])
        assert [r[0] for r in rows] == ["outer", "inner"]

    def test_subtree_isomorphism_dedup(self, con):
        resource = {
            "resourceType": "Questionnaire",
            "item": [
                {"text": "same", "item": [{"text": "same2"}]},
                {"item": [{"text": "same", "item": [{"text": "same2"}]}]},
            ],
        }
        view = {
            "resource": "Questionnaire",
            "select": [{
                "repeat": ["item"],
                "column": [{"name": "t", "path": "text"}],
            }],
        }
        rows = _run_view(con, view, [resource], "Questionnaire")
        # Identical subtree at a deeper level collapses (value-dedup).
        assert [r[0] for r in rows] == ["same", "same2", None]

    def test_row_index_under_repeat(self, con):
        resource = {
            "resourceType": "Patient",
            "extension": [{"url": "a"}, {"url": "b"}],
        }
        view = {
            "resource": "Patient",
            "select": [{
                "repeat": ["extension"],
                "column": [
                    {"name": "u", "path": "url"},
                    {"name": "ri", "path": "%rowIndex"},
                ],
            }],
        }
        rows = _run_view(con, view, [resource])
        assert rows == [("a", 0), ("b", 1)]
