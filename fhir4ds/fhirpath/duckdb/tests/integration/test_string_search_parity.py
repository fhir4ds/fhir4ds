"""Parity tests for FHIRPath string search functions in DuckDB UDFs."""

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


def _connection() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(config={"allow_unsigned_extensions": True})
    register_fhirpath(con)
    return con


def _python_fallback_connection(monkeypatch: pytest.MonkeyPatch) -> duckdb.DuckDBPyConnection:
    monkeypatch.setattr(duckdb, "__version__", "0.0.0-forced-python-fallback")
    con = duckdb.connect(config={"allow_unsigned_extensions": True})
    assert register_fhirpath(con) is False
    return con


def _all_public_outputs(con: duckdb.DuckDBPyConnection, resource: str, expression: str):
    return con.execute(
        "SELECT fhirpath(?::JSON, ?), fhirpath_text(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_bool(?::JSON, ?), fhirpath_number(?::JSON, ?)",
        [resource, expression, resource, expression, resource, expression, resource, expression, resource, expression],
    ).fetchone()


def test_string_search_functions_match_cpp() -> None:
    resource = json.dumps(
        {
            "resourceType": "Patient",
            "s": "abcdef",
            "empty": "",
            "unicode": "café",
        }
    )
    expressions = [
        "s.indexOf('cd')",
        "s.indexOf('zz')",
        "s.indexOf('')",
        "empty.indexOf('a')",
        "s.substring(0)",
        "s.substring(2)",
        "s.substring(2, 3)",
        "s.substring(6)",
        "s.substring(0, 0)",
        "s.substring(99)",
        "s.substring(-1)",
        "s.substring(1, -1)",
        "s.startsWith('ab')",
        "s.startsWith('bc')",
        "s.startsWith('')",
        "s.endsWith('ef')",
        "s.endsWith('de')",
        "s.endsWith('')",
        "s.contains('cd')",
        "s.contains('zz')",
        "s.contains('')",
        "unicode.indexOf('é')",
        "unicode.substring(3, 1)",
    ]

    con = _connection()
    try:
        for expression in expressions:
            cpp = _all_public_outputs(con, resource, expression)
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


def test_string_search_invalid_types_match_python_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    resource = json.dumps(
        {
            "resourceType": "Patient",
            "s": "abc123",
            "num": 123,
            "flag": True,
            "arr": ["abc", "def"],
            "obj": {"code": "abc"},
        }
    )
    expressions = [
        "s.indexOf(123)",
        "s.indexOf(true)",
        "s.startsWith(123)",
        "s.startsWith(true)",
        "s.endsWith(123)",
        "s.contains(123)",
        "s.contains(true)",
        "s.substring('1')",
        "s.substring(1.5)",
        "s.substring(true)",
        "s.substring(1, '2')",
        "s.substring(1, 2.5)",
        "num.contains('2')",
        "flag.contains('r')",
        "obj.contains('code')",
        "arr.contains('b')",
    ]

    native = _connection()
    fallback = _python_fallback_connection(monkeypatch)
    try:
        for expression in expressions:
            assert _all_public_outputs(native, resource, expression) == _all_public_outputs(
                fallback, resource, expression
            )
    finally:
        native.close()
        fallback.close()
