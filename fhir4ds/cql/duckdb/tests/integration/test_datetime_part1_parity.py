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
        # months: from Jun 1 2012 to Jan 1 2014 = 18 whole months;
        #         from Jun 1 2012 to Dec 1 2014 = 30 whole months
        "DurationMonthsAsymmetric": '{"start":18,"end":30,"lowClosed":true,"highClosed":true}',
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
