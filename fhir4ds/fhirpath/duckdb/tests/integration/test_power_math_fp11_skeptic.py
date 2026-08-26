"""FP-11 SKEPTIC (2026-08-17) §5.7 Math regressions.

Covers the four issues fixed in this launch, all verified against the
FHIRPath N1 2.0.0 §5.7 normative text (spec/N1/index.adoc) and the STU3
functions.json:

- QA-001: power(Integer, Integer) -> Integer; negative Integer exponent
  on an Integer base -> empty.
- QA-002: exact Decimal arithmetic for Decimal-base power with integral
  exponents on BOTH engines (no binary64 noise like 1.2100000000000002).
- QA-003: round() never renders negative zero.
- QA-004: power with a non-integral exponent renders with the
  shortest-round-trip binary64 text (consistent with sqrt(), which the
  spec calls "equivalent to raising a number to the power of 0.5").
"""

from __future__ import annotations

import json

import duckdb
import pytest

from fhir4ds.fhirpath.duckdb import register_fhirpath
from fhir4ds.fhirpath.duckdb.tests.integration.test_math_parity import (
    _cpp_connection,
    _python_fallback_connection,
)


def _expr_text(con: duckdb.DuckDBPyConnection, resource: str, expr: str):
    row = con.execute(
        "SELECT fhirpath_text(?::JSON, ?)", [resource, expr]
    ).fetchone()
    return row[0]


@pytest.mark.parametrize(
    "expr,expected",
    [
        # QA-001: Integer in, Integer out (renders without ".0").
        ("2.power(3)", "8"),
        ("2.power(0)", "1"),
        ("(0-2).power(3)", "-8"),
        ("5.power(1)", "5"),
        ("2.power(3).type().name", "Integer"),
        # Mixture stays Decimal.
        ("2.0.power(3)", "8.0"),
        ("2.power(3.0)", "8.0"),
        ("2.5.power(2)", "6.25"),
        # Negative Integer exponent on Integer base: unrepresentable as
        # Integer -> empty (STU3 functions.json).
        ("2.power(-1)", None),
        ("(0-2).power(-3)", None),
        ("10.power(-5)", None),
        # Decimal base with negative integral exponent: exact Decimal.
        ("2.5.power(-1)", "0.4"),
        ("10.0.power(-1)", "0.1"),
        # QA-002: exact Decimal power — no binary64 noise.
        ("1.1.power(2)", "1.21"),
        ("1.1.power(3)", "1.331"),
        ("0.1.power(3)", "0.001"),
        ("1.5.power(30)", "191751.0592328840866684913635"),
        # QA-004: transcendental exponent -> shortest-round-trip float text.
        ("2.power(0.5)", "1.4142135623730951"),
        ("3.power(0.5)", "1.7320508075688772"),
        ("2.power(1.5)", "2.8284271247461903"),
        # Unrepresentable -> empty.
        ("(0-2).power(0.5)", None),
        ("0.power(0)", None),
        # 28-sig context rounding for long Decimal results.
        ("(1.1).power(-1)", "0.9090909090909090909090909091"),
        # QA-003: no negative zero from round().
        ("(0-0.4).round()", "0.0"),
        ("(0-0.0).round()", "0.0"),
        ("0.4.round()", "0.0"),
        ("(0-0.49).round(1)", "-0.5"),
    ],
)
def test_power_and_round_semantics_both_engines(
    monkeypatch, expr: str, expected
) -> None:
    resource = json.dumps({"resourceType": "Observation"})
    cpp = _cpp_connection()
    py = _python_fallback_connection(monkeypatch)
    try:
        cpp_text = _expr_text(cpp, resource, expr)
        py_text = _expr_text(py, resource, expr)
        assert cpp_text == expected, f"native {expr!r}: {cpp_text!r}"
        assert py_text == expected, f"fallback {expr!r}: {py_text!r}"
    finally:
        cpp.close()
        py.close()


def test_power_integer_result_is_integer_typed(monkeypatch) -> None:
    resource = json.dumps({"resourceType": "Observation"})
    con = duckdb.connect(config={"allow_unsigned_extensions": True})
    assert register_fhirpath(con) is True
    try:
        for expr in ("2.power(3) is Integer", "2.power(3) = 8"):
            row = con.execute(
                "SELECT fhirpath_text(?::JSON, ?)", [resource, expr]
            ).fetchone()[0]
            assert row == "true", expr
    finally:
        con.close()
