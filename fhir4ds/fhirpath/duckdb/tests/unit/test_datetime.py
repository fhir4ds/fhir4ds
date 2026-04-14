"""
Unit tests for FHIRPath Date/Time functions.

Tests date/time handling per FHIRPath specification:
- Date/time literals
- Date/time arithmetic
- Duration components
- Component extraction
- Current time functions
- Comparison operations
"""

from __future__ import annotations

from datetime import date, datetime, time as dt_time, timedelta
from unittest import mock

import pytest

from ...functions.datetime import (
    DatePrecision,
    TimePrecision,
    FHIRDate,
    FHIRDateTime,
    FHIRTime,
    FHIRDuration,
    DateTimeLiteral,
    DateTimeDuration,
    DateTimeArithmetic,
    DateTimeFunctions,
    DateTimeComparisons,
)


class TestFHIRDate:
    """Tests for FHIRDate class."""

    def test_create_date_full(self) -> None:
        """Test creating a full date."""
        d = FHIRDate(value=date(2019, 1, 15), precision=DatePrecision.DAY)
        assert d.value == date(2019, 1, 15)
        assert d.precision == DatePrecision.DAY
        assert str(d) == "2019-01-15"

    def test_create_date_year_month(self) -> None:
        """Test creating a year-month date."""
        d = FHIRDate(value=date(2019, 1, 1), precision=DatePrecision.MONTH)
        assert str(d) == "2019-01"

    def test_create_date_year_only(self) -> None:
        """Test creating a year-only date."""
        d = FHIRDate(value=date(2019, 1, 1), precision=DatePrecision.YEAR)
        assert str(d) == "2019"

    def test_date_with_timezone(self) -> None:
        """Test date with timezone."""
        d = FHIRDate(value=date(2019, 1, 15), precision=DatePrecision.DAY, timezone="+05:00")
        assert str(d) == "2019-01-15+05:00"

    def test_date_equality(self) -> None:
        """Test date equality comparison."""
        d1 = FHIRDate(value=date(2019, 1, 15), precision=DatePrecision.DAY)
        d2 = FHIRDate(value=date(2019, 1, 15), precision=DatePrecision.DAY)
        d3 = FHIRDate(value=date(2019, 1, 16), precision=DatePrecision.DAY)
        d4 = FHIRDate(value=date(2019, 1, 15), precision=DatePrecision.MONTH)

        assert d1 == d2
        assert d1 != d3
        # Different precision means different dates
        assert d1 != d4

    def test_date_ordering(self) -> None:
        """Test date ordering comparisons."""
        d1 = FHIRDate(value=date(2019, 1, 15), precision=DatePrecision.DAY)
        d2 = FHIRDate(value=date(2019, 1, 20), precision=DatePrecision.DAY)
        d3 = FHIRDate(value=date(2019, 2, 1), precision=DatePrecision.DAY)

        assert d1 < d2
        assert d2 < d3
        assert d1 < d3
        assert d1 <= d1
        assert d2 > d1
        assert d3 >= d2

    def test_date_ordering_different_precision(self) -> None:
        """Test date ordering with different precision."""
        d1 = FHIRDate(value=date(2019, 1, 1), precision=DatePrecision.YEAR)
        d2 = FHIRDate(value=date(2019, 6, 15), precision=DatePrecision.DAY)
        d3 = FHIRDate(value=date(2020, 1, 1), precision=DatePrecision.YEAR)

        # Compare at year precision
        assert d1 <= d2  # Same year
        assert d1 < d3  # Different year

    def test_from_string(self) -> None:
        """Test parsing date from string."""
        d = FHIRDate.from_string("@2019-01-15")
        assert d.value == date(2019, 1, 15)
        assert d.precision == DatePrecision.DAY


class TestFHIRDateTime:
    """Tests for FHIRDateTime class."""

    def test_create_datetime_full(self) -> None:
        """Test creating a full datetime."""
        dt = FHIRDateTime(
            value=datetime(2019, 1, 15, 12, 30, 45),
            precision=DatePrecision.SECOND
        )
        assert dt.value == datetime(2019, 1, 15, 12, 30, 45)
        assert str(dt) == "2019-01-15T12:30:45"

    def test_create_datetime_with_milliseconds(self) -> None:
        """Test datetime with milliseconds."""
        dt = FHIRDateTime(
            value=datetime(2019, 1, 15, 12, 30, 45, 123000),
            precision=DatePrecision.MILLISECOND
        )
        assert str(dt) == "2019-01-15T12:30:45.123"

    def test_datetime_equality(self) -> None:
        """Test datetime equality."""
        dt1 = FHIRDateTime(value=datetime(2019, 1, 15, 12, 30), precision=DatePrecision.MINUTE)
        dt2 = FHIRDateTime(value=datetime(2019, 1, 15, 12, 30), precision=DatePrecision.MINUTE)
        dt3 = FHIRDateTime(value=datetime(2019, 1, 15, 12, 31), precision=DatePrecision.MINUTE)

        assert dt1 == dt2
        assert dt1 != dt3

    def test_datetime_ordering(self) -> None:
        """Test datetime ordering comparisons."""
        dt1 = FHIRDateTime(value=datetime(2019, 1, 15, 12, 30), precision=DatePrecision.MINUTE)
        dt2 = FHIRDateTime(value=datetime(2019, 1, 15, 12, 45), precision=DatePrecision.MINUTE)

        assert dt1 < dt2
        assert dt2 > dt1

    def test_date_component(self) -> None:
        """Test extracting date component."""
        dt = FHIRDateTime(value=datetime(2019, 1, 15, 12, 30, 45), precision=DatePrecision.SECOND)
        date_part = dt.date_component
        assert isinstance(date_part, FHIRDate)
        assert date_part.value == date(2019, 1, 15)

    def test_time_component(self) -> None:
        """Test extracting time component."""
        dt = FHIRDateTime(value=datetime(2019, 1, 15, 12, 30, 45), precision=DatePrecision.SECOND)
        time_part = dt.time_component
        assert isinstance(time_part, FHIRTime)
        assert time_part.value.hour == 12
        assert time_part.value.minute == 30


class TestFHIRTime:
    """Tests for FHIRTime class."""

    def test_create_time_full(self) -> None:
        """Test creating a full time."""
        t = FHIRTime(value=dt_time(12, 30, 45), precision=TimePrecision.SECOND)
        assert t.value == dt_time(12, 30, 45)
        assert str(t) == "T12:30:45"

    def test_create_time_hour_only(self) -> None:
        """Test creating hour-only time."""
        t = FHIRTime(value=dt_time(12, 0, 0), precision=TimePrecision.HOUR)
        assert str(t) == "T12"

    def test_create_time_with_milliseconds(self) -> None:
        """Test time with milliseconds."""
        t = FHIRTime(value=dt_time(12, 30, 45, 123000), precision=TimePrecision.MILLISECOND)
        assert str(t) == "T12:30:45.123"

    def test_time_equality(self) -> None:
        """Test time equality."""
        t1 = FHIRTime(value=dt_time(12, 30), precision=TimePrecision.MINUTE)
        t2 = FHIRTime(value=dt_time(12, 30), precision=TimePrecision.MINUTE)
        t3 = FHIRTime(value=dt_time(12, 31), precision=TimePrecision.MINUTE)

        assert t1 == t2
        assert t1 != t3

    def test_time_ordering(self) -> None:
        """Test time ordering comparisons."""
        t1 = FHIRTime(value=dt_time(10, 0), precision=TimePrecision.MINUTE)
        t2 = FHIRTime(value=dt_time(12, 30), precision=TimePrecision.MINUTE)
        t3 = FHIRTime(value=dt_time(15, 45), precision=TimePrecision.MINUTE)

        assert t1 < t2
        assert t2 < t3
        assert t1 < t3

    def test_time_ordering_different_precision(self) -> None:
        """Test time ordering with different precision."""
        t1 = FHIRTime(value=dt_time(12, 0, 0), precision=TimePrecision.HOUR)
        t2 = FHIRTime(value=dt_time(12, 30, 45), precision=TimePrecision.SECOND)

        # Both have same hour, so at hour precision they're equal
        assert t1 <= t2
        assert not (t1 < t2)
        assert not (t1 > t2)


class TestFHIRDuration:
    """Tests for FHIRDuration class."""

    def test_create_duration_years(self) -> None:
        """Test creating duration with years."""
        d = FHIRDuration(years=5)
        assert d.years == 5
        assert str(d) == "5 years"

    def test_create_duration_singular(self) -> None:
        """Test creating duration with singular unit."""
        d = FHIRDuration(years=1)
        assert str(d) == "1 year"

    def test_create_duration_multiple_units(self) -> None:
        """Test creating duration with multiple units."""
        d = FHIRDuration(years=1, months=2, days=3)
        assert "1 year" in str(d)
        assert "2 months" in str(d)
        assert "3 days" in str(d)

    def test_duration_negation(self) -> None:
        """Test negating duration."""
        d = FHIRDuration(years=5, days=3)
        neg = -d
        assert neg.years == -5
        assert neg.days == -3

    def test_duration_addition(self) -> None:
        """Test adding durations."""
        d1 = FHIRDuration(years=1, months=6)
        d2 = FHIRDuration(years=2, days=10)
        result = d1 + d2
        assert result.years == 3
        assert result.months == 6
        assert result.days == 10

    def test_duration_subtraction(self) -> None:
        """Test subtracting durations."""
        d1 = FHIRDuration(years=5, days=10)
        d2 = FHIRDuration(years=2, days=3)
        result = d1 - d2
        assert result.years == 3
        assert result.days == 7

    def test_duration_to_timedelta(self) -> None:
        """Test converting to timedelta."""
        d = FHIRDuration(days=5, hours=12)
        td = d.to_timedelta()
        assert td == timedelta(days=5, hours=12)

    def test_duration_is_empty(self) -> None:
        """Test checking if duration is empty."""
        empty = FHIRDuration()
        non_empty = FHIRDuration(days=1)
        assert empty.is_empty
        assert not non_empty.is_empty


class TestDateTimeLiteral:
    """Tests for DateTimeLiteral parsing."""

    def test_parse_year(self) -> None:
        """Test parsing year-only date."""
        d = DateTimeLiteral.parse_date("@2019")
        assert d.value.year == 2019
        assert d.precision == DatePrecision.YEAR

    def test_parse_year_month(self) -> None:
        """Test parsing year-month date."""
        d = DateTimeLiteral.parse_date("@2019-01")
        assert d.value.year == 2019
        assert d.value.month == 1
        assert d.precision == DatePrecision.MONTH

    def test_parse_full_date(self) -> None:
        """Test parsing full date."""
        d = DateTimeLiteral.parse_date("@2019-01-15")
        assert d.value == date(2019, 1, 15)
        assert d.precision == DatePrecision.DAY

    def test_parse_date_without_at(self) -> None:
        """Test parsing date without @ prefix."""
        d = DateTimeLiteral.parse_date("2019-01-15")
        assert d.value == date(2019, 1, 15)

    def test_parse_time_hour_minute(self) -> None:
        """Test parsing hour:minute time."""
        t = DateTimeLiteral.parse_time("@T12:30")
        assert t.value.hour == 12
        assert t.value.minute == 30
        assert t.precision == TimePrecision.MINUTE

    def test_parse_time_with_seconds(self) -> None:
        """Test parsing time with seconds."""
        t = DateTimeLiteral.parse_time("@T12:30:45")
        assert t.value.second == 45
        assert t.precision == TimePrecision.SECOND

    def test_parse_time_with_milliseconds(self) -> None:
        """Test parsing time with milliseconds."""
        t = DateTimeLiteral.parse_time("@T12:30:45.123")
        assert t.value.microsecond == 123000
        assert t.precision == TimePrecision.MILLISECOND

    def test_parse_datetime(self) -> None:
        """Test parsing full datetime."""
        dt = DateTimeLiteral.parse_datetime("@2019-01-15T12:30:45")
        assert dt.value == datetime(2019, 1, 15, 12, 30, 45)
        assert dt.precision == DatePrecision.SECOND

    def test_parse_datetime_with_timezone(self) -> None:
        """Test parsing datetime with timezone."""
        dt = DateTimeLiteral.parse_datetime("@2019-01-15T12:30:45Z")
        assert dt.value == datetime(2019, 1, 15, 12, 30, 45)
        assert dt.timezone == "Z"

    def test_parse_auto_detect(self) -> None:
        """Test auto-detecting format."""
        # Date
        result = DateTimeLiteral.parse("@2019-01-15")
        assert isinstance(result, FHIRDate)

        # Time
        result = DateTimeLiteral.parse("@T12:30")
        assert isinstance(result, FHIRTime)

        # Datetime
        result = DateTimeLiteral.parse("@2019-01-15T12:30")
        assert isinstance(result, FHIRDateTime)

    def test_parse_invalid_format(self) -> None:
        """Test parsing invalid format raises error."""
        with pytest.raises(ValueError):
            DateTimeLiteral.parse("invalid")


class TestDateTimeDuration:
    """Tests for DateTimeDuration parsing."""

    def test_parse_years(self) -> None:
        """Test parsing years duration."""
        d = DateTimeDuration.parse("5 years")
        assert d.years == 5

    def test_parse_singular_unit(self) -> None:
        """Test parsing singular unit."""
        d = DateTimeDuration.parse("1 year")
        assert d.years == 1

    def test_parse_negative(self) -> None:
        """Test parsing negative duration."""
        d = DateTimeDuration.parse("-3 days")
        assert d.days == -3

    def test_factory_methods(self) -> None:
        """Test factory methods."""
        assert DateTimeDuration.years(5).years == 5
        assert DateTimeDuration.months(3).months == 3
        assert DateTimeDuration.weeks(2).weeks == 2
        assert DateTimeDuration.days(10).days == 10
        assert DateTimeDuration.hours(24).hours == 24
        assert DateTimeDuration.minutes(60).minutes == 60
        assert DateTimeDuration.seconds(30).seconds == 30
        assert DateTimeDuration.milliseconds(500).milliseconds == 500


class TestDateTimeArithmetic:
    """Tests for DateTimeArithmetic operations."""

    def test_add_days_to_date(self) -> None:
        """Test adding days to date."""
        d = FHIRDate(value=date(2019, 1, 15), precision=DatePrecision.DAY)
        duration = FHIRDuration(days=5)
        result = DateTimeArithmetic.add(d, duration)
        assert result.value == date(2019, 1, 20)
        assert result.precision == DatePrecision.DAY

    def test_add_months_to_date(self) -> None:
        """Test adding months to date."""
        d = FHIRDate(value=date(2019, 1, 15), precision=DatePrecision.DAY)
        duration = FHIRDuration(months=2)
        result = DateTimeArithmetic.add(d, duration)
        assert result.value == date(2019, 3, 15)

    def test_add_years_to_date(self) -> None:
        """Test adding years to date."""
        d = FHIRDate(value=date(2019, 1, 15), precision=DatePrecision.DAY)
        duration = FHIRDuration(years=1)
        result = DateTimeArithmetic.add(d, duration)
        assert result.value == date(2020, 1, 15)

    def test_subtract_days_from_date(self) -> None:
        """Test subtracting days from date."""
        d = FHIRDate(value=date(2019, 1, 15), precision=DatePrecision.DAY)
        duration = FHIRDuration(days=5)
        result = DateTimeArithmetic.subtract(d, duration)
        assert result.value == date(2019, 1, 10)

    def test_add_hours_to_datetime(self) -> None:
        """Test adding hours to datetime."""
        dt = FHIRDateTime(value=datetime(2019, 1, 15, 12, 0), precision=DatePrecision.MINUTE)
        duration = FHIRDuration(hours=3)
        result = DateTimeArithmetic.add(dt, duration)
        assert result.value == datetime(2019, 1, 15, 15, 0)

    def test_date_difference(self) -> None:
        """Test calculating difference between dates."""
        d1 = FHIRDate(value=date(2019, 1, 20), precision=DatePrecision.DAY)
        d2 = FHIRDate(value=date(2019, 1, 15), precision=DatePrecision.DAY)
        result = DateTimeArithmetic.difference(d1, d2)
        assert result.days == 5

    def test_datetime_difference(self) -> None:
        """Test calculating difference between datetimes."""
        dt1 = FHIRDateTime(value=datetime(2019, 1, 15, 15, 30), precision=DatePrecision.MINUTE)
        dt2 = FHIRDateTime(value=datetime(2019, 1, 15, 12, 0), precision=DatePrecision.MINUTE)
        result = DateTimeArithmetic.difference(dt1, dt2)
        assert result.hours == 3
        assert result.minutes == 30


class TestDateTimeFunctions:
    """Tests for DateTimeFunctions."""

    def test_year_extraction(self) -> None:
        """Test extracting year."""
        dt = FHIRDateTime(value=datetime(2019, 6, 15, 12, 30), precision=DatePrecision.MINUTE)
        assert DateTimeFunctions.year(dt) == 2019

        d = FHIRDate(value=date(2019, 6, 15), precision=DatePrecision.DAY)
        assert DateTimeFunctions.year(d) == 2019

    def test_month_extraction(self) -> None:
        """Test extracting month."""
        dt = FHIRDateTime(value=datetime(2019, 6, 15, 12, 30), precision=DatePrecision.MINUTE)
        assert DateTimeFunctions.month(dt) == 6

    def test_day_extraction(self) -> None:
        """Test extracting day."""
        dt = FHIRDateTime(value=datetime(2019, 6, 15, 12, 30), precision=DatePrecision.MINUTE)
        assert DateTimeFunctions.day(dt) == 15

    def test_hour_extraction(self) -> None:
        """Test extracting hour."""
        dt = FHIRDateTime(value=datetime(2019, 6, 15, 12, 30), precision=DatePrecision.MINUTE)
        assert DateTimeFunctions.hour(dt) == 12

        t = FHIRTime(value=dt_time(12, 30, 45), precision=TimePrecision.SECOND)
        assert DateTimeFunctions.hour(t) == 12

    def test_minute_extraction(self) -> None:
        """Test extracting minute."""
        dt = FHIRDateTime(value=datetime(2019, 6, 15, 12, 30), precision=DatePrecision.MINUTE)
        assert DateTimeFunctions.minute(dt) == 30

    def test_second_extraction(self) -> None:
        """Test extracting second."""
        dt = FHIRDateTime(value=datetime(2019, 6, 15, 12, 30, 45), precision=DatePrecision.SECOND)
        assert DateTimeFunctions.second(dt) == 45

    def test_extraction_with_none(self) -> None:
        """Test extraction functions with None input."""
        assert DateTimeFunctions.year(None) is None
        assert DateTimeFunctions.month(None) is None
        assert DateTimeFunctions.day(None) is None
        assert DateTimeFunctions.hour(None) is None
        assert DateTimeFunctions.minute(None) is None
        assert DateTimeFunctions.second(None) is None

    def test_date_component(self) -> None:
        """Test extracting date component from datetime."""
        dt = FHIRDateTime(value=datetime(2019, 6, 15, 12, 30, 45), precision=DatePrecision.SECOND)
        result = DateTimeFunctions.dateComponent(dt)
        assert isinstance(result, FHIRDate)
        assert result.value == date(2019, 6, 15)

    def test_time_component(self) -> None:
        """Test extracting time component from datetime."""
        dt = FHIRDateTime(value=datetime(2019, 6, 15, 12, 30, 45), precision=DatePrecision.SECOND)
        result = DateTimeFunctions.timeComponent(dt)
        assert isinstance(result, FHIRTime)
        assert result.value.hour == 12
        assert result.value.minute == 30
        assert result.value.second == 45

    def test_now(self) -> None:
        """Test now() returns current datetime."""
        with mock.patch('fhir4ds.fhirpath.duckdb.functions.datetime.datetime') as mock_dt:
            mock_dt.now.return_value = datetime(2019, 6, 15, 12, 30, 45)
            result = DateTimeFunctions.now()
            assert result.value == datetime(2019, 6, 15, 12, 30, 45)
            assert result.precision == DatePrecision.MILLISECOND

    def test_today(self) -> None:
        """Test today() returns current date."""
        with mock.patch('fhir4ds.fhirpath.duckdb.functions.datetime.date') as mock_date:
            mock_date.today.return_value = date(2019, 6, 15)
            result = DateTimeFunctions.today()
            assert result.value == date(2019, 6, 15)
            assert result.precision == DatePrecision.DAY

    def test_time_of_day(self) -> None:
        """Test timeOfDay() returns current time."""
        with mock.patch('fhir4ds.fhirpath.duckdb.functions.datetime.datetime') as mock_dt:
            mock_dt.now.return_value = datetime(2019, 6, 15, 12, 30, 45, 123000)
            result = DateTimeFunctions.timeOfDay()
            assert result.value.hour == 12
            assert result.value.minute == 30
            assert result.value.second == 45


class TestDateTimeComparisons:
    """Tests for DateTimeComparisons."""

    def test_less_than_dates(self) -> None:
        """Test less than comparison for dates."""
        d1 = FHIRDate(value=date(2019, 1, 15), precision=DatePrecision.DAY)
        d2 = FHIRDate(value=date(2019, 1, 20), precision=DatePrecision.DAY)
        assert DateTimeComparisons.less_than(d1, d2) is True
        assert DateTimeComparisons.less_than(d2, d1) is False
        assert DateTimeComparisons.less_than(d1, d1) is False

    def test_less_than_datetimes(self) -> None:
        """Test less than comparison for datetimes."""
        dt1 = FHIRDateTime(value=datetime(2019, 1, 15, 12, 0), precision=DatePrecision.MINUTE)
        dt2 = FHIRDateTime(value=datetime(2019, 1, 15, 15, 0), precision=DatePrecision.MINUTE)
        assert DateTimeComparisons.less_than(dt1, dt2) is True

    def test_less_than_times(self) -> None:
        """Test less than comparison for times."""
        t1 = FHIRTime(value=dt_time(10, 0), precision=TimePrecision.MINUTE)
        t2 = FHIRTime(value=dt_time(15, 0), precision=TimePrecision.MINUTE)
        assert DateTimeComparisons.less_than(t1, t2) is True

    def test_less_or_equal(self) -> None:
        """Test less than or equal comparison."""
        d1 = FHIRDate(value=date(2019, 1, 15), precision=DatePrecision.DAY)
        d2 = FHIRDate(value=date(2019, 1, 20), precision=DatePrecision.DAY)
        d3 = FHIRDate(value=date(2019, 1, 15), precision=DatePrecision.DAY)

        assert DateTimeComparisons.less_or_equal(d1, d2) is True
        assert DateTimeComparisons.less_or_equal(d1, d3) is True
        assert DateTimeComparisons.less_or_equal(d2, d1) is False

    def test_greater_than(self) -> None:
        """Test greater than comparison."""
        d1 = FHIRDate(value=date(2019, 1, 20), precision=DatePrecision.DAY)
        d2 = FHIRDate(value=date(2019, 1, 15), precision=DatePrecision.DAY)
        assert DateTimeComparisons.greater_than(d1, d2) is True
        assert DateTimeComparisons.greater_than(d2, d1) is False

    def test_greater_or_equal(self) -> None:
        """Test greater than or equal comparison."""
        d1 = FHIRDate(value=date(2019, 1, 20), precision=DatePrecision.DAY)
        d2 = FHIRDate(value=date(2019, 1, 15), precision=DatePrecision.DAY)
        d3 = FHIRDate(value=date(2019, 1, 20), precision=DatePrecision.DAY)

        assert DateTimeComparisons.greater_or_equal(d1, d2) is True
        assert DateTimeComparisons.greater_or_equal(d1, d3) is True
        assert DateTimeComparisons.greater_or_equal(d2, d1) is False

    def test_equals_with_precision(self) -> None:
        """Test equality with precision awareness."""
        d1 = FHIRDate(value=date(2019, 1, 1), precision=DatePrecision.YEAR)
        d2 = FHIRDate(value=date(2019, 6, 15), precision=DatePrecision.DAY)
        d3 = FHIRDate(value=date(2019, 1, 1), precision=DatePrecision.YEAR)

        # Same year but different precision = not equal
        assert DateTimeComparisons.equals(d1, d2) is False
        # Same year and same precision = equal
        assert DateTimeComparisons.equals(d1, d3) is True

    def test_not_equals(self) -> None:
        """Test not equals comparison."""
        d1 = FHIRDate(value=date(2019, 1, 15), precision=DatePrecision.DAY)
        d2 = FHIRDate(value=date(2019, 1, 20), precision=DatePrecision.DAY)
        assert DateTimeComparisons.not_equals(d1, d2) is True

    def test_comparisons_with_none(self) -> None:
        """Test comparisons with None input."""
        d = FHIRDate(value=date(2019, 1, 15), precision=DatePrecision.DAY)

        assert DateTimeComparisons.less_than(None, d) is None
        assert DateTimeComparisons.less_than(d, None) is None
        assert DateTimeComparisons.greater_than(None, d) is None
        assert DateTimeComparisons.equals(None, d) is None


class TestPrecisionSemantics:
    """Tests for FHIRPath precision semantics."""

    def test_different_precision_not_equal(self) -> None:
        """Test that @2019 != @2019-01-01 per FHIRPath semantics."""
        d1 = FHIRDate(value=date(2019, 1, 1), precision=DatePrecision.YEAR)
        d2 = FHIRDate(value=date(2019, 1, 1), precision=DatePrecision.DAY)
        assert d1 != d2

    def test_comparison_at_lower_precision(self) -> None:
        """Test comparison happens at the lower precision level."""
        dt1 = FHIRDateTime(value=datetime(2019, 1, 15, 12, 0), precision=DatePrecision.DAY)
        dt2 = FHIRDateTime(value=datetime(2019, 1, 15, 15, 30), precision=DatePrecision.MINUTE)

        # Both on same day, so at DAY precision they should be equal
        assert not (dt1 < dt2)
        assert not (dt1 > dt2)

    def test_time_comparison_at_hour_precision(self) -> None:
        """Test time comparison at hour precision."""
        t1 = FHIRTime(value=dt_time(12, 0, 0), precision=TimePrecision.HOUR)
        t2 = FHIRTime(value=dt_time(12, 30, 45), precision=TimePrecision.SECOND)

        # Same hour, at HOUR precision they're equal
        assert not (t1 < t2)
        assert not (t1 > t2)
        assert t1 <= t2
        assert t1 >= t2


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_parse_date_with_leading_zeros(self) -> None:
        """Test parsing dates with leading zeros."""
        d = DateTimeLiteral.parse_date("@2019-01-05")
        assert d.value.month == 1
        assert d.value.day == 5

    def test_month_overflow_in_addition(self) -> None:
        """Test adding months that overflow to next year."""
        d = FHIRDate(value=date(2019, 11, 15), precision=DatePrecision.DAY)
        duration = FHIRDuration(months=3)
        result = DateTimeArithmetic.add(d, duration)
        assert result.value.month == 2
        assert result.value.year == 2020

    def test_day_overflow_in_addition(self) -> None:
        """Test adding days that overflow to next month."""
        d = FHIRDate(value=date(2019, 1, 31), precision=DatePrecision.DAY)
        duration = FHIRDuration(days=5)
        result = DateTimeArithmetic.add(d, duration)
        assert result.value.month == 2
        assert result.value.day == 5

    def test_negative_duration_addition(self) -> None:
        """Test adding negative duration."""
        d = FHIRDate(value=date(2019, 1, 15), precision=DatePrecision.DAY)
        duration = FHIRDuration(days=-5)
        result = DateTimeArithmetic.add(d, duration)
        assert result.value == date(2019, 1, 10)

    def test_empty_duration_string(self) -> None:
        """Test empty duration is empty."""
        d = FHIRDuration()
        assert str(d) == "0 seconds"

    def test_year_only_date_comparison(self) -> None:
        """Test year-only dates compare correctly."""
        d1 = FHIRDate(value=date(2019, 1, 1), precision=DatePrecision.YEAR)
        d2 = FHIRDate(value=date(2020, 1, 1), precision=DatePrecision.YEAR)
        assert d1 < d2
