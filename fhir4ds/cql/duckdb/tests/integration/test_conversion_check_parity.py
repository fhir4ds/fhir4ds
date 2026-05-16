"""CQL conversion-check UDF parity checks."""

from __future__ import annotations

import duckdb

from fhir4ds.cql.duckdb import register
from fhir4ds.cql.duckdb.extension import _register_python_supplements
from fhir4ds.cql.parser import parse_expression
from fhir4ds.cql.parser.ast_nodes import FunctionRef
from fhir4ds.cql.translator import translate_cql


def _python_only_connection() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(config={"allow_unsigned_extensions": True})
    _register_python_supplements(con, cpp_loaded=False, include_fhirpath=True)
    return con


def _cpp_connection() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(config={"allow_unsigned_extensions": True})
    register(con, include_fhirpath=True)
    return con


def test_cql_conversion_check_expressions_parse_and_translate() -> None:
    for expression in [
        "ConvertsToBoolean('true')",
        "ConvertsToInteger('42')",
        "ConvertsToLong('9223372036854775807')",
        "ConvertsToRatio('{\"numerator\":{\"value\":1},\"denominator\":{\"value\":2}}')",
        "CanConvertQuantity('1000 mg', 'g')",
        "ConvertQuantity('1000 mg', 'g')",
    ]:
        parsed = parse_expression(expression)
        assert isinstance(parsed, FunctionRef)

    cql = """library ConversionChecks version '1.0.0'
using FHIR version '4.0.1'
context Patient
define B: ConvertsToBoolean('true')
define I: ConvertsToInteger('42')
define Q: CanConvertQuantity('1000 mg', 'g')
"""
    translated = translate_cql(cql)
    assert "ConvertsToBoolean" in str(translated["B"])
    assert "ConvertsToInteger" in str(translated["I"])
    assert "CanConvertQuantity" in str(translated["Q"])


def test_cql_conversion_check_duckdb_surface_matches_cpp_registration() -> None:
    ratio = '{"numerator":{"value":1,"unit":"mg"},"denominator":{"value":2,"unit":"mL"}}'
    expressions = [
        "SELECT ConvertsToBoolean('true')",
        "SELECT ConvertsToBoolean('maybe')",
        "SELECT ConvertsToDate('2024-01-15')",
        "SELECT ConvertsToDateTime('2024-01-15T10:30:00')",
        "SELECT ConvertsToDecimal('1.25')",
        "SELECT ConvertsToDecimal('NaN')",
        "SELECT ConvertsToInteger('42')",
        "SELECT ConvertsToInteger('2147483648')",
        "SELECT ConvertsToLong('9223372036854775807')",
        "SELECT ConvertsToQuantity('5 ''mg''')",
        "SELECT ConvertsToQuantity('5 mg')",
        f"SELECT ConvertsToRatio('{ratio}')",
        "SELECT ConvertsToString('abc')",
        "SELECT ConvertsToTime('T10:30:00')",
        "SELECT CanConvertQuantity('1000 ''mg''', 'g')",
        "SELECT ConvertQuantity('1000 ''mg''', 'g')",
    ]

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for expression in expressions:
            assert cpp.execute(expression).fetchone() == py.execute(expression).fetchone()
    finally:
        py.close()
        cpp.close()
