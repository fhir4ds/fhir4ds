"""Parity tests for FHIRPath math functions in DuckDB UDFs."""

from __future__ import annotations

import json

import duckdb

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


def _cpp_connection() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(config={"allow_unsigned_extensions": True})
    assert register_fhirpath(con) is True
    return con


def _python_fallback_connection(monkeypatch) -> duckdb.DuckDBPyConnection:
    monkeypatch.setattr(duckdb, "__version__", "0.0.0-forced-python-fallback")
    con = duckdb.connect(config={"allow_unsigned_extensions": True})
    assert register_fhirpath(con) is False
    return con


def test_math_functions_match_cpp() -> None:
    resource = json.dumps(
        {
            "resourceType": "Observation",
            "i": -5,
            "d": -2.5,
            "p": 2.5,
            "zero": 0,
            "one": 1,
        }
    )
    expressions = [
        "i.abs()",
        "d.abs()",
        "p.ceiling()",
        "d.ceiling()",
        "p.floor()",
        "d.floor()",
        "p.truncate()",
        "d.truncate()",
        "p.round()",
        "p.round(1)",
        "p.round(0)",
        "3.14159.round(3)",
        "3.14159.abs()",
        "(-3.14159).abs()",
        "d.round()",
        "one.exp()",
        "one.ln()",
        "p.log(10)",
        "p.power(2)",
        "p.sqrt()",
        "zero.sqrt()",
        "d.sqrt()",
        "zero.ln()",
        "zero.log(10)",
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


def test_math_argument_validation_matches_forced_python_fallback(monkeypatch) -> None:
    resource = json.dumps(
        {
            "resourceType": "Observation",
            "p": 2.5,
        }
    )
    expressions = [
        "10.log((2 | 3))",
        "2.power((3 | 4))",
        "p.round((2 | 3))",
        "p.round(-1)",
        "p.round(1.5)",
        "p.round('x')",
        "p.round(true)",
    ]

    cpp = _cpp_connection()
    py = _python_fallback_connection(monkeypatch)
    try:
        for expression in expressions:
            cpp_result = cpp.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_text(?::JSON, ?), fhirpath_number(?::JSON, ?), fhirpath_json(?::JSON, ?)",
                [resource, expression, resource, expression, resource, expression, resource, expression],
            ).fetchone()
            py_result = py.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_text(?::JSON, ?), fhirpath_number(?::JSON, ?), fhirpath_json(?::JSON, ?)",
                [resource, expression, resource, expression, resource, expression, resource, expression],
            ).fetchone()
            assert cpp_result == py_result == ([], None, None, None), expression
    finally:
        cpp.close()
        py.close()


def test_only_abs_accepts_quantity_math_input_in_cpp_and_fallback(monkeypatch) -> None:
    resource = json.dumps({"resourceType": "Observation"})
    cases = {
        "(-5.5 'mg').abs()": (["5.5 'mg'"], "5.5 'mg'", '[{"value":5.5,"unit":"mg"}]'),
        "(-5.5 'mg').ceiling()": ([], None, None),
        "(-5.5 'mg').floor()": ([], None, None),
        "(-5.5 'mg').truncate()": ([], None, None),
        "(-5.55 'mg').round(1)": ([], None, None),
        "(5.5 'mg').ln()": ([], None, None),
        "(5.5 'mg').log(10)": ([], None, None),
        "(5.5 'mg').power(2)": ([], None, None),
        "(5.5 'mg').sqrt()": ([], None, None),
    }

    cpp = _cpp_connection()
    py = _python_fallback_connection(monkeypatch)
    try:
        for expression, expected in cases.items():
            cpp_result = cpp.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_text(?::JSON, ?), fhirpath_json(?::JSON, ?)",
                [resource, expression, resource, expression, resource, expression],
            ).fetchone()
            py_result = py.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_text(?::JSON, ?), fhirpath_json(?::JSON, ?)",
                [resource, expression, resource, expression, resource, expression],
            ).fetchone()
            assert cpp_result == py_result == expected, expression
    finally:
        cpp.close()
        py.close()
