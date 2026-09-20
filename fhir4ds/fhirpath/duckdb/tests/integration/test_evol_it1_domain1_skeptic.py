"""Regression tests: Evolution iter 1 Domain 1 SKEPTIC findings.

QA-001: fhirpath_bool native/fallback parity on Decimal-typed zero/one
        results (one.ln() -> Decimal 0.0, zero.sqrt() -> Decimal 0.0).
        Native converts via its numeric branch (False); the Python
        fallback previously only recognized int/float and returned None.
QA-002: empty expression string must be row-resilient empty/NULL across
        ALL wrapper UDFs on BOTH engines (native used to throw
        "FHIRPath expression cannot be empty", killing the query).
"""

from __future__ import annotations

import json

import duckdb
import pytest

from fhir4ds.fhirpath.duckdb import register_fhirpath


def _cpp_connection() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(config={"allow_unsigned_extensions": True})
    assert register_fhirpath(con) is True
    return con


def _python_fallback_connection(monkeypatch) -> duckdb.DuckDBPyConnection:
    monkeypatch.setattr(duckdb, "__version__", "0.0.0-forced-python-fallback")
    con = duckdb.connect(config={"allow_unsigned_extensions": True})
    assert register_fhirpath(con) is False
    return con


RESOURCE = json.dumps(
    {"resourceType": "Observation", "i": -5, "d": -2.5, "p": 2.5, "zero": 0, "one": 1}
)

# (expression, expected fhirpath_bool value) — Decimal-zero results
DECIMAL_ZERO_BOOL_CASES = [
    ("one.ln()", False),          # Decimal('0.0')
    ("zero.sqrt()", False),       # Decimal('0.0')
    ("i.abs() - 5", False),       # Decimal 0 via arithmetic
]

DECIMAL_NONZERO_BOOL_CASES = [
    ("p.log(10)", None),          # Decimal 0.39794... -> NULL
    ("one.exp()", None),          # Decimal 2.718... -> NULL
    ("d.abs()", None),            # Decimal 2.5 -> NULL
]


@pytest.mark.parametrize("expression,expected", DECIMAL_ZERO_BOOL_CASES)
def test_fhirpath_bool_decimal_zero_parity_evol_it1(
    monkeypatch, expression: str, expected
) -> None:
    cpp = _cpp_connection()
    py = _python_fallback_connection(monkeypatch)
    try:
        cpp_val = cpp.execute(
            "SELECT fhirpath_bool(?::JSON, ?)", [RESOURCE, expression]
        ).fetchone()[0]
        py_val = py.execute(
            "SELECT fhirpath_bool(?::JSON, ?)", [RESOURCE, expression]
        ).fetchone()[0]
        assert cpp_val == expected
        assert py_val == expected
    finally:
        cpp.close()
        py.close()


@pytest.mark.parametrize("expression,expected", DECIMAL_NONZERO_BOOL_CASES)
def test_fhirpath_bool_decimal_nonzero_parity_evol_it1(
    monkeypatch, expression: str, expected
) -> None:
    cpp = _cpp_connection()
    py = _python_fallback_connection(monkeypatch)
    try:
        cpp_val = cpp.execute(
            "SELECT fhirpath_bool(?::JSON, ?)", [RESOURCE, expression]
        ).fetchone()[0]
        py_val = py.execute(
            "SELECT fhirpath_bool(?::JSON, ?)", [RESOURCE, expression]
        ).fetchone()[0]
        assert cpp_val == expected
        assert py_val == expected
    finally:
        cpp.close()
        py.close()


@pytest.mark.parametrize(
    "udf,expected",
    [
        ("fhirpath", []),
        ("fhirpath_text", None),
        ("fhirpath_number", None),
        ("fhirpath_bool", None),
        ("fhirpath_date", None),
        ("fhirpath_json", None),
    ],
)
def test_empty_expression_row_resilient_both_engines_evol_it1(
    monkeypatch, udf: str, expected
) -> None:
    """Empty expression must NOT raise on either engine (QA-002)."""
    cpp = _cpp_connection()
    py = _python_fallback_connection(monkeypatch)
    try:
        cpp_val = cpp.execute(
            f"SELECT {udf}(?::JSON, '')", [RESOURCE]
        ).fetchone()[0]
        py_val = py.execute(
            f"SELECT {udf}(?::JSON, '')", [RESOURCE]
        ).fetchone()[0]
        assert cpp_val == expected
        assert py_val == expected
    finally:
        cpp.close()
        py.close()
