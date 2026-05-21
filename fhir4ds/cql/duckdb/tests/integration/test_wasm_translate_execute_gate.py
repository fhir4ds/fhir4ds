"""Strict no-Python translate-and-execute coverage for supported CQL."""

from __future__ import annotations

from .wasm_runtime_helpers import (
    catalog_names,
    emitted_function_names,
    no_python_connection,
    translated_expression_sql,
)


RUNTIME_CQL = """library WasmRuntimeGate version '1.0.0'
using FHIR version '4.0.1'
context Patient

define SameOrBeforeDay: @2024-01-01 same or before day of @2024-01-02
define BeforeDay: @2024-01-01 before day of @2024-01-02
define AfterDay: @2024-01-02 after day of @2024-01-01
define DifferenceDays: difference in days between @2024-01-01 and @2024-01-03
define DatePlusDay: @2024-01-01 + 1 day
define TimeEqual: @T10:00:00.000 = @T10:00:00.000
define TimeDiffHours: difference in hours between @T20 and @T23:25:15.555
define TimePlusHours: @T15:59:59.999 + 5 hours
define TimezoneBeforeHour: @2012-03-10T10:20:00.999+07:00 before hour of @2012-03-10T10:20:00.999+06:00
define DstDifferenceHoursLiteral: difference in hours between @2017-03-12T01:00:00-07:00 and @2017-03-12T03:00:00-06:00
define DstDifferenceMinutesLiteral: difference in minutes between @2017-11-05T01:30:00-06:00 and @2017-11-05T01:15:00-07:00
define DstDifferenceHoursCtor: difference in hours between DateTime(2017, 3, 12, 1, 0, 0, 0, -7.0) and DateTime(2017, 3, 12, 3, 0, 0, 0, -6.0)
define DstDifferenceMinutesCtor: difference in minutes between DateTime(2017, 11, 5, 1, 30, 0, 0, -6.0) and DateTime(2017, 11, 5, 1, 15, 0, 0, -7.0)
define PartialPrecisionUncertain: DateTime(2014, 12, 20) same day or after DateTime(2014, 12)
define DurationUncertainDays: days between DateTime(2014, 1, 15) and DateTime(2014, 2)
define HighBoundaryDecimal: HighBoundary(1.587, 8)
define LowBoundaryDecimal: LowBoundary(1.587, 8)
define PredecessorDecimal: predecessor of 1.0
define AgeYearsAt: CalculateAgeInYearsAt(@1980-01-01, @2024-01-01)
define AgeWeeksAt: CalculateAgeInWeeksAt(@2024-01-01, @2024-01-15)
define NullInterval: Interval[null, null]
define IntervalIntersectOpenNullHigh: Interval[1, 10] intersect Interval[5, null)
define DateTimeIncludedInPrecisionNull: Interval [@2017-09-01T00:00:00, @2017-09-01T00:00:00] included in millisecond of Interval [@2017-09-01T00:00:00.000, @2017-12-30T23:59:59.999]
define NullIntervalOverlaps: Interval[null, null] overlaps Interval[1, 10]
define NullBoundaryProperIncluded: Interval[1, 10] properly included in Interval[null, null]
define DateTimeOverlapUncertain: Interval[DateTime(2012, 1, 25), DateTime(2012, 2, 26)] overlaps Interval[DateTime(2012, 2), DateTime(2012, 3, 28)]
define DateTimeOverlapYearMonthTrue: Interval[DateTime(2012), DateTime(2013, 3)] overlaps Interval[DateTime(2012, 2), DateTime(2013, 2)]
define ExpandInteger: expand Interval[1, 3]
define ExpandIntegerPer2: expand Interval[1, 10] per 2
define ExpandIntegerOpenPer2: expand Interval[1, 10) per 2
define ExpandDecimalPerPointOne: expand Interval[10, 10] per 0.1
define ExpandDatePerDay: expand Interval[@2018-01-01, @2018-01-04] per 1 day
define ExpandDatePer2Days: expand Interval[@2018-01-01, @2018-01-04] per 2 days
define ExpandTimePerHour: expand Interval[@T10, @T12] per 1 hour
define ExpandTimePerMinute: expand Interval[@T10, @T12] per 1 minute
define WidthInteger: width of Interval[1, 3]
define PointInteger: point from Interval[1, 1]
define StringRegex: Matches('abc', 'a.*')
define StringReplace: ReplaceMatches('abc', 'b', 'x')
"""


EXPECTED = {
    "SameOrBeforeDay": True,
    "BeforeDay": True,
    "AfterDay": True,
    "DifferenceDays": "2",
    "DatePlusDay": "2024-01-02",
    "TimeEqual": True,
    "TimeDiffHours": "3",
    "TimePlusHours": "T20:59:59.999",
    "TimezoneBeforeHour": True,
    "DstDifferenceHoursLiteral": "1",
    "DstDifferenceMinutesLiteral": "45",
    "DstDifferenceHoursCtor": "1",
    "DstDifferenceMinutesCtor": "45",
    "PartialPrecisionUncertain": None,
    "DurationUncertainDays": '{"start":16,"end":44,"lowClosed":true,"highClosed":true}',
    "HighBoundaryDecimal": 1.58799999,
    "LowBoundaryDecimal": 1.587,
    "PredecessorDecimal": 0.99999999,
    "AgeYearsAt": 44,
    "AgeWeeksAt": 2,
    "NullInterval": None,
    "IntervalIntersectOpenNullHigh": '{"low": "5", "high": null, "lowClosed": true, "highClosed": false}',
    "DateTimeIncludedInPrecisionNull": None,
    "NullIntervalOverlaps": None,
    "NullBoundaryProperIncluded": True,
    "DateTimeOverlapUncertain": None,
    "DateTimeOverlapYearMonthTrue": True,
    "ExpandInteger": "[1,2,3]",
    "ExpandIntegerPer2": "[1,3,5,7,9]",
    "ExpandIntegerOpenPer2": "[1,3,5,7]",
    "ExpandDecimalPerPointOne": "[10.0,10.1,10.2,10.3,10.4,10.5,10.6,10.7,10.8,10.9]",
    "ExpandDatePerDay": '["2018-01-01","2018-01-02","2018-01-03","2018-01-04"]',
    "ExpandDatePer2Days": '["2018-01-01","2018-01-03"]',
    "ExpandTimePerHour": '["T10","T11","T12"]',
    "ExpandTimePerMinute": "[]",
    "WidthInteger": "2",
    "PointInteger": "1",
    "StringRegex": True,
    "StringReplace": "axc",
}


def test_translator_emitted_functions_exist_in_no_python_runtime() -> None:
    translated = translated_expression_sql(RUNTIME_CQL)
    emitted = set().union(*(emitted_function_names(sql) for sql in translated.values()))

    with no_python_connection() as con:
        available = catalog_names(con)

    missing = {name for name in emitted if name.lower() not in available}
    assert missing == set()


def test_supported_cql_executes_in_no_python_runtime() -> None:
    translated = translated_expression_sql(RUNTIME_CQL)

    with no_python_connection() as con:
        for name, sql_expr in translated.items():
            result = con.execute(f"SELECT {sql_expr}").fetchone()[0]
            assert result == EXPECTED[name], name


def test_no_python_math_macros_follow_cql_edge_cases() -> None:
    with no_python_connection() as con:
        assert con.execute("SELECT Power(-2, 0.5)").fetchone()[0] is None
        assert con.execute("SELECT Round(-2.5)::VARCHAR").fetchone()[0] == "-2.00000000"
        assert con.execute("SELECT RoundTo(-2.55, 1)::VARCHAR").fetchone()[0] == "-2.50000000"
