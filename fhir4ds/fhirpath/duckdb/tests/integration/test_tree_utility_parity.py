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
        ("descendants().count()", ["5"], "[5]"),
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
