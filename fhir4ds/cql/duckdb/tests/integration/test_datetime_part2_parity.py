"""CQL date/time operator part 2 parity checks."""

from __future__ import annotations

import duckdb

from fhir4ds.cql.duckdb import register
from fhir4ds.cql.duckdb.extension import _register_python_supplements
from fhir4ds.cql.parser import parse_expression
from fhir4ds.cql.parser.ast_nodes import BinaryExpression, FunctionRef
from fhir4ds.cql.translator import translate_cql


def _python_only_connection() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(config={"allow_unsigned_extensions": True})
    _register_python_supplements(con, cpp_loaded=False, include_fhirpath=True)
    return con


def _cpp_connection() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(config={"allow_unsigned_extensions": True})
    register(con, include_fhirpath=True)
    return con


def test_cql_datetime_part2_expressions_parse_and_translate() -> None:
    for expression in ["Now()", "Time(10,30,0,0)", "TimeOfDay()", "Today()"]:
        assert isinstance(parse_expression(expression), FunctionRef)

    for expression in [
        "@2024-01-01 on or after day of @2024-01-01",
        "@2024-01-01 on or before day of @2024-01-02",
        "@2024-01-01 same day as @2024-01-01",
        "@2024-01-02 same or after day of @2024-01-01",
        "@2024-01-01 same or before day of @2024-01-02",
        "@2024-01-01T10:00:00 - 5 'h'",
    ]:
        assert isinstance(parse_expression(expression), BinaryExpression)

    cql = """library DateTime2 version '1.0.0'
using FHIR version '4.0.1'
context Patient
define NowCheck: Now()
define OnAfter: @2024-01-01 on or after day of @2024-01-01
define OnBefore: @2024-01-01 on or before day of @2024-01-02
define SameAs: @2024-01-01 same day as @2024-01-01
define SameAfter: @2024-01-02 same or after day of @2024-01-01
define SameBefore: @2024-01-01 same or before day of @2024-01-02
define SubtractDateTime: @2024-01-01T10:00:00 - 5 'h'
define TimeCtor: Time(10, 30, 0, 0)
define TimeOfDayCheck: TimeOfDay()
define TodayCheck: Today()
"""
    translated = translate_cql(cql)

    assert "CURRENT_TIMESTAMP" in translated["NowCheck"].to_sql()
    assert "cqlSameOrAfterP" in str(translated["OnAfter"])
    assert "cqlSameOrBeforeP" in str(translated["OnBefore"])
    assert "cqlSameAsP" in str(translated["SameAs"])
    assert "cqlSameOrAfterP" in str(translated["SameAfter"])
    assert "cqlSameOrBeforeP" in str(translated["SameBefore"])
    assert "dateSubtractQuantity" in str(translated["SubtractDateTime"])
    assert "make_time" in str(translated["TimeCtor"])
    assert "CURRENT_TIME" in translated["TimeOfDayCheck"].to_sql()
    assert "CURRENT_DATE" in translated["TodayCheck"].to_sql()


def test_cql_datetime_part2_duckdb_surface_matches_cpp_registration() -> None:
    expressions = [
        "SELECT dateTimeNow() IS NOT NULL",
        "SELECT dateTimeToday() IS NOT NULL",
        "SELECT dateTimeTimeOfDay() IS NOT NULL",
        "SELECT dateTimeSameAs('2024-01-01', '2024-01-02', 'month')",
        "SELECT dateTimeSameOrBefore('2024-01-01', '2024-01-02', 'day')",
        "SELECT dateTimeSameOrAfter('2024-01-02', '2024-01-01', 'day')",
        "SELECT cqlSameAsP('2024-01-01', '2024-01-02', 'month')",
        "SELECT cqlSameOrBeforeP('2024-01-01', '2024-01-02', 'day')",
        "SELECT cqlSameOrAfterP('2024-01-02', '2024-01-01', 'day')",
        "SELECT dateSubtractQuantity('2024-01-01T10:00:00', '{\"value\":5,\"code\":\"h\"}')",
    ]

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for expression in expressions:
            assert cpp.execute(expression).fetchone() == py.execute(expression).fetchone()
    finally:
        py.close()
        cpp.close()
