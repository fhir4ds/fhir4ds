"""CQL date/time operator part 1 parity checks."""

from __future__ import annotations

import duckdb
import pytest

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
    assert "dateComponent" in str(translated["YearComponent"])
    assert "cqlDifferenceBetween" in str(translated["DifferenceMonths"])
    assert "cqlDurationBetween" in str(translated["DurationDays"])


def test_cql_datetime_part1_duckdb_surface_matches_cpp_registration() -> None:
    expressions = [
        "SELECT dateComponent('2024-06-15', 'year')",
        "SELECT dateComponent('2024-06-15', 'month')",
        "SELECT dateComponent('T23:20:15.555', 'hour')",
        "SELECT dateComponent('2014', 'month')",
        "SELECT dateComponent('2014-01', 'day')",
        "SELECT dateAddQuantity('2024-01-31', '{\"value\":1,\"code\":\"mo\"}')",
        "SELECT dateAddQuantity('2024-01-01T10:00:00', '{\"value\":5,\"code\":\"h\"}')",
        "SELECT dateAddQuantity('2014T', '{\"value\":24,\"code\":\"mo\"}')",
        "SELECT cqlBeforeP('2024-01-01', '2024-02-01', 'month')",
        "SELECT cqlAfterP('2024-02-01', '2024-01-01', 'month')",
        "SELECT cqlDurationBetween('2024-01-01', '2024-01-31', 'day')",
        "SELECT cqlDurationBetween('2012-01-02', '2012', 'month')",
        "SELECT cqlDurationBetween('2005T', '2010T', 'year')",
        "SELECT cqlDurationBetween('2024', '2025', 'bogus')",
        "SELECT cqlDifferenceBetween('2012-01-02', '2012', 'month')",
        "SELECT cqlDifferenceBetween('2024', '2025', 'bogus')",
        "SELECT cqlDifferenceBetween('2000-10-10T10:05:45.500-06:00', '2000-10-10T10:05:45.900-07:00', 'millisecond')",
        "SELECT cqlDurationBetween('2024', '2025', 'month')",
        "SELECT dateAddQuantity('2024-01-01T10:00:00+14:30', '{\"value\":1,\"unit\":\"hour\"}')",
        "SELECT dateSubtractQuantity('2024-01-01T10:00:00+14:30', '{\"value\":1,\"unit\":\"hour\"}')",
        "SELECT dateComponent('2024-01-01T10:00:00+14:30', 'hour')",
        "SELECT dateComponent('2024-01-01T10:00:00+05:00', 'millisecond')",
        "SELECT dateComponent('T10:00:00+05:00', 'millisecond')",
        "SELECT dateComponent('2024-01-01T10:00:00.123+05:00', 'millisecond')",
        "SELECT cqlBeforeP('2024-01-01T10:00:00+14:30','2024-01-01T11:00:00+14:30','hour')",
        "SELECT cqlDurationBetween('2024-01-01T10:00:00+14:30','2024-01-01T11:00:00+14:30','hour')",
        "SELECT cqlDifferenceBetween('2024-01-01T10:00:00+14:30','2024-01-01T11:00:00+14:30','hour')",
        "SELECT dateComponent('2024-13', 'month')",
        "SELECT cqlBeforeP('2024-13', '2025-01', 'month')",
        "SELECT dateAddQuantity('T12', '{\"value\":61,\"unit\":\"minute\"}')",
        "SELECT dateAddQuantity('T12:30', '{\"value\":45,\"unit\":\"second\"}')",
        "SELECT dateSubtractQuantity('T00', '{\"value\":1,\"unit\":\"hour\"}')",
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


def test_cql_datetime_part1_explorer_component_timezone_suffix_regression() -> None:
    cql = """library DateTime1ExplorerComponent version '1.0.0'
using FHIR version '4.0.1'
context Patient
define MsOffsetNoMs: millisecond from @2024-01-01T10:00:00+05:00
define MsOffsetZuluNoMs: millisecond from @2024-01-01T10:00:00Z
define MsOffsetWithMs: millisecond from @2024-01-01T10:00:00.123+05:00
define SecOffsetNoMs: second from @2024-01-01T10:00:00+05:00
define QueryAliasMsNoMs: singleton from ({ @2024-01-01T10:00:00+05:00 } D return millisecond from D)
"""
    translated = translate_cql(cql)
    expected = {
        "MsOffsetNoMs": None,
        "MsOffsetZuluNoMs": None,
        "MsOffsetWithMs": 123,
        "SecOffsetNoMs": 0,
        "QueryAliasMsNoMs": None,
    }

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for name, expected_value in expected.items():
            sql = f"SELECT {translated[name].to_sql()}"
            assert py.execute(sql).fetchone() == (expected_value,), name
            assert cpp.execute(sql).fetchone() == (expected_value,), name
    finally:
        py.close()
        cpp.close()


def test_cql_datetime_part1_rejects_invalid_between_units() -> None:
    expressions = [
        "SELECT cqlDurationBetween('2024', '2025', 'bogus')",
        "SELECT cqlDifferenceBetween('2024', '2025', 'bogus')",
    ]

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for expression in expressions:
            assert py.execute(expression).fetchone() == (None,)
            assert cpp.execute(expression).fetchone() == (None,)
    finally:
        py.close()
        cpp.close()


def test_cql_datetime_part1_skeptic_regressions() -> None:
    cql = """library DateTime1Skeptic version '1.0.0'
using FHIR version '4.0.1'
context Patient
define DynamicDateTimeHour: DateTime(year from @2024-01-01, 2, 3, 4)
define DynamicDateTimeNegativeHalfTimezone: DateTime(year from @2024-01-01, 1, 1, 12, 0, 0, 0, -7.5)
define DynamicDateTimePositiveHalfTimezone: DateTime(year from @2024-01-01, 1, 1, 12, 0, 0, 0, 5.5)
define YearPrecisionDateTime: DateTime(2003)
define MonthPrecisionDateTime: DateTime(2003, 10)
define AddYearPrecisionDateTime: DateTime(2014) + 24 months
define DateFromYearPrecisionDateTime: date from DateTime(2012)
define DateFromMonthPrecisionDateTime: date from DateTime(2012, 5)
define DateFromDayPrecisionDateTime: date from DateTime(2012, 5, 10)
define DateFromHourPrecisionDateTime: date from DateTime(2012, 5, 10, 6)
define DynamicDateFromDateTime: date from DateTime(year from @2024-01-01, 2, 3, 4)
define TimeFromDateTime: time from DateTime(2012, 1, 1, 12, 30, 0, 0, -7)
define TimeFromDayPrecisionDateTime: time from DateTime(2012, 1, 1)
define DifferenceMonthsUncertain: difference in months between @2012-01-02 and @2012
define DifferenceMonthsUncertainCompare: difference in months between @2012-01-02 and @2012 > 5
define DifferenceMillisecondsTimezone: difference in milliseconds between DateTime(2000, 10, 10, 10, 5, 45, 500, -6.0) and DateTime(2000, 10, 10, 10, 5, 45, 900, -7.0)
define DurationYearsUncertain: years between DateTime(2005) and DateTime(2010)
define DurationYearsParenthesizedCompareTrue: (years between DateTime(2005) and DateTime(2010)) < 6
define DurationYearsParenthesizedCompareUncertain: (years between DateTime(2005) and DateTime(2010)) < 5
define DurationDaysParenthesizedScalarCompare: (days between @2024-01-01 and @2024-01-02) < 2
define DurationDifferenceArithmeticDivision: Truncate(280 - (difference in days between @2024-01-01 and @2024-01-08)) / 7
define DurationDifferenceArithmeticDiv: (280 - (difference in days between @2024-01-01 and @2024-01-08)) div 7
define DurationMonthsUncertain: months between @2012-01-02 and @2012
define DurationMonthsUncertainCompare: months between @2012-01-02 and @2012 > 5
define DurationMonthsUncertainLessThan11: months between @2012-01-02 and @2012 < 11
define AddInvalidTimezone: @2024-01-01T10:00:00+14:30 + 1 hour
define BeforeInvalidTimezone: @2024-01-01T10:00:00+14:30 before hour of @2024-01-01T11:00:00+14:30
define DurationInvalidTimezone: hours between @2024-01-01T10:00:00+14:30 and @2024-01-01T11:00:00+14:30
define DifferenceInvalidTimezone: difference in hours between @2024-01-01T10:00:00+14:30 and @2024-01-01T11:00:00+14:30
define DynamicDateInvalidMonth: Date(year from @2024-01-01, 13)
define DynamicDateTimeInvalidHour: DateTime(year from @2024-01-01, 1, 1, 24)
define DynamicDateTimeInvalidTimezone: DateTime(year from @2024-01-01, 1, 1, 12, 0, 0, 0, 14.5)
define MonthFromInvalidDynamicDate: month from Date(year from @2024-01-01, 13)
define InvalidDynamicDateBefore: Date(year from @2024-01-01, 13) before month of Date(year from @2025-01-01, 1)
define TimeWithMillisecond: Time(12, 30, 15, 250)
define MillisecondFromTime: millisecond from Time(12, 30, 15, 250)
define TimeInvalidHour: Time(24, 0)
"""
    translated = translate_cql(cql)
    expected = {
        "DynamicDateTimeHour": "2024-02-03T04",
        "DynamicDateTimeNegativeHalfTimezone": "2024-01-01T12:00:00.000-07:30",
        "DynamicDateTimePositiveHalfTimezone": "2024-01-01T12:00:00.000+05:30",
        "YearPrecisionDateTime": "2003T",
        "MonthPrecisionDateTime": "2003-10T",
        "AddYearPrecisionDateTime": "2016T",
        "DateFromYearPrecisionDateTime": "2012",
        "DateFromMonthPrecisionDateTime": "2012-05",
        "DateFromDayPrecisionDateTime": "2012-05-10",
        "DateFromHourPrecisionDateTime": "2012-05-10",
        "DynamicDateFromDateTime": "2024-02-03",
        "TimeFromDateTime": "T12:30:00.000-07:00",
        "TimeFromDayPrecisionDateTime": None,
        "DifferenceMonthsUncertain": '{"start":0,"end":11,"lowClosed":true,"highClosed":true}',
        "DifferenceMonthsUncertainCompare": None,
        "DifferenceMillisecondsTimezone": "3600400",
        "DurationYearsUncertain": '{"start":4,"end":5,"lowClosed":true,"highClosed":true}',
        "DurationYearsParenthesizedCompareTrue": True,
        "DurationYearsParenthesizedCompareUncertain": None,
        "DurationDaysParenthesizedScalarCompare": True,
        "DurationDifferenceArithmeticDivision": 39.0,
        "DurationDifferenceArithmeticDiv": 39.0,
        "DurationMonthsUncertain": '{"start":0,"end":10,"lowClosed":true,"highClosed":true}',
        "DurationMonthsUncertainCompare": None,
        "DurationMonthsUncertainLessThan11": True,
        "AddInvalidTimezone": None,
        "BeforeInvalidTimezone": None,
        "DurationInvalidTimezone": None,
        "DifferenceInvalidTimezone": None,
        "DynamicDateInvalidMonth": None,
        "DynamicDateTimeInvalidHour": None,
        "DynamicDateTimeInvalidTimezone": None,
        "MonthFromInvalidDynamicDate": None,
        "InvalidDynamicDateBefore": None,
        "TimeWithMillisecond": "T12:30:15.250",
        "MillisecondFromTime": 250,
        "TimeInvalidHour": None,
    }

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        assert "ToDate" in translated["DynamicDateFromDateTime"].to_sql()
        for name, expected_value in expected.items():
            sql = f"SELECT {translated[name].to_sql()}"
            assert py.execute(sql).fetchone() == (expected_value,)
            assert cpp.execute(sql).fetchone() == (expected_value,)
    finally:
        py.close()
        cpp.close()


@pytest.mark.parametrize(
    "expression",
    [
        "Date(2012.5)",
        "Date(2012, 1.5)",
        "DateTime(2012.5)",
        "DateTime(2012, 1.5)",
        "Date(2012 + 0.5)",
        "Date(2012, 1 + 0.5)",
        "DateTime(2012 + 0.5)",
        "DateTime(2012, 1 + 0.5)",
    ],
)
def test_cql_datetime_part1_rejects_non_integer_constructor_components(expression: str) -> None:
    cql = f"""library DateTime1HistorianInvalid version '1.0.0'
using FHIR version '4.0.1'
context Patient
define InvalidCtor: {expression}
"""
    with pytest.raises(ValueError):
        translate_cql(cql)


def test_cql_datetime_part1_explorer_year_target_duration_uncertainty() -> None:
    """CQL-13 EXPLORER: years-target duration_high_boundary for year-precision
    operand must max month/day so the maximum whole-year count is returned.

    Per CQL §DurationBetween: when operands have different precision, the
    result is an interval representing the possible values. The official
    conformance test
    ``years between DateTime(2005) and DateTime(2010) // Interval[4, 5]``
    already exercises the symmetric year-vs-year case; this regression
    covers the asymmetric day-precision-start vs year-precision-end case.
    """
    cql = """library DateTime1ExplorerYearTarget version '1.0.0'
using FHIR version '4.0.1'
context Patient
define DurationYearsAsymmetric: years between @2012-06-01 and @2014
define DurationYearsAsymmetricReverse: years between @2014 and @2012-06-01
define DifferenceYearsAsymmetric: difference in years between @2012-06-01 and @2014
define DurationMonthsAsymmetric: months between @2012-06-01 and @2014
define DifferenceMonthsAsymmetric: difference in months between @2012-06-01 and @2014
define DurationDaysAsymmetric: days between @2012-06-01 and @2014
"""
    translated = translate_cql(cql)
    expected = {
        # min: start_high (2012-06-01T23:59:59.999) -> end_low (2014-01-01) = 1 year
        # max: start_low (2012-06-01T00:00:00) -> end_high (2014-12-01) = 2 years
        "DurationYearsAsymmetric": '{"start":1,"end":2,"lowClosed":true,"highClosed":true}',
        "DurationYearsAsymmetricReverse": '{"start":-2,"end":-1,"lowClosed":true,"highClosed":true}',
        # difference counts crossed boundaries; min=max=2
        "DifferenceYearsAsymmetric": "2",
        # months: from Jun 1 2012 to Jan 1 2014 = 19 whole months
        #         (Jun 2012 + 19mo = Jan 1 2014, midnight convention);
        #         from Jun 1 2012 to Dec 1 2014 = 30 whole months
        "DurationMonthsAsymmetric": '{"start":19,"end":30,"lowClosed":true,"highClosed":true}',
        # difference months: crossed boundaries 19..30
        "DifferenceMonthsAsymmetric": '{"start":19,"end":30,"lowClosed":true,"highClosed":true}',
        # days: from Jun 1 2012 to Dec 31 2014 = 943 days max
        "DurationDaysAsymmetric": '{"start":578,"end":943,"lowClosed":true,"highClosed":true}',
    }
    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for name, expected_value in expected.items():
            sql = f"SELECT {translated[name].to_sql()}"
            assert py.execute(sql).fetchone() == (expected_value,), (
                f"Python mismatch for {name}"
            )
            assert cpp.execute(sql).fetchone() == (expected_value,), (
                f"C++ mismatch for {name}"
            )
    finally:
        py.close()
        cpp.close()


def test_cql_datetime_part1_explorer_timezoneoffset_from_z_suffix() -> None:
    """CQL-13 EXPLORER: timezoneoffset from @...Z must return 0.0.

    Per CQL §DateTime ISO-8601 representation, ``Z`` is the UTC designator
    and is equivalent to ``+00:00``. The extractor must therefore return
    ``0.0`` for ``Z``-suffixed values, not null.
    """
    cql = """library DateTime1ExplorerZSuffix version '1.0.0'
using FHIR version '4.0.1'
context Patient
define TimeZoneOffsetFromZ: timezoneoffset from @2024-05-15T10:30:45.500Z
define TimeZoneOffsetFromZNoMs: timezoneoffset from @2024-05-15T10:30:45Z
define TimeZoneOffsetFromPlusZero: timezoneoffset from @2024-05-15T10:30:45.500+00:00
define TimeZoneOffsetFromMinusZero: timezoneoffset from @2024-05-15T10:30:45.500-00:00
define TimeZoneOffsetNoOffset: timezoneoffset from @2024-05-15T10:30:45.500
"""
    translated = translate_cql(cql)
    expected = {
        "TimeZoneOffsetFromZ": 0.0,
        "TimeZoneOffsetFromZNoMs": 0.0,
        "TimeZoneOffsetFromPlusZero": 0.0,
        "TimeZoneOffsetFromMinusZero": 0.0,
        "TimeZoneOffsetNoOffset": None,
    }
    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for name, expected_value in expected.items():
            sql = f"SELECT {translated[name].to_sql()}"
            assert py.execute(sql).fetchone() == (expected_value,), (
                f"Python mismatch for {name}"
            )
            assert cpp.execute(sql).fetchone() == (expected_value,), (
                f"C++ mismatch for {name}"
            )
    finally:
        py.close()
        cpp.close()


def test_cql_datetime_part1_week_difference_and_date_unit_restriction() -> None:
    """CQL 1.5 STU4 §8.7 / §8.1 regression coverage (CQL-13 SKEPTIC).

    §8.7 Difference: Sunday is the first day of the week for counting
    boundaries crossed. §8.1 Add / §8.15 Subtract: for Date values the
    quantity unit must be years, months, weeks, or days (sub-day units
    produce null, not a silently truncated no-op).
    """
    cql = """library DateTime13 version '1.0.0'
using FHIR version '4.0.1'
context Patient
define DiffWeeksCrossingSunday: difference in weeks between @2024-01-04 and @2024-01-10
define DiffWeeksSatToSun: difference in weeks between @2024-01-06 and @2024-01-07
define DiffWeeksSameSundayWeek: difference in weeks between @2024-01-01 and @2024-01-06
define DiffWeeksMultipleOfSeven: difference in weeks between @2024-01-01 and @2024-01-15
define DiffWeeksBackwardAcrossSunday: difference in weeks between @2024-01-10 and @2024-01-04
define DiffWeeksSundayToSunday: difference in weeks between @2024-01-07 and @2024-01-14
define DurWeeksThuToWed: weeks between @2024-01-04 and @2024-01-10
define DiffWeeksTimeComponents: difference in weeks between @2024-01-06T23:00:00 and @2024-01-07T01:00:00
define AddHourToDateIsNull: @2024-01-01 + 1 hour
define AddMinuteToDateIsNull: @2024-01-01 + 30 'min'
define AddSecondToDateIsNull: @2024-01-01 + 90 's'
define AddMillisecondToDateIsNull: @2024-01-01 + 1500 'ms'
define SubtractHourFromDateIsNull: @2024-01-01 - 1 hour
define AddDayToDateStillWorks: @2024-01-01 + 1 day
define AddHourToDateTimeStillWorks: @2024-01-01T00:00:00 + 1 hour
define AddMinuteToHourPrecisionStillWorks: @2024-01-01T10 + 61 minutes
"""
    translated = translate_cql(cql)
    expected = {
        "DiffWeeksCrossingSunday": "1",
        "DiffWeeksSatToSun": "1",
        "DiffWeeksSameSundayWeek": "0",
        "DiffWeeksMultipleOfSeven": "2",
        "DiffWeeksBackwardAcrossSunday": "-1",
        "DiffWeeksSundayToSunday": "1",
        "DurWeeksThuToWed": "0",
        "DiffWeeksTimeComponents": "1",
        "AddHourToDateIsNull": None,
        "AddMinuteToDateIsNull": None,
        "AddSecondToDateIsNull": None,
        "AddMillisecondToDateIsNull": None,
        "SubtractHourFromDateIsNull": None,
        "AddDayToDateStillWorks": "2024-01-02",
        "AddHourToDateTimeStillWorks": "2024-01-01T01:00:00",
        "AddMinuteToHourPrecisionStillWorks": "2024-01-01T11",
    }
    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for name, expected_value in expected.items():
            sql = f"SELECT {translated[name].to_sql()}"
            assert py.execute(sql).fetchone() == (expected_value,), (
                f"Python mismatch for {name}: {py.execute(sql).fetchone()} != {expected_value}"
            )
            assert cpp.execute(sql).fetchone() == (expected_value,), (
                f"C++ mismatch for {name}: {cpp.execute(sql).fetchone()} != {expected_value}"
            )
    finally:
        py.close()
        cpp.close()


def test_cql_datetime_part1_subday_difference_boundaries_and_time_unit_restriction() -> None:
    """CQL 1.5 STU4 §8.7 / §8.1 regression coverage (CQL-13 HISTORIAN).

    §8.7 Difference for sub-day precisions counts boundaries crossed
    (floor(epoch/unit) index difference), NOT truncated elapsed duration
    (which is §8.8 Duration semantics). §8.1 Add / §8.15 Subtract: for
    Time values the quantity unit must be hours, minutes, seconds, or
    milliseconds (day-level units produce null, not a silent no-op).
    """
    cql = """library DateTime13b version '1.0.0'
using FHIR version '4.0.1'
context Patient
define DiffHoursBoundary: difference in hours between @2024-01-01T10:30:00 and @2024-01-01T12:15:00
define DurHoursSame: hours between @2024-01-01T10:30:00 and @2024-01-01T12:15:00
define DiffHoursNegative: difference in hours between @2024-01-01T12:15:00 and @2024-01-01T10:30:00
define DiffMinutesBoundary: difference in minutes between @T10:30:30 and @T10:32:10
define DurMinutesSame: minutes between @T10:30:30 and @T10:32:10
define DiffSecondsBoundary: difference in seconds between @T00:00:00.900 and @T00:00:02.100
define DurSecondsSame: seconds between @T00:00:00.900 and @T00:00:02.100
define DiffHoursAlignedStillWorks: difference in hours between @2024-01-01T10:00:00 and @2024-01-01T12:00:00
define DiffHoursTimezone: difference in hours between @2024-01-01T12:00:00-07:00 and @2024-01-01T12:00:00-05:00
define TimeAddWeekIsNull: @T12:30 + 1 week
define TimeAddDayIsNull: @T12:30 + 1 day
define TimeAddDayUCUMIsNull: @T12:30 + 1 'd'
define TimeSubtractWeekIsNull: @T12:30 - 1 week
define TimeAddHourStillWorks: @T12:30:00 + 1 hour
define TimeAddMinuteStillWorks: @T12:30 + 45 minutes
"""
    translated = translate_cql(cql)
    expected = {
        "DiffHoursBoundary": "2",
        "DurHoursSame": "1",
        "DiffHoursNegative": "-2",
        "DiffMinutesBoundary": "2",
        "DurMinutesSame": "1",
        "DiffSecondsBoundary": "2",
        "DurSecondsSame": "1",
        "DiffHoursAlignedStillWorks": "2",
        "DiffHoursTimezone": "-2",
        "TimeAddWeekIsNull": None,
        "TimeAddDayIsNull": None,
        "TimeAddDayUCUMIsNull": None,
        "TimeSubtractWeekIsNull": None,
        "TimeAddHourStillWorks": "T13:30:00",
        "TimeAddMinuteStillWorks": "T13:15",
    }
    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for name, expected_value in expected.items():
            sql = f"SELECT {translated[name].to_sql()}"
            assert py.execute(sql).fetchone() == (expected_value,), (
                f"Python mismatch for {name}: {py.execute(sql).fetchone()} != {expected_value}"
            )
            assert cpp.execute(sql).fetchone() == (expected_value,), (
                f"C++ mismatch for {name}: {cpp.execute(sql).fetchone()} != {expected_value}"
            )
    finally:
        py.close()
        cpp.close()


def test_cql_datetime_part1_explorer2_year_month_uncertainty_and_tz_and_ctor_nulls() -> None:
    """CQL-13 EXPLORER (2nd launch) regressions.

    1. Calendar year/month duration with a month-precision operand must
       return an uncertainty interval (day-of-month unknown), mirroring the
       official test ``years between DateTime(2005) and DateTime(2010)``.
       Day-precision date-only operands stay crisp.
    2. Python engine must agree with C++ when the end operand of a
       years/months duration is a timezone-aware DateTime (wall-component
       comparison, no silent null).
    3. Constructors accept trailing static-null components, including below
       a specified timezoneOffset; a static null ABOVE a specified
       component is the spec's DateInvalid form and is rejected.
    """
    cql = """library DateTime1Explorer2 version '1.0.0'
using FHIR version '4.0.1'
context Patient
define YrsMonthPrecUncertain: years between @1975-03 and @2020-03-01
define YrsMonthPrecBothUncertain: years between @1975-03 and @2020-03
define YrsMonthPrecCrisp: years between @1975-03 and @2020-03-31
define YrsDayPrecCrisp: years between @1975-03-31 and @2020-03-01
define MonsMonthPrecUncertain: months between @1975-03 and @1975-03-31
define MonsDayPrecCrisp: months between @1975-03-02 and @2020-03-01
define YrsTzAwareEnd: years between @1975-03-31 and @2020-02-29T10:30:00-07:00
define CtorDateTrailingNull: Date(2024, null)
define CtorDateTrailingNull3: Date(2024, null, null)
define CtorDTNullBelowTz: DateTime(2024, 1, 1, 10, 30, null, null, -7.0)
define CtorDTNullTz: DateTime(2024, 1, 1, 10, 30, 0, 0, null)
define CtorDTFullTz: DateTime(2024, 1, 1, 10, 30, 0, 0, -7.0)
define CtorDTHourOnlyTz: DateTime(2024, 1, 1, 10, null, null, null, -7.0)
"""
    translated = translate_cql(cql)
    expected = {
        "YrsMonthPrecUncertain": '{"start":44,"end":45,"lowClosed":true,"highClosed":true}',
        "YrsMonthPrecBothUncertain": '{"start":44,"end":45,"lowClosed":true,"highClosed":true}',
        "YrsMonthPrecCrisp": "45",
        "YrsDayPrecCrisp": "44",
        "MonsMonthPrecUncertain": "0",
        "MonsDayPrecCrisp": "539",
        "YrsTzAwareEnd": "44",
        "CtorDateTrailingNull": "2024",
        "CtorDateTrailingNull3": "2024",
        "CtorDTNullBelowTz": "2024-01-01T10:30-07:00",
        "CtorDTNullTz": "2024-01-01T10:30:00.000",
        "CtorDTFullTz": "2024-01-01T10:30:00.000-07:00",
        "CtorDTHourOnlyTz": "2024-01-01T10-07:00",
    }
    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for name, expected_value in expected.items():
            sql = f"SELECT {translated[name].to_sql()}"
            assert py.execute(sql).fetchone() == (expected_value,), (
                f"Python mismatch for {name}: {py.execute(sql).fetchone()} != {expected_value}"
            )
            assert cpp.execute(sql).fetchone() == (expected_value,), (
                f"C++ mismatch for {name}: {cpp.execute(sql).fetchone()} != {expected_value}"
            )
    finally:
        py.close()
        cpp.close()


def test_cql_datetime_part1_explorer2_interior_null_component_rejected() -> None:
    """CQL §22.5 DateInvalid: DateTime(2012, 1, 1, 12, null, 0, 0, -7) has a
    specified second below an unspecified minute and must be rejected."""
    cql = """library DateTime1Explorer2Invalid version '1.0.0'
using FHIR version '4.0.1'
context Patient
define Bad: DateTime(2012, 1, 1, 12, null, 0, 0, -7)
"""
    with pytest.raises(Exception):
        translate_cql(cql)


def test_cql_datetime_part2_same_as_without_precision_and_cross_type() -> None:
    """CQL 1.5 §8.12/§9.24 + Cql.g4 concurrentWithIntervalOperatorPhrase.

    Bare `same as` (no precision) must parse and compare at the finest
    precision specified in either input, null when uncertain; intervals
    compare start and end points. Mixed Time/DateTime operand pairs are
    undefined per the same-type signatures and must be null (uncertain),
    never a definitive false from zero-filled date components. Now() must
    respect the CQL DateTime millisecond precision limit.
    """
    cql = """library DateTime2SameAs version '1.0.0'
using FHIR version '4.0.1'
context Patient
define PointEqual: @2024-01-01 same as @2024-01-01
define PointUncertain: @2012-01-01 same as @2012-01
define MonthEqual: @2012-01 same as @2012-01
define TimeEqual: @T10:30 same as @T10:30
define TimeUncertain: @T10:30:00 same as @T10:30
define IntervalEqual: Interval[@2024-01-01, @2024-06-01] same as Interval[@2024-01-01, @2024-06-01]
define IntervalFalse: Interval[@2024-01-01, @2024-06-01] same as Interval[@2024-02-01, @2024-06-01]
define IntervalUncertain: Interval[@2024-01, @2024-06-01] same as Interval[@2024-01-15, @2024-06-01]
define CrossTypeSameAs: @T13:36:12 same second as @2024-01-01T13:36:12.500
define CrossTypeSameOrAfter: @T13:36:12 same second or after @2024-01-01T13:36:12.500
define TimeSameSecondStillCertain: @T13:36:12 same second as @T13:36:12.500
define NowValue: Now()
"""
    translated = translate_cql(cql)
    expected = {
        "PointEqual": "true",
        "PointUncertain": None,
        "MonthEqual": "true",
        "TimeEqual": "true",
        "TimeUncertain": None,
        "IntervalEqual": "true",
        "IntervalFalse": "false",
        "IntervalUncertain": None,
        "CrossTypeSameAs": None,
        "CrossTypeSameOrAfter": None,
        "TimeSameSecondStillCertain": "true",
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
        # Now() fractional seconds must be exactly 3 digits (millisecond model).
        for con in (py, cpp):
            now_str = con.execute(f"SELECT ({translated['NowValue'].to_sql()})").fetchone()[0]
            assert isinstance(now_str, str) and "T" in now_str
            frac = now_str.split("T")[1].split("-")[0].split("+")[0].rstrip("Z").split(".")
            assert len(frac) == 1 or len(frac[1]) == 3, f"Now() sub-millisecond precision: {now_str!r}"
    finally:
        py.close()
        cpp.close()


def test_cql_datetime_part2_no_precision_interval_same_or_and_time_null_ctor() -> None:
    """CQL 1.5 §9.25/§9.26 + §8.16.

    No-precision `same or after` / `same or before` on interval (or mixed
    point/interval) operands must compare start-of-left vs end-of-right
    (§9.25) / end-of-left vs start-of-right (§9.26) at the finest precision
    of either input — the same bound extraction the precision variants use.
    Previously the raw interval strings reached the point-comparison UDF:
    the native engine compared low-vs-low (definitive wrong booleans) while
    the Python fallback returned null. `Time(null)` (no component specified)
    evaluates to null like Time(null, null) instead of crashing translation.
    """
    cql = """library DateTime2Historian version '1.0.0'
using FHIR version '4.0.1'
context Patient
define SoaIntFalse: Interval[@2012-01-01, @2012-01-02] same or after Interval[@2012-01-01, @2012-01-03]
define SoaIntTrue: Interval[@2012-01-04, @2012-01-05] same or after Interval[@2012-01-01, @2012-01-03]
define SoaPointInterval: @2012-01-03 same or after Interval[@2012-01-01, @2012-01-04]
define SoaIntervalPoint: Interval[@2012-01-04, @2012-01-05] same or after @2012-01-03
define SobIntTrue: Interval[@2012-01-01, @2012-01-02] same or before Interval[@2012-01-03, @2012-01-04]
define SobIntFalse: Interval[@2012-01-01, @2012-01-03] same or before Interval[@2012-01-01, @2012-01-02]
define SobPointInterval: @2012-01-05 same or before Interval[@2012-01-06, @2012-01-08]
define SobUncertain: Interval[@2012-01-02, @2012-01-03] same or before Interval[@2012-01, @2012-06]
define PointsUnaffected: @2012-01-02 same or after @2012-01-01
define PointsUncertain: @2012-01-02 same or after @2012-01
define TimeNullSingle: Time(null)
define TimeInvalidSpec: Time(12, null, 0, 0)
define TimeHourStillWorks: Time(12)
"""
    translated = translate_cql(cql)
    expected = {
        "SoaIntFalse": "false",
        "SoaIntTrue": "true",
        "SoaPointInterval": "false",
        "SoaIntervalPoint": "true",
        "SobIntTrue": "true",
        "SobIntFalse": "false",
        "SobPointInterval": "true",
        "SobUncertain": None,
        "PointsUnaffected": "true",
        "PointsUncertain": None,
        "TimeNullSingle": None,
        "TimeInvalidSpec": None,
        "TimeHourStillWorks": "t12",
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
