"""Parity tests for FHIRPath tree navigation and deterministic utility functions."""

from __future__ import annotations

import json
import time

import duckdb
import pytest

from fhir4ds.fhirpath.duckdb import register_fhirpath
from fhir4ds.fhirpath.duckdb.udf import (
    fhirpath_bool_udf,
    fhirpath_json_udf,
    fhirpath_number_udf,
    fhirpath_scalar,
    fhirpath_text_udf,
)


def _connection() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(config={"allow_unsigned_extensions": True})
    register_fhirpath(con)
    return con


def _python_fallback_connection(monkeypatch: pytest.MonkeyPatch) -> duckdb.DuckDBPyConnection:
    monkeypatch.setattr(duckdb, "__version__", "0.0.0-forced-python-fallback")
    con = duckdb.connect(config={"allow_unsigned_extensions": True})
    assert register_fhirpath(con) is False
    return con


def test_tree_navigation_and_trace_match_cpp() -> None:
    resource = json.dumps(
        {
            "resourceType": "Patient",
            "id": "p1",
            "active": True,
            "name": [{"given": ["Ann"], "family": "Smith"}],
            "contact": [{"telecom": [{"value": "555"}]}],
        }
    )
    expressions = [
        "children().count()",
        "descendants().where($this = 'Ann').count()",
        "name.children().count()",
        "name.descendants().where($this = 'Ann').count()",
        "id.trace('id')",
    ]

    con = _connection()
    try:
        for expression in expressions:
            cpp = con.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_text(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_bool(?::JSON, ?), fhirpath_number(?::JSON, ?)",
                [resource, expression, resource, expression, resource, expression, resource, expression, resource, expression],
            ).fetchone()
            py = (
                fhirpath_scalar(resource, expression),
                fhirpath_text_udf(resource, expression),
                fhirpath_json_udf(resource, expression),
                fhirpath_bool_udf(resource, expression),
                fhirpath_number_udf(resource, expression),
            )
            assert cpp == py
    finally:
        con.close()


def test_tree_navigation_preserves_null_children_in_native_and_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    resource = json.dumps(
        {
            "resourceType": "Patient",
            "id": "p1",
            "active": None,
            "name": [{"given": ["Ann"], "family": None}],
        }
    )
    expressions = [
        ("children().count()", ["3"], "[3]"),
        ("descendants().count()", ["4"], "[4]"),
        ("name.children().count()", ["2"], "[2]"),
        ("children()", ["p1", "", '{"given":["Ann"],"family":null}'], '["p1",null,{"given":["Ann"],"family":null}]'),
        ("name.children()", ["Ann", ""], '["Ann",null]'),
    ]

    native = _connection()
    fallback = _python_fallback_connection(monkeypatch)
    try:
        for expression, expected_list, expected_json in expressions:
            native_row = native.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_json(?::JSON, ?)",
                [resource, expression, resource, expression],
            ).fetchone()
            fallback_row = fallback.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_json(?::JSON, ?)",
                [resource, expression, resource, expression],
            ).fetchone()
            assert native_row == fallback_row
            assert native_row == (expected_list, expected_json)
    finally:
        native.close()
        fallback.close()


def test_descendants_is_repeat_children_for_repeated_values(monkeypatch: pytest.MonkeyPatch) -> None:
    resource = json.dumps(
        {
            "resourceType": "Patient",
            "id": "p1",
            "a": "x",
            "b": "x",
            "nested": {"c": "x"},
            "items": [{"v": "x"}, {"v": "x"}],
        }
    )

    native = _connection()
    fallback = _python_fallback_connection(monkeypatch)
    try:
        expression = "descendants().count() = repeat(children()).count()"
        for con in (native, fallback):
            assert con.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_is_valid(?)",
                [resource, expression, resource, expression, expression],
            ).fetchone() == (["true"], "[true]", True)

        count_expression = "descendants().count()"
        native_row = native.execute(
            "SELECT fhirpath(?::JSON, ?), fhirpath_json(?::JSON, ?)",
            [resource, count_expression, resource, count_expression],
        ).fetchone()
        fallback_row = fallback.execute(
            "SELECT fhirpath(?::JSON, ?), fhirpath_json(?::JSON, ?)",
            [resource, count_expression, resource, count_expression],
        ).fetchone()
        assert native_row == fallback_row == (["4"], "[4]")
    finally:
        native.close()
        fallback.close()


def test_descendants_matches_repeat_children_for_key_ordered_objects(monkeypatch: pytest.MonkeyPatch) -> None:
    resource = '{"resourceType":"Patient","a":{"x":1,"y":2},"b":{"y":2,"x":1}}'

    native = _connection()
    fallback = _python_fallback_connection(monkeypatch)
    try:
        for expression, expected in [
            ("descendants().count() = repeat(children()).count()", (["true"], "[true]", True)),
            ("descendants().count()", (["3"], "[3]", True)),
        ]:
            native_row = native.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_is_valid(?)",
                [resource, expression, resource, expression, expression],
            ).fetchone()
            fallback_row = fallback.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_is_valid(?)",
                [resource, expression, resource, expression, expression],
            ).fetchone()
            assert native_row == fallback_row == expected
    finally:
        native.close()
        fallback.close()


def test_descendants_traverses_deep_nested_resources(monkeypatch: pytest.MonkeyPatch) -> None:
    resource_obj = {"resourceType": "Patient", "id": "p1"}
    cursor = resource_obj
    for depth in range(105):
        cursor["child"] = {"valueString": f"v{depth}"}
        cursor = cursor["child"]
    resource = json.dumps(resource_obj)
    expression = "descendants().where($this = 'v104').count()"

    native = _connection()
    fallback = _python_fallback_connection(monkeypatch)
    try:
        native_row = native.execute(
            "SELECT fhirpath(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_is_valid(?)",
            [resource, expression, resource, expression, expression],
        ).fetchone()
        fallback_row = fallback.execute(
            "SELECT fhirpath(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_is_valid(?)",
            [resource, expression, resource, expression, expression],
        ).fetchone()
        assert native_row == fallback_row == (["1"], "[1]", True)
    finally:
        native.close()
        fallback.close()


def test_descendants_matches_repeat_children_for_split_primitive_json(monkeypatch: pytest.MonkeyPatch) -> None:
    resource = json.dumps(
        {
            "resourceType": "Patient",
            "id": "p1",
            "birthDate": "1970-01-01",
            "_birthDate": {
                "extension": [
                    {
                        "url": "http://example.org/ext/birth",
                        "valueString": "midday",
                    }
                ]
            },
            "name": [{"given": ["Ann"], "family": None}],
        }
    )
    expressions = [
        "descendants().where($this = 'midday').count()",
        "repeat(children()).where($this = 'midday').count()",
    ]

    native = _connection()
    fallback = _python_fallback_connection(monkeypatch)
    try:
        for expression in expressions:
            native_row = native.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_is_valid(?)",
                [resource, expression, resource, expression, expression],
            ).fetchone()
            fallback_row = fallback.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_is_valid(?)",
                [resource, expression, resource, expression, expression],
            ).fetchone()
            assert native_row == fallback_row

        primitive_extension_descendants = native.execute(
            "SELECT fhirpath(?::JSON, ?), fhirpath_json(?::JSON, ?)",
            [
                resource,
                "descendants().where($this = 'midday').count()",
                resource,
                "descendants().where($this = 'midday').count()",
            ],
        ).fetchone()
        assert primitive_extension_descendants == (["1"], "[1]")
    finally:
        native.close()
        fallback.close()


def test_primitive_extension_metadata_is_visible_to_tree_navigation(monkeypatch: pytest.MonkeyPatch) -> None:
    resource = json.dumps(
        {
            "resourceType": "Patient",
            "id": "p1",
            "birthDate": "1970-01-01",
            "_birthDate": {
                "extension": [
                    {
                        "url": "http://example.org/fhir/StructureDefinition/birth-note",
                        "valueString": "midday",
                    }
                ]
            },
            "name": [
                {
                    "given": ["Ann"],
                    "_given": [
                        {
                            "extension": [
                                {
                                    "url": "http://example.org/fhir/StructureDefinition/given-note",
                                    "valueString": "alias",
                                }
                            ]
                        }
                    ],
                    "family": "Able",
                }
            ],
        }
    )
    expressions = [
        (
            "birthDate.children().where(url = 'http://example.org/fhir/StructureDefinition/birth-note').valueString",
            (["midday"], '["midday"]', True),
        ),
        (
            "birthDate.descendants().where($this = 'midday').count()",
            (["1"], "[1]", True),
        ),
        (
            "name.given.extension('http://example.org/fhir/StructureDefinition/given-note').valueString",
            (["alias"], '["alias"]', True),
        ),
        (
            "name.given.children().where(url = 'http://example.org/fhir/StructureDefinition/given-note').valueString",
            (["alias"], '["alias"]', True),
        ),
        (
            "name.given.descendants().where($this = 'alias').count()",
            (["1"], "[1]", True),
        ),
    ]

    native = _connection()
    fallback = _python_fallback_connection(monkeypatch)
    try:
        for expression, expected in expressions:
            native_row = native.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_is_valid(?)",
                [resource, expression, resource, expression, expression],
            ).fetchone()
            fallback_row = fallback.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_is_valid(?)",
                [resource, expression, resource, expression, expression],
            ).fetchone()
            assert native_row == fallback_row == expected
    finally:
        native.close()
        fallback.close()


def test_current_time_functions_are_stable_within_native_expression(monkeypatch: pytest.MonkeyPatch) -> None:
    resource = json.dumps(
        {
            "resourceType": "Patient",
            "id": "p1",
            "extension": [{"url": str(i), "valueString": "x"} for i in range(40000)],
        }
    )
    slow_condition = " and ".join(["descendants().count() > 0"] * 8)
    expression = f"now() = iif({slow_condition}, now(), now())"

    native = _connection()
    fallback = _python_fallback_connection(monkeypatch)
    try:
        deadline = time.time() + 2.0
        while time.time() < deadline and time.time() % 1 < 0.75:
            time.sleep(0.001)

        native_result = native.execute(
            "SELECT fhirpath_bool(?::JSON, ?)",
            [resource, expression],
        ).fetchone()[0]
        fallback_result = fallback.execute(
            "SELECT fhirpath_bool(?::JSON, ?)",
            [resource, expression],
        ).fetchone()[0]

        assert native_result is True
        assert native_result == fallback_result
    finally:
        native.close()
        fallback.close()


def test_tree_utility_invalid_signatures_match_python_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    resource = json.dumps({"resourceType": "Patient", "id": "p1", "name": [{"given": ["Ann"]}]})
    expressions = [
        "children(1)",
        "descendants(1)",
        "trace()",
        "trace(1)",
        "trace('x', id, id)",
        "now(1)",
        "today(1)",
        "timeOfDay(1)",
    ]

    native = _connection()
    fallback = _python_fallback_connection(monkeypatch)
    try:
        for expression in expressions:
            native_row = native.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_is_valid(?)",
                [resource, expression, resource, expression, expression],
            ).fetchone()
            fallback_row = fallback.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_is_valid(?)",
                [resource, expression, resource, expression, expression],
            ).fetchone()
            assert native_row == fallback_row == ([], None, False)
    finally:
        native.close()
        fallback.close()


def test_trace_projection_is_validated_in_native_and_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    resource = json.dumps({"resourceType": "Patient", "id": "p1", "name": [{"given": ["Ann"]}]})

    native = _connection()
    fallback = _python_fallback_connection(monkeypatch)
    try:
        for expression, expected in [
            ("name.trace('names', given).given.count() = 1", (["true"], "[true]", True)),
            ("name.trace('names', given.single()).given.count() = 1", (["true"], "[true]", True)),
            ("name.trace(id).given.count() = 1", (["true"], "[true]", True)),
        ]:
            native_row = native.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_is_valid(?)",
                [resource, expression, resource, expression, expression],
            ).fetchone()
            fallback_row = fallback.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_is_valid(?)",
                [resource, expression, resource, expression, expression],
            ).fetchone()
            assert native_row == fallback_row == expected

        multi_given_resource = json.dumps(
            {"resourceType": "Patient", "id": "p1", "name": [{"given": ["Ann", "A"]}]}
        )
        expression = "name.trace('names', given.single()).given.count() = 2"
        native_row = native.execute(
            "SELECT fhirpath(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_is_valid(?)",
            [multi_given_resource, expression, multi_given_resource, expression, expression],
        ).fetchone()
        fallback_row = fallback.execute(
            "SELECT fhirpath(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_is_valid(?)",
            [multi_given_resource, expression, multi_given_resource, expression, expression],
        ).fetchone()
        assert native_row == fallback_row == ([], None, True)
    finally:
        native.close()
        fallback.close()


def test_trace_projection_is_scoped_per_item_in_native_and_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    resource = json.dumps(
        {
            "resourceType": "Patient",
            "id": "p1",
            "name": [
                {"given": ["Ann"], "family": "Able"},
                {"given": ["Bob"], "family": "Baker"},
            ],
        }
    )

    native = _connection()
    fallback = _python_fallback_connection(monkeypatch)
    try:
        for expression in [
            "name.trace('names', given.single()).given.count() = 2",
            "name.trace('idx', $index.single()).given.count() = 2",
        ]:
            native_row = native.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_is_valid(?)",
                [resource, expression, resource, expression, expression],
            ).fetchone()
            fallback_row = fallback.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_is_valid(?)",
                [resource, expression, resource, expression, expression],
            ).fetchone()
            assert native_row == fallback_row == (["true"], "[true]", True)
    finally:
        native.close()
        fallback.close()
