"""CQL date/time operator part 2 parity checks."""

from __future__ import annotations

import duckdb
import pytest

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
    for expression in ["Now()", "Time(10,30,0,0)", "Time(12)", "TimeOfDay()", "Today()"]:
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
define TimeHourOnly: Time(12)
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
    assert "dateComponent" in str(translated["TimeCtor"])
    assert "printf" in str(translated["TimeCtor"])
    assert "T%02d" in str(translated["TimeHourOnly"])
    assert "CURRENT_TIME" in translated["TimeOfDayCheck"].to_sql()
    assert "'T' ||" in translated["TimeOfDayCheck"].to_sql()
    assert "CURRENT_DATE" in translated["TodayCheck"].to_sql()


def test_cql_datetime_part2_duckdb_surface_matches_cpp_registration() -> None:
    expressions = [
        "SELECT dateTimeNow() IS NOT NULL",
        "SELECT dateTimeToday() IS NOT NULL",
        "SELECT dateTimeTimeOfDay() IS NOT NULL",
        "SELECT SUBSTR(dateTimeNow(), 11, 1)",
        "SELECT SUBSTR(dateTimeNow(), 20, 1)",
        "SELECT SUBSTR(dateTimeTimeOfDay(), 1, 1)",
        "SELECT LENGTH(dateTimeTimeOfDay())",
        "SELECT dateTimeSameAs('2024-01-01', '2024-01-02', 'month')",
        "SELECT dateTimeSameOrBefore('2024-01-01', '2024-01-02', 'day')",
        "SELECT dateTimeSameOrAfter('2024-01-02', '2024-01-01', 'day')",
        "SELECT dateTimeSameAs('2024-01-01T00:30:00+01:00', '2023-12-31T23:30:00Z', 'second')",
        "SELECT dateTimeSameAs('2024-01', '2024-01-15', 'day')",
        "SELECT dateTimeSameAs('2024-01-01', '2024-01-01', 'bogus')",
        "SELECT cqlSameAsP('2024-01-01', '2024-01-02', 'month')",
        "SELECT cqlSameOrBeforeP('2024-01-01', '2024-01-02', 'day')",
        "SELECT cqlSameOrAfterP('2024-01-02', '2024-01-01', 'day')",
        "SELECT cqlSameAsP('2024-01-01T00:30:00+01:00', '2023-12-31T23:30:00Z', 'second')",
        "SELECT cqlSameAsP('2024-01-01', '2024-01-01', 'bogus')",
        "SELECT dateSubtractQuantity('2024-01-01T10:00:00', '{\"value\":5,\"code\":\"h\"}')",
        "SELECT dateSubtractQuantity('2024-01-15', '{\"value\":1.5,\"unit\":\"week\"}')",
        "SELECT dateSubtractQuantity('2024-01-01', '{\"unit\":\"day\"}')",
        "SELECT dateSubtractQuantity('2024-01-01', '{\"value\":null,\"unit\":\"day\"}')",
        "SELECT dateSubtractQuantity('2024-01-01', '{\"value\":\"abc\",\"unit\":\"day\"}')",
        "SELECT dateSubtractQuantity('2024-01-01', '{\"value\":\"5\",\"unit\":\"day\"}')",
        "SELECT dateSubtractQuantity('2024-01-01', '{\"value\":true,\"unit\":\"day\"}')",
        "SELECT dateSubtractQuantity('2024-01-01', 'not json')",
        "SELECT dateAddQuantity('2024-01-01', '{\"unit\":\"day\"}')",
        "SELECT dateAddQuantity('2024-01-01', '{\"value\":null,\"unit\":\"day\"}')",
        "SELECT dateAddQuantity('2024-01-01', '{\"value\":\"abc\",\"unit\":\"day\"}')",
        "SELECT dateAddQuantity('2024-01-01', '{\"value\":\"5\",\"unit\":\"day\"}')",
        "SELECT dateAddQuantity('2024-01-01', '{\"value\":true,\"unit\":\"day\"}')",
        "SELECT dateAddQuantity('2024-01-01', 'not json')",
    ]

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for expression in expressions:
            assert cpp.execute(expression).fetchone() == py.execute(expression).fetchone()
    finally:
        py.close()
        cpp.close()


def test_cql_timeofday_equality_matches_cpp_and_python() -> None:
    translated = translate_cql(
        """library DateTime2TimeOfDay version '1.0.0'
using FHIR version '4.0.1'
context Patient
define TimeOfDayEqualsItself: TimeOfDay() = TimeOfDay()
define TimeOfDaySameSecond: TimeOfDay() same second as TimeOfDay()
define TimeOfDayHour: hour from TimeOfDay()
define TimeOfDayMinute: minute from TimeOfDay()
define TimeOfDaySecond: second from TimeOfDay()
define TimeHourOnly: Time(12)
define TimeHourOnlyFromComponent: Time(hour from @T12:30)
define TimeFromDateTimeExtraction: time from @2024-01-01T12:30:15
define TimeMinuteNull: Time(12, null)
define TimeSecondNull: Time(12, 30, null)
define TimeMillisecondNull: Time(12, 30, 0, null)
define TimeInvalidGap: Time(12, null, 0)
"""
    )

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for con in (py, cpp):
            assert con.execute(f"SELECT {translated['TimeOfDayEqualsItself'].to_sql()}").fetchone() == (True,)
            assert con.execute(f"SELECT {translated['TimeOfDaySameSecond'].to_sql()}").fetchone() == (True,)
            hour = con.execute(f"SELECT {translated['TimeOfDayHour'].to_sql()}").fetchone()[0]
            minute = con.execute(f"SELECT {translated['TimeOfDayMinute'].to_sql()}").fetchone()[0]
            second = con.execute(f"SELECT {translated['TimeOfDaySecond'].to_sql()}").fetchone()[0]
            assert 0 <= hour <= 23
            assert 0 <= minute <= 59
            assert 0 <= second <= 59
            assert con.execute(f"SELECT {translated['TimeHourOnly'].to_sql()}").fetchone() == ("T12",)
            assert con.execute(f"SELECT {translated['TimeHourOnlyFromComponent'].to_sql()}").fetchone() == ("T12",)
            assert con.execute(f"SELECT {translated['TimeFromDateTimeExtraction'].to_sql()}").fetchone() == ("T12:30:15",)
            assert con.execute(f"SELECT {translated['TimeMinuteNull'].to_sql()}").fetchone() == ("T12",)
            assert con.execute(f"SELECT {translated['TimeSecondNull'].to_sql()}").fetchone() == ("T12:30",)
            assert con.execute(f"SELECT {translated['TimeMillisecondNull'].to_sql()}").fetchone() == ("T12:30:00",)
            assert con.execute(f"SELECT {translated['TimeInvalidGap'].to_sql()}").fetchone() == (None,)
    finally:
        py.close()
        cpp.close()


def test_cql_time_constructor_static_invalid_components_rejected() -> None:
    for expression in [
        "Time(true)",
        "Time(12.5)",
        "Time(true, 0)",
        "Time(12.5, 0)",
    ]:
        with pytest.raises(ValueError):
            translate_cql(
                f"""library DateTime2InvalidTime version '1.0.0'
using FHIR version '4.0.1'
context Patient
define BadTime: {expression}
"""
            )

    translated = translate_cql(
        """library DateTime2InvalidTimeRange version '1.0.0'
using FHIR version '4.0.1'
context Patient
define BigMs: Time(12, 0, 0, 1000)
define BigHour: Time(24)
"""
    )
    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for name in ["BigMs", "BigHour"]:
            sql = f"SELECT {translated[name].to_sql()}"
            assert py.execute(sql).fetchone() == (None,)
            assert cpp.execute(sql).fetchone() == (None,)
    finally:
        py.close()
        cpp.close()


def test_cql_invalid_week_precision_matches_cpp_and_python() -> None:
    translated = translate_cql(
        """library DateTime2WeekPrecision version '1.0.0'
using FHIR version '4.0.1'
context Patient
define SameWeek: @2024-01-01 same week as @2024-01-01
define OnAfterWeek: @2024-01-02 on or after week of @2024-01-01
"""
    )

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for name in ["SameWeek", "OnAfterWeek"]:
            sql = f"SELECT {translated[name].to_sql()}"
            assert py.execute(sql).fetchone() == (None,)
            assert cpp.execute(sql).fetchone() == (None,)
    finally:
        py.close()
        cpp.close()


def test_cql_datetime_timezone_precision_edges_match_reference() -> None:
    translated = translate_cql(
        """library DateTime2TimezonePrecision version '1.0.0'
using FHIR version '4.0.1'
context Patient
define SameDayOffsetLocal:
  @2024-01-01T00:30:00+01:00 same day as @2024-01-01T00:30:00Z
define SameMonthOffsetLocal:
  @2024-01-01T00:30:00+01:00 same month as @2024-01-01T00:30:00Z
define SameSecondOffsetNormalized:
  @2024-01-01T00:30:00+01:00 same second as @2023-12-31T23:30:00Z
define SameDayOrAfterOffsetLocal:
  @2024-01-01T00:30:00+01:00 same day or after @2024-01-01T23:30:00-02:00
define SameDayOrBeforeOffsetLocal:
  @2024-01-01T23:30:00-02:00 same day or before @2024-01-01T00:30:00+01:00
"""
    )
    expected = {
        "SameDayOffsetLocal": True,
        "SameMonthOffsetLocal": True,
        "SameSecondOffsetNormalized": True,
        "SameDayOrAfterOffsetLocal": True,
        "SameDayOrBeforeOffsetLocal": True,
    }
    direct = {
        "SELECT cqlSameAsP('2024-01-01T00:30:00+01:00','2024-01-01T00:30:00Z','day')": True,
        "SELECT cqlSameAsP('2024-01-01T00:30:00+01:00','2024-01-01T00:30:00Z','month')": True,
        "SELECT cqlSameAsP('2024-01-01T00:30:00+01:00','2023-12-31T23:30:00Z','second')": True,
        "SELECT cqlSameOrAfterP('2024-01-01T00:30:00+01:00','2024-01-01T23:30:00-02:00','day')": True,
        "SELECT cqlSameOrBeforeP('2024-01-01T23:30:00-02:00','2024-01-01T00:30:00+01:00','day')": True,
        "SELECT dateTimeSameAs('2024-01-01T00:30:00+01:00','2024-01-01T00:30:00Z','day')": True,
    }

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for con in (py, cpp):
            for name, expected_value in expected.items():
                assert con.execute(f"SELECT {translated[name].to_sql()}").fetchone() == (expected_value,)
            for sql, expected_value in direct.items():
                assert con.execute(sql).fetchone() == (expected_value,)
            assert con.execute(
                "SELECT cqlSameAsP('T00:30:00+01:00','T00:30:00Z','hour')"
            ).fetchone() == (True,)
            assert con.execute(
                "SELECT cqlSameAsP('T00:30:00+01:00','T23:30:00Z','second')"
            ).fetchone() == (False,)
    finally:
        py.close()
        cpp.close()
