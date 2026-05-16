"""CQL conversion function parity checks."""

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


def test_cql_conversion_expressions_parse_and_translate() -> None:
    for expression in [
        "ToBoolean('true')",
        "ToInteger('42')",
        "ToLong('9223372036854775807')",
        "ToRatio('{\"numerator\":{\"value\":1},\"denominator\":{\"value\":2}}')",
        "ToQuantity('5 mg')",
        "ToConcept('{\"code\":\"x\"}')",
    ]:
        parsed = parse_expression(expression)
        assert isinstance(parsed, FunctionRef)

    cql = """library Conversions version '1.0.0'
using FHIR version '4.0.1'
context Patient
define L: ToLong('9223372036854775807')
define R: ToRatio('{"numerator":{"value":1},"denominator":{"value":2}}')
"""
    translated = translate_cql(cql)
    assert "ToLong" in str(translated["L"])
    assert "ToRatio" in str(translated["R"])


def test_cql_conversion_duckdb_surface_matches_cpp_registration() -> None:
    ratio = '{"numerator":{"value":1,"unit":"mg"},"denominator":{"value":2,"unit":"mL"}}'
    expressions = [
        "SELECT ToString(123)",
        "SELECT ToBoolean('true')",
        "SELECT ToInteger('42')",
        "SELECT ToDecimal('1.25')::VARCHAR",
        "SELECT ToDate('2024-01-15')::VARCHAR",
        "SELECT ToDateTime('2024-01-15T10:30:00')::VARCHAR",
        "SELECT ToTime('T10:30:00')::VARCHAR",
        "SELECT ToQuantity('5.5 ''cm''')",
        "SELECT ToQuantity('5 cm')",
        "SELECT ToLong('9223372036854775807')",
        "SELECT ToLong('9223372036854775808')",
        f"SELECT ToRatio('{ratio}')",
        "SELECT ToRatio('not json')",
        "SELECT ToConcept('{\"code\":\"x\",\"system\":\"s\"}')",
    ]

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for expression in expressions:
            assert cpp.execute(expression).fetchone() == py.execute(expression).fetchone()
    finally:
        py.close()
        cpp.close()
