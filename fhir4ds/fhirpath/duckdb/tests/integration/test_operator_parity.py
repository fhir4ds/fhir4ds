"""Parity tests for FHIRPath operator/null semantics in DuckDB UDFs."""

from __future__ import annotations

import json

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


RESOURCE = json.dumps(
    {
        "resourceType": "Patient",
        "id": "p",
        "active": True,
        "gender": "female",
        "zero": 0,
        "boolText": "false",
        "name": [{"given": ["Ann", "Beth"], "family": "Smith"}],
    }
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


def _all_udfs(con: duckdb.DuckDBPyConnection, resource: str, expression: str):
    return con.execute(
        """
        SELECT
            fhirpath(?::JSON, ?),
            fhirpath_text(?::JSON, ?),
            fhirpath_json(?::JSON, ?),
            fhirpath_bool(?::JSON, ?),
            fhirpath_number(?::JSON, ?)
        """,
        [
            resource,
            expression,
            resource,
            expression,
            resource,
            expression,
            resource,
            expression,
            resource,
            expression,
        ],
    ).fetchone()


def test_decimal_json_and_iif_empty_criterion_match_python_fallback() -> None:
    expressions = ["6 / 2", "iif({}, 1, 2)"]

    con = _connection()
    try:
        for expression in expressions:
            cpp = con.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_text(?::JSON, ?), fhirpath_json(?::JSON, ?)",
                [RESOURCE, expression, RESOURCE, expression, RESOURCE, expression],
            ).fetchone()
            py = (
                fhirpath_scalar(RESOURCE, expression),
                fhirpath_text_udf(RESOURCE, expression),
                fhirpath_json_udf(RESOURCE, expression),
            )
            assert cpp == py
    finally:
        con.close()


def test_empty_collection_rhs_after_literal_operator_matches_python_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    expressions = ["'x' & {}", "'x' + {}"]

    cpp = _connection()
    py = _python_fallback_connection(monkeypatch)
    try:
        for expression in expressions:
            assert _all_udfs(cpp, RESOURCE, expression) == _all_udfs(py, RESOURCE, expression)
    finally:
        cpp.close()
        py.close()


def test_boolean_singleton_evaluation_matches_python_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    expressions = [
        "active and gender",
        "true and gender",
        "zero and true",
        "true and zero",
        "boolText and true",
        "gender or false",
        "gender xor false",
        "gender implies false",
        "false implies gender",
        "gender.not()",
        "iif(gender, 1, 2)",
    ]

    cpp = _connection()
    py = _python_fallback_connection(monkeypatch)
    try:
        for expression in expressions:
            assert _all_udfs(cpp, RESOURCE, expression) == _all_udfs(py, RESOURCE, expression)
    finally:
        cpp.close()
        py.close()


def test_python_fallback_scalar_uses_singleton_boolean_rules() -> None:
    cases = {
        "true and gender": (["true"], "true", "[true]", True, None),
        "zero and true": (["true"], "true", "[true]", True, None),
        "true and zero": (["true"], "true", "[true]", True, None),
        "boolText and true": (["true"], "true", "[true]", True, None),
        "gender.not()": (["false"], "false", "[false]", False, None),
        "iif(gender, 'yes', 'no')": (["yes"], "yes", '["yes"]', None, None),
    }

    for expression, expected in cases.items():
        assert (
            fhirpath_scalar(RESOURCE, expression),
            fhirpath_text_udf(RESOURCE, expression),
            fhirpath_json_udf(RESOURCE, expression),
            fhirpath_bool_udf(RESOURCE, expression),
            fhirpath_number_udf(RESOURCE, expression),
        ) == expected


def test_iif_rejects_multi_item_input_in_public_udfs(monkeypatch: pytest.MonkeyPatch) -> None:
    expression = "('a'|'b').iif(true, 'yes', 'no')"

    cpp = _connection()
    py = _python_fallback_connection(monkeypatch)
    try:
        assert _all_udfs(cpp, RESOURCE, expression) == ([], None, None, None, None)
        assert _all_udfs(cpp, RESOURCE, expression) == _all_udfs(py, RESOURCE, expression)
    finally:
        cpp.close()
        py.close()
