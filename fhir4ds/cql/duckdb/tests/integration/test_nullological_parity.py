"""CQL nullological operator parity checks."""

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


def test_cql_nullological_expressions_parse_and_translate() -> None:
    for expression in ["Coalesce(null, 'x')", "IsNull(null)", "IsTrue(true)", "IsFalse(false)"]:
        parsed = parse_expression(expression)
        assert isinstance(parsed, FunctionRef)

    cql = """library Nulls version '1.0.0'
using FHIR version '4.0.1'
context Patient
define C: Coalesce(null, 'x')
define T: IsTrue(true)
"""
    translated = translate_cql(cql)
    assert "COALESCE" in str(translated["C"]) or "Coalesce" in str(translated["C"])
    assert "IsTrue" in str(translated["T"])


def test_cql_nullological_duckdb_surface_matches_cpp_registration() -> None:
    expressions = [
        'SELECT "Coalesce"(NULL, \'world\')',
        'SELECT "Coalesce"(\'first\', \'second\')',
        'SELECT "IsNull"(NULL)',
        'SELECT "IsNull"(1)',
        'SELECT "IsTrue"(true)',
        'SELECT "IsTrue"(false)',
        'SELECT "IsTrue"(NULL)',
        'SELECT "IsFalse"(false)',
        'SELECT "IsFalse"(true)',
        'SELECT "IsFalse"(NULL)',
        'SELECT logicalCoalesce(\'[null, null, "5"]\')',
        'SELECT logicalCoalesce(\'[null, true, false]\')',
        "SELECT logicalCoalesce('[]')",
        "SELECT logicalCoalesce(NULL)",
    ]

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for expression in expressions:
            assert cpp.execute(expression).fetchone() == py.execute(expression).fetchone()
    finally:
        py.close()
        cpp.close()
