"""Parity tests for FHIRPath boolean logic operators."""

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


def _fallback_connection(monkeypatch: pytest.MonkeyPatch) -> duckdb.DuckDBPyConnection:
    monkeypatch.setattr(duckdb, "__version__", "0.0.0-forced-python-fallback")
    con = duckdb.connect()
    loaded = register_fhirpath(con)
    assert loaded is False
    return con


def test_boolean_logic_operators_match_cpp() -> None:
    resource = json.dumps(
        {
            "resourceType": "Patient",
            "t": True,
            "f": False,
            "arr": [True, False],
            "s": "x",
        }
    )
    expressions = [
        "t and t",
        "t and f",
        "f and t",
        "f and f",
        "t or f",
        "f or f",
        "t xor f",
        "t xor t",
        "t implies f",
        "f implies t",
        "not()",
        "t.not()",
        "f.not()",
        "{}.not()",
        "{} and t",
        "{} or t",
        "{} or f",
        "{} implies f",
        "t and {}",
        "f and {}",
        "arr and t",
        "s and t",
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


def test_multi_item_boolean_operands_return_empty_in_native_and_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resource = json.dumps(
        {
            "resourceType": "Patient",
            "t": True,
            "f": False,
            "arr": [True, False],
        }
    )
    expressions = [
        "arr or t",
        "arr and f",
        "arr implies t",
        "f implies arr",
        "t implies arr",
        "arr xor t",
        "arr.not()",
    ]

    native = _connection()
    fallback = _fallback_connection(monkeypatch)
    try:
        for expression in expressions:
            native_result = native.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_bool(?::JSON, ?)",
                [resource, expression, resource, expression, resource, expression],
            ).fetchone()
            fallback_result = fallback.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_bool(?::JSON, ?)",
                [resource, expression, resource, expression, resource, expression],
            ).fetchone()
            assert native_result == fallback_result == ([], None, None)
    finally:
        native.close()
        fallback.close()


@pytest.mark.parametrize(
    ("expression", "expected_json", "expected_bool"),
    [
        ("t and t", "[true]", True),
        ("t and f", "[false]", False),
        ("f and t", "[false]", False),
        ("f and f", "[false]", False),
        ("t and {}", None, None),
        ("f and {}", "[false]", False),
        ("{} and t", None, None),
        ("{} and f", "[false]", False),
        ("{} and {}", None, None),
        ("t or t", "[true]", True),
        ("t or f", "[true]", True),
        ("f or t", "[true]", True),
        ("f or f", "[false]", False),
        ("t or {}", "[true]", True),
        ("f or {}", None, None),
        ("{} or t", "[true]", True),
        ("{} or f", None, None),
        ("{} or {}", None, None),
        ("t xor t", "[false]", False),
        ("t xor f", "[true]", True),
        ("f xor t", "[true]", True),
        ("f xor f", "[false]", False),
        ("t xor {}", None, None),
        ("f xor {}", None, None),
        ("{} xor t", None, None),
        ("{} xor f", None, None),
        ("{} xor {}", None, None),
        ("t implies t", "[true]", True),
        ("t implies f", "[false]", False),
        ("t implies {}", None, None),
        ("f implies t", "[true]", True),
        ("f implies f", "[true]", True),
        ("f implies {}", "[true]", True),
        ("{} implies t", "[true]", True),
        ("{} implies f", None, None),
        ("{} implies {}", None, None),
        ("not()", "[false]", False),
        ("t.not()", "[false]", False),
        ("f.not()", "[true]", True),
        ("{}.not()", None, None),
    ],
)
def test_boolean_logic_truth_tables_native_and_fallback(
    expression: str,
    expected_json: str | None,
    expected_bool: bool | None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resource = json.dumps(
        {
            "resourceType": "Patient",
            "t": True,
            "f": False,
        }
    )
    expected_text = None if expected_bool is None else str(expected_bool).lower()

    native = _connection()
    fallback = _fallback_connection(monkeypatch)
    try:
        native_result = native.execute(
            "SELECT fhirpath_text(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_bool(?::JSON, ?)",
            [resource, expression, resource, expression, resource, expression],
        ).fetchone()
        fallback_result = fallback.execute(
            "SELECT fhirpath_text(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_bool(?::JSON, ?)",
            [resource, expression, resource, expression, resource, expression],
        ).fetchone()
        assert native_result == fallback_result == (expected_text, expected_json, expected_bool)
    finally:
        native.close()
        fallback.close()


@pytest.mark.parametrize(
    ("expression", "expected_json", "expected_bool"),
    [
        ("s and t", "[true]", True),
        ("s.not()", "[false]", False),
        ("t or f and f", "[true]", True),
        ("t xor t or t", "[true]", True),
        ("f implies f implies f", "[false]", False),
        ("f implies s", "[true]", True),
    ],
)
def test_boolean_logic_singleton_precedence_and_short_circuit_parity(
    expression: str,
    expected_json: str,
    expected_bool: bool,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resource = json.dumps(
        {
            "resourceType": "Patient",
            "t": True,
            "f": False,
            "s": "male",
            "arr": [True, False],
        }
    )
    expected_text = str(expected_bool).lower()

    native = _connection()
    fallback = _fallback_connection(monkeypatch)
    try:
        native_result = native.execute(
            "SELECT fhirpath_text(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_bool(?::JSON, ?)",
            [resource, expression, resource, expression, resource, expression],
        ).fetchone()
        fallback_result = fallback.execute(
            "SELECT fhirpath_text(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_bool(?::JSON, ?)",
            [resource, expression, resource, expression, resource, expression],
        ).fetchone()
        assert native_result == fallback_result == (expected_text, expected_json, expected_bool)
    finally:
        native.close()
        fallback.close()


@pytest.mark.parametrize(
    "expression",
    [
        "false implies (1 | 2)",
        "false implies iif(true, 1 | 2, 3)",
        "false implies iif(false, 1, 2 | 3)",
    ],
)
def test_implies_rejects_multi_item_rhs_before_false_short_circuit(
    expression: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resource = json.dumps(
        {
            "resourceType": "Patient",
            "f": False,
            "arr": [1, 2],
        }
    )

    native = _connection()
    fallback = _fallback_connection(monkeypatch)
    try:
        query = """
            SELECT
                fhirpath(?::JSON, ?),
                fhirpath_json(?::JSON, ?),
                fhirpath_bool(?::JSON, ?),
                fhirpath_is_valid(?)
        """
        params = [
            resource,
            expression,
            resource,
            expression,
            resource,
            expression,
            expression,
        ]
        native_result = native.execute(query, params).fetchone()
        fallback_result = fallback.execute(query, params).fetchone()
        assert native_result == fallback_result == ([], None, None, False)
    finally:
        native.close()
        fallback.close()


@pytest.mark.parametrize("expression", ["t.not(false)", "not(false)"])
def test_boolean_not_rejects_arguments_in_native_and_fallback(
    expression: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resource = json.dumps(
        {
            "resourceType": "Patient",
            "t": True,
        }
    )

    native = _connection()
    fallback = _fallback_connection(monkeypatch)
    try:
        native_result = native.execute(
            "SELECT fhirpath(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_bool(?::JSON, ?), fhirpath_is_valid(?)",
            [resource, expression, resource, expression, resource, expression, expression],
        ).fetchone()
        fallback_result = fallback.execute(
            "SELECT fhirpath(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_bool(?::JSON, ?), fhirpath_is_valid(?)",
            [resource, expression, resource, expression, resource, expression, expression],
        ).fetchone()
        assert native_result == fallback_result == ([], None, None, False)
    finally:
        native.close()
        fallback.close()
