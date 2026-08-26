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


def test_cql_datetime_part2_explorer_decimal_quantity_truncation_above_seconds() -> None:
    """CQL §Add / §Subtract: "For precisions above seconds, any decimal
    portion of the time-valued quantity is ignored."

    The triggering condition is the quantity UNIT (year/month/week/day/
    hour/minute are above seconds; second/millisecond are at-or-below),
    not the input precision. So `1.5 days` should always become 1 day,
    `1.5 hours` should always become 1 hour, regardless of whether the
    input is Date, DateTime, or Time.

    Regression coverage for CQL-14 EXPLORER QA-001 (2026-07-02):
    fhir4ds/cql/duckdb/udf/datetime.py:dateAddQuantity previously only
    truncated decimal portions when the quantity unit was FINER than
    the input precision. The Time-only path had no truncation at all,
    and the equal-precision DateTime path inherited the float through
    to Python's timedelta. Native C++ extension had the same bug at
    extensions/cql/src/cql_extension.cpp:ApplyQuantityAtInputPrecision.
    """
    cases = [
        # (sql, expected_value)
        # Time-only path: above-seconds decimal must truncate
        (
            "SELECT dateAddQuantity('T12:00', "
            "'{\"value\": 1.5, \"unit\": \"hour\", "
            "\"system\": \"http://unitsofmeasure.org\"}')",
            "T13:00",
        ),
        (
            "SELECT dateAddQuantity('T12:00:00', "
            "'{\"value\": 1.5, \"unit\": \"minute\", "
            "\"system\": \"http://unitsofmeasure.org\"}')",
            "T12:01:00",
        ),
        # Date path: same-precision decimal must truncate
        (
            "SELECT dateAddQuantity('2024-01-15', "
            "'{\"value\": 1.5, \"unit\": \"day\"}')",
            "2024-01-16",
        ),
        (
            "SELECT dateAddQuantity('2024-01-15', "
            "'{\"value\": 2.5, \"unit\": \"day\"}')",
            "2024-01-17",
        ),
        (
            "SELECT dateAddQuantity('2024-01-15', "
            "'{\"value\": 1.5, \"unit\": \"week\"}')",
            "2024-01-22",
        ),
        # DateTime path: same-precision decimal must truncate
        (
            "SELECT dateAddQuantity('2024-01-15T12:00:00', "
            "'{\"value\": 1.5, \"unit\": \"day\"}')",
            "2024-01-16T12:00:00",
        ),
        (
            "SELECT dateAddQuantity('2024-01-15T12', "
            "'{\"value\": 1.5, \"unit\": \"hour\"}')",
            "2024-01-15T13",
        ),
        # Subtract path: same rules apply
        (
            "SELECT dateSubtractQuantity('2024-01-15', "
            "'{\"value\": 1.5, \"unit\": \"day\"}')",
            "2024-01-14",
        ),
        (
            "SELECT dateSubtractQuantity('2024-01-15', "
            "'{\"value\": 2.5, \"unit\": \"day\"}')",
            "2024-01-13",
        ),
        (
            "SELECT dateSubtractQuantity('T12:00', "
            "'{\"value\": 1.5, \"unit\": \"hour\"}')",
            "T11:00",
        ),
    ]
    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for con_name, con in (("python", py), ("cpp", cpp)):
            for sql, expected in cases:
                actual = con.execute(sql).fetchone()[0]
                assert actual == expected, (
                    f"[{con_name}] {sql} -> {actual!r}; expected {expected!r}"
                )
    finally:
        py.close()
        cpp.close()


def test_cql_datetime_part2_explorer_integer_quantity_unaffected() -> None:
    """Regression guard: integer-valued Quantity arithmetic must be
    unaffected by the decimal-truncation fix."""
    cases = [
        (
            "SELECT dateAddQuantity('2024-01-15', "
            "'{\"value\": 1, \"unit\": \"day\"}')",
            "2024-01-16",
        ),
        (
            "SELECT dateSubtractQuantity('2024-01-15', "
            "'{\"value\": 7, \"unit\": \"day\"}')",
            "2024-01-08",
        ),
        # CQL §Add spec examples
        (
            "SELECT dateAddQuantity('2024', "
            "'{\"value\": 24, \"unit\": \"month\"}')",
            "2026",
        ),
        (
            "SELECT dateAddQuantity('2024', "
            "'{\"value\": 18, \"unit\": \"month\"}')",
            "2025",
        ),
        # Year-precision Subtract spec example
        (
            "SELECT dateSubtractQuantity('2014T', "
            "'{\"value\": 25, \"unit\": \"month\"}')",
            "2012T",
        ),
        # Leap-day arithmetic
        (
            "SELECT dateSubtractQuantity('2020-02-29', "
            "'{\"value\": 1, \"unit\": \"year\"}')",
            "2019-02-28",
        ),
    ]
    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for con_name, con in (("python", py), ("cpp", cpp)):
            for sql, expected in cases:
                actual = con.execute(sql).fetchone()[0]
                assert actual == expected, (
                    f"[{con_name}] {sql} -> {actual!r}; expected {expected!r}"
                )
    finally:
        py.close()
        cpp.close()


def test_cql_datetime_part2_starts_ends_same_or_and_on_or_precision() -> None:
    """CQL 1.5 §9.18/§9.19 ("same" is a synonym for "on" in timing phrases),
    §9.25 Same Or After / §9.26 Same Or Before, §9.24 Same As.

    Two previously broken timing-phrase surfaces:
    1. `starts/ends same <precision> or after|or before` — the parser dropped
       the `or after`/`or before` qualifier (consuming the token as if it were
       `as`), lowering to same-as equality (definitive wrong booleans), and
       the no-precision forms were hard ParseErrors. Per the CQL grammar
       these are SameOrAfter/SameOrBefore on the start/end boundary of the
       left operand.
    2. `starts/ends on or before|after <precision> of X` — the interval-bound
       side was hardcoded to DATE casts, ignoring the specified precision,
       producing false negatives at year/month precision.
    """
    cql = """library DateTime2Explorer version '1.0.0'
using FHIR version '4.0.1'
context Patient
define StartsWithOrAfterTrue: Interval[@2012-01-02, @2012-01-05] starts same day or after @2012-01-01
define StartsWithOrAfterFalse: Interval[@2012-01-01, @2012-01-05] starts same day or after @2012-01-02
define EndsWithOrBeforeTrue: Interval[@2012-01-01, @2012-01-05] ends same day or before @2012-01-06
define EndsWithOrBeforeFalse: Interval[@2012-01-01, @2012-01-06] ends same day or before @2012-01-05
define StartsWithOrAfterHour: Interval[@2012-01-01T05:00:00, @2012-01-01T09:00:00] starts same hour or after @2012-01-01T03:30:00
define NoPrecisionOrAfter: Interval[@2012-01-02, @2012-01-05] starts same or after @2012-01-01
define NoPrecisionOrBefore: Interval[@2012-01-01, @2012-01-05] ends same or before @2012-01-06
define SameOrIntervalRight: Interval[@2012-01-05, @2012-01-06] starts same day or after Interval[@2012-01-01, @2012-01-04]
define SameOrBeforeIntervalRight: Interval[@2012-01-01, @2012-01-02] ends same day or before Interval[@2012-01-03, @2012-01-04]
define StartsOnOrBeforeYear: Interval[@2012-01-01, @2012-06-01] starts on or before year of @2012-12-31
define EndsOnOrBeforeYear: Interval[@2012-01-01, @2012-06-01] ends on or before year of @2012-12-31
define EndsOnOrBeforeMonth: Interval[@2012-01-01, @2012-03-01] ends on or before month of @2012-03-20
define EndsOnOrBeforeMonthFalse: Interval[@2012-01-01, @2012-04-01] ends on or before month of @2012-03-20
define StartsOnOrAfterMonth: Interval[@2012-03-15, @2012-06-01] starts on or after month of @2012-03-20
define EndsOnOrAfterYear: Interval[@2012-03-01, @2012-06-01] ends on or after year of @2012-01-15
define StartsOnOrBeforeDay: Interval[@2012-01-01, @2012-01-05] starts on or before day of @2012-01-06
define SameAsPointStillWorks: Interval[@2012-01-01, @2012-01-05] starts same day as @2012-01-01
define SameAsIntervalSingleton: Interval[@2012-01-01, @2012-01-05] starts same day as Interval[@2012-01-01, @2012-01-10]
"""
    translated = translate_cql(cql)
    expected = {
        "StartsWithOrAfterTrue": "true",
        "StartsWithOrAfterFalse": "false",
        "EndsWithOrBeforeTrue": "true",
        "EndsWithOrBeforeFalse": "false",
        "StartsWithOrAfterHour": "true",
        "NoPrecisionOrAfter": "true",
        "NoPrecisionOrBefore": "true",
        "SameOrIntervalRight": "true",
        "SameOrBeforeIntervalRight": "true",
        "StartsOnOrBeforeYear": "true",
        "EndsOnOrBeforeYear": "true",
        "EndsOnOrBeforeMonth": "true",
        "EndsOnOrBeforeMonthFalse": "false",
        "StartsOnOrAfterMonth": "true",
        "EndsOnOrAfterYear": "true",
        "StartsOnOrBeforeDay": "true",
        "SameAsPointStillWorks": "true",
        # §9.24 Same As with a point-vs-interval operand: the point is a
        # singleton interval so start AND end must match — differing ends → false.
        "SameAsIntervalSingleton": "false",
    }
    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for name, expected_value in expected.items():
            sql = f"SELECT CAST(({translated[name].to_sql()}) AS VARCHAR)"
            py_row = py.execute(sql).fetchone()[0]
            cpp_row = cpp.execute(sql).fetchone()[0]
            norm = lambda v: None if v is None else str(v).strip().lower()  # noqa: E731
            assert norm(py_row) == expected_value, f"Python mismatch for {name}: {py_row!r} != {expected_value!r}"
            assert norm(cpp_row) == expected_value, f"C++ mismatch for {name}: {cpp_row!r} != {expected_value!r}"
    finally:
        py.close()
        cpp.close()
