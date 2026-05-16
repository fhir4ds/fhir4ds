"""CQL comparison operator parity checks."""

from __future__ import annotations

import duckdb

from fhir4ds.cql.duckdb import register
from fhir4ds.cql.duckdb.extension import _register_python_supplements
from fhir4ds.cql.parser import parse_expression
from fhir4ds.cql.parser.ast_nodes import BinaryExpression
from fhir4ds.cql.translator import translate_cql


def _python_only_connection() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(config={"allow_unsigned_extensions": True})
    _register_python_supplements(con, cpp_loaded=False, include_fhirpath=True)
    return con


def _cpp_connection() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(config={"allow_unsigned_extensions": True})
    register(con, include_fhirpath=True)
    return con


def test_cql_comparison_expressions_parse_and_translate() -> None:
    operators = {
        "5 = 5": "=",
        "5 != 6": "!=",
        "5 < 6": "<",
        "5 <= 5": "<=",
        "6 > 5": ">",
        "6 >= 6": ">=",
        "'abc' ~ 'abc'": "~",
        "'abc' !~ 'def'": "!~",
        "5 between 1 and 10": "between",
    }
    for expression, operator in operators.items():
        parsed = parse_expression(expression)
        assert isinstance(parsed, BinaryExpression)
        assert parsed.operator == operator

    cql = """library Comparisons version '1.0.0'
using FHIR version '4.0.1'
context Patient
define BetweenCheck: 5 between 1 and 10
define QuantityEq: 1 'h' = 60 'min'
define DateBefore: @2024-01 before @2024-02
"""
    translated = translate_cql(cql)

    between_sql = str(translated["BetweenCheck"])
    assert "operator='>='" in between_sql
    assert "operator='<='" in between_sql

    quantity_sql = str(translated["QuantityEq"])
    assert "quantity_compare" in quantity_sql
    assert "value='=='" in quantity_sql

    date_sql = str(translated["DateBefore"])
    assert "cqlBefore" in date_sql


def test_cql_comparison_duckdb_surface_matches_cpp_registration() -> None:
    expressions = [
        (
            "SELECT quantityCompare('{\"value\":1,\"code\":\"h\"}', "
            "'{\"value\":60,\"code\":\"min\"}', '==')"
        ),
        (
            "SELECT quantityCompare('{\"value\":1,\"code\":\"h\"}', "
            "'{\"value\":30,\"code\":\"min\"}', '>')"
        ),
        (
            "SELECT quantityCompare('{\"value\":1,\"code\":\"kg\"}', "
            "'{\"value\":1000,\"code\":\"g\"}', '<=')"
        ),
        (
            "SELECT quantityCompare('{\"value\":1,\"code\":\"kg\"}', "
            "'{\"value\":1,\"code\":\"m\"}', '<')"
        ),
        "SELECT dateTimeSameAs('2024-01-15', '2024-01-20', 'month')",
        "SELECT dateTimeSameOrBefore('2024-01-15', '2024-01-20', 'day')",
        "SELECT dateTimeSameOrAfter('2024-02', '2024-01', 'month')",
        "SELECT fhirpath_bool('{\"resourceType\":\"Patient\",\"age\":5}'::JSON, 'age = 5')",
        "SELECT fhirpath_bool('{\"resourceType\":\"Patient\",\"age\":5}'::JSON, 'age != 6')",
        "SELECT fhirpath_bool('{\"resourceType\":\"Patient\",\"age\":5}'::JSON, 'age >= 5')",
        "SELECT fhirpath_bool('{\"resourceType\":\"Patient\",\"age\":5}'::JSON, 'age <= 5')",
    ]

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for expression in expressions:
            assert cpp.execute(expression).fetchone() == py.execute(expression).fetchone()
    finally:
        py.close()
        cpp.close()
