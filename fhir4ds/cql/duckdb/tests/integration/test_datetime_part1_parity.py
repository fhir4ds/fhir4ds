"""CQL date/time operator part 1 parity checks."""

from __future__ import annotations

import duckdb

from fhir4ds.cql.duckdb import register
from fhir4ds.cql.duckdb.extension import _register_python_supplements
from fhir4ds.cql.parser import parse_expression
from fhir4ds.cql.parser.ast_nodes import BinaryExpression, DateComponent, DifferenceBetween, DurationBetween, FunctionRef
from fhir4ds.cql.translator import translate_cql


def _python_only_connection() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(config={"allow_unsigned_extensions": True})
    _register_python_supplements(con, cpp_loaded=False, include_fhirpath=True)
    return con


def _cpp_connection() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(config={"allow_unsigned_extensions": True})
    register(con, include_fhirpath=True)
    return con


def test_cql_datetime_part1_expressions_parse_and_translate() -> None:
    assert isinstance(parse_expression("@2024-02-01 after month of @2024-01-01"), BinaryExpression)
    assert isinstance(parse_expression("@2024-01-01 before month of @2024-02-01"), BinaryExpression)
    assert isinstance(parse_expression("year from @2024-06-15"), DateComponent)
    assert isinstance(parse_expression("difference in months between @2024-01-31 and @2024-02-01"), DifferenceBetween)
    assert isinstance(parse_expression("days between @2024-01-01 and @2024-01-31"), DurationBetween)
    assert isinstance(parse_expression("Date(2024,1,15)"), FunctionRef)
    assert isinstance(parse_expression("DateTime(2024,1,15,10,30,0)"), FunctionRef)

    cql = """library DateTime1 version '1.0.0'
using FHIR version '4.0.1'
context Patient
define AddDateTime: @2024-01-01T10:00:00 + 5 'h'
define AfterMonth: @2024-02-01 after month of @2024-01-01
define BeforeMonth: @2024-01-01 before month of @2024-02-01
define DateCtor: Date(2024, 1, 15)
define DateTimeCtor: DateTime(2024, 1, 15, 10, 30, 0)
define YearComponent: year from @2024-06-15
define DifferenceMonths: difference in months between @2024-01-31 and @2024-02-01
define DurationDays: days between @2024-01-01 and @2024-01-31
"""
    translated = translate_cql(cql)

    assert "dateAddQuantity" in str(translated["AddDateTime"])
    assert "cqlAfterP" in str(translated["AfterMonth"])
    assert "cqlBeforeP" in str(translated["BeforeMonth"])
    assert translated["DateCtor"].to_sql() == "'2024-01-15'"
    assert translated["DateTimeCtor"].to_sql() == "'2024-01-15T10:30:00'"
    assert "SUBSTR" in str(translated["YearComponent"])
    assert "differenceInMonths" in str(translated["DifferenceMonths"])
    assert "cqlDurationBetween" in str(translated["DurationDays"])


def test_cql_datetime_part1_duckdb_surface_matches_cpp_registration() -> None:
    expressions = [
        "SELECT dateComponent('2024-06-15', 'year')",
        "SELECT dateComponent('2024-06-15', 'month')",
        "SELECT dateAddQuantity('2024-01-31', '{\"value\":1,\"code\":\"mo\"}')",
        "SELECT dateAddQuantity('2024-01-01T10:00:00', '{\"value\":5,\"code\":\"h\"}')",
        "SELECT cqlBeforeP('2024-01-01', '2024-02-01', 'month')",
        "SELECT cqlAfterP('2024-02-01', '2024-01-01', 'month')",
        "SELECT cqlDurationBetween('2024-01-01', '2024-01-31', 'day')",
        "SELECT cqlDurationBetween('2024', '2025', 'month')",
        "SELECT differenceInMonths('2024-01-31', '2024-02-01')",
        "SELECT DaysBetween('2024-02-28', '2024-03-01')",
    ]

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for expression in expressions:
            assert cpp.execute(expression).fetchone() == py.execute(expression).fetchone()
    finally:
        py.close()
        cpp.close()
