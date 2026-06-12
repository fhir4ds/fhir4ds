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


def _all_public_outputs_with_valid(con: duckdb.DuckDBPyConnection, resource: str, expression: str):
    return con.execute(
        """
        SELECT
          fhirpath(?::JSON, ?),
          fhirpath_text(?::JSON, ?),
          fhirpath_json(?::JSON, ?),
          fhirpath_bool(?::JSON, ?),
          fhirpath_number(?::JSON, ?),
          fhirpath_is_valid(?)
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
            expression,
        ],
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
        "s.substring(1, -4)",
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


def test_string_search_invalid_arity_matches_python_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    resource = json.dumps({"resourceType": "Patient", "s": "abcdef"})
    expressions = [
        "s.indexOf()",
        "s.indexOf('a', 'b')",
        "s.substring()",
        "s.substring(1, 2, 3)",
        "s.startsWith()",
        "s.startsWith('a', 'b')",
        "s.endsWith()",
        "s.endsWith('f', 'b')",
        "s.contains()",
        "s.contains('b', 'c')",
    ]

    native = _connection()
    fallback = _python_fallback_connection(monkeypatch)
    try:
        for expression in expressions:
            assert _all_public_outputs_with_valid(native, resource, expression) == (
                [],
                None,
                None,
                None,
                None,
                False,
            )
            assert _all_public_outputs_with_valid(fallback, resource, expression) == (
                [],
                None,
                None,
                None,
                None,
                False,
            )
    finally:
        native.close()
        fallback.close()


def test_string_search_constant_wrong_types_are_invalid_in_native_and_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resource = json.dumps({"resourceType": "Patient"})
    expressions = [
        "'abc'.contains(1)",
        "'abc'.startsWith(1)",
        "'abc'.endsWith(1)",
        "1.indexOf('1')",
        "1.contains('1')",
        "'abc'.substring('1')",
        "'abc'.substring(1.5)",
        "'abc'.substring(1, '2')",
        "'abc'.substring(1, 2.5)",
    ]

    native = _connection()
    fallback = _python_fallback_connection(monkeypatch)
    try:
        for expression in expressions:
            assert _all_public_outputs_with_valid(native, resource, expression) == (
                [],
                None,
                None,
                None,
                None,
                False,
            )
            assert _all_public_outputs_with_valid(fallback, resource, expression) == (
                [],
                None,
                None,
                None,
                None,
                False,
            )
    finally:
        native.close()
        fallback.close()


def test_string_search_arguments_resolve_in_outer_focus(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resource = json.dumps(
        {
            "resourceType": "Patient",
            "s": "abcdef",
            "term": "cd",
            "prefix": "ab",
            "suffix": "ef",
            "start": 2,
            "length": 3,
            "num": 123,
            "terms": ["a", "b"],
            "lens": [1, 2],
            "negLen": -4,
            "decLen": 1.5,
        }
    )
    expressions = [
        "s.indexOf(term)",
        "s.substring(start)",
        "s.substring(start, length)",
        "s.startsWith(prefix)",
        "s.endsWith(suffix)",
        "s.contains(term)",
        "s.indexOf(num)",
        "s.indexOf(terms)",
        "s.substring(1, lens)",
        "s.substring(1, negLen)",
        "s.substring(1, decLen)",
    ]

    native = _connection()
    fallback = _python_fallback_connection(monkeypatch)
    try:
        for expression in expressions:
            assert _all_public_outputs(native, resource, expression) == _all_public_outputs(
                fallback, resource, expression
            )
        assert _all_public_outputs(native, resource, "s.indexOf(term)")[4] == 2.0
        assert _all_public_outputs(native, resource, "s.substring(start, length)")[1] == "cde"
        assert _all_public_outputs(native, resource, "s.substring(1, negLen)")[1] == ""
        assert _all_public_outputs(native, resource, "s.startsWith(prefix)")[3] is True
        assert _all_public_outputs(native, resource, "s.endsWith(suffix)")[3] is True
        assert _all_public_outputs(native, resource, "s.contains(term)")[3] is True
    finally:
        native.close()
        fallback.close()


def test_string_search_literal_union_argument_validation_matches_native(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resource = json.dumps({"resourceType": "Patient", "s": "abcdef"})
    cases = {
        "s.indexOf(('a'|'a'))": (["0"], "0", "[0]", False, 0.0, True),
        "s.indexOf(('a'|'b'))": ([], None, None, None, None, False),
        "s.substring((1|1))": (["bcdef"], "bcdef", '["bcdef"]', None, None, True),
        "s.substring((1|2))": ([], None, None, None, None, False),
        "s.substring(1, (1|1))": (["b"], "b", '["b"]', None, None, True),
        "s.substring(1, (1|2))": ([], None, None, None, None, False),
        "s.substring((1|1.0))": (["bcdef"], "bcdef", '["bcdef"]', None, None, True),
        "s.substring((1.0|1))": ([], None, None, None, None, False),
        "s.substring((1|1.0), (1|1.0))": (["b"], "b", '["b"]', None, None, True),
        "missing.indexOf(('a'|'b'))": ([], None, None, None, None, False),
        "missing.substring((1|2))": ([], None, None, None, None, False),
    }

    native = _connection()
    fallback = _python_fallback_connection(monkeypatch)
    try:
        for expression, expected in cases.items():
            assert _all_public_outputs_with_valid(native, resource, expression) == expected
            assert _all_public_outputs_with_valid(fallback, resource, expression) == expected
    finally:
        native.close()
        fallback.close()
