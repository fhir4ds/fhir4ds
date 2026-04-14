"""
Unit tests for CQL DateTime Difference UDFs.

Tests for date/time difference functions:
- yearsBetween, monthsBetween, weeksBetween, daysBetween
- hoursBetween, minutesBetween, secondsBetween, millisecondsBetween
"""

import pytest
import duckdb

from ..udf.datetime import (
    yearsBetween,
    monthsBetween,
    weeksBetween,
    daysBetween,
    hoursBetween,
    minutesBetween,
    secondsBetween,
    millisecondsBetween,
    registerDatetimeUdfs,
)


# ========================================
# yearsBetween tests
# ========================================

def test_years_between_exact_years():
    """Test years between for exact year boundaries."""
    result = yearsBetween("2020-01-01", "2025-01-01")
    assert result == 5


def test_years_between_partial_year():
    """Test years between when not complete year."""
    result = yearsBetween("2020-06-15", "2025-01-01")
    assert result == 4  # 4 complete years


def test_years_between_same_date():
    """Test years between same date."""
    result = yearsBetween("2020-01-01", "2020-01-01")
    assert result == 0


def test_years_between_negative():
    """Test years between when end is before start."""
    result = yearsBetween("2025-01-01", "2020-01-01")
    assert result == -5


def test_years_between_null_start():
    """Test years between with null start."""
    assert yearsBetween(None, "2020-01-01") is None


def test_years_between_null_end():
    """Test years between with null end."""
    assert yearsBetween("2020-01-01", None) is None


def test_years_between_both_null():
    """Test years between with both null."""
    assert yearsBetween(None, None) is None


def test_years_between_invalid_format():
    """Test years between with invalid date format."""
    assert yearsBetween("not-a-date", "2020-01-01") is None


# ========================================
# monthsBetween tests
# ========================================

def test_months_between_exact_months():
    """Test months between for exact month boundaries."""
    result = monthsBetween("2020-01-01", "2020-06-01")
    assert result == 5


def test_months_between_across_years():
    """Test months between across year boundary."""
    result = monthsBetween("2020-06-01", "2022-03-01")
    assert result == 21  # 12 + 9 months


def test_months_between_partial_month():
    """Test months between when day of month matters."""
    result = monthsBetween("2020-01-15", "2020-02-10")
    assert result == 0  # Not a complete month yet


def test_months_between_same_date():
    """Test months between same date."""
    result = monthsBetween("2020-01-01", "2020-01-01")
    assert result == 0


def test_months_between_null_start():
    """Test months between with null start."""
    assert monthsBetween(None, "2020-01-01") is None


def test_months_between_null_end():
    """Test months between with null end."""
    assert monthsBetween("2020-01-01", None) is None


# ========================================
# weeksBetween tests
# ========================================

def test_weeks_between_exact_weeks():
    """Test weeks between for exact week boundaries."""
    result = weeksBetween("2020-01-01", "2020-01-22")
    assert result == 3


def test_weeks_between_partial_week():
    """Test weeks between with partial week."""
    result = weeksBetween("2020-01-01", "2020-01-10")
    assert result == 1  # 9 days = 1 week


def test_weeks_between_same_date():
    """Test weeks between same date."""
    result = weeksBetween("2020-01-01", "2020-01-01")
    assert result == 0


def test_weeks_between_null_start():
    """Test weeks between with null start."""
    assert weeksBetween(None, "2020-01-01") is None


def test_weeks_between_null_end():
    """Test weeks between with null end."""
    assert weeksBetween("2020-01-01", None) is None


# ========================================
# daysBetween tests
# ========================================

def test_days_between_positive():
    """Test days between positive difference."""
    result = daysBetween("2020-01-01", "2020-01-11")
    assert result == 10


def test_days_between_negative():
    """Test days between negative difference."""
    result = daysBetween("2020-01-11", "2020-01-01")
    assert result == -10


def test_days_between_same_date():
    """Test days between same date."""
    result = daysBetween("2020-01-01", "2020-01-01")
    assert result == 0


def test_days_between_null_start():
    """Test days between with null start."""
    assert daysBetween(None, "2020-01-01") is None


def test_days_between_null_end():
    """Test days between with null end."""
    assert daysBetween("2020-01-01", None) is None


def test_days_between_invalid_format():
    """Test days between with invalid date format."""
    assert daysBetween("invalid", "2020-01-01") is None


# ========================================
# hoursBetween tests
# ========================================

def test_hours_between_positive():
    """Test hours between positive difference."""
    result = hoursBetween("2020-01-01T00:00:00Z", "2020-01-01T10:00:00Z")
    assert result == 10


def test_hours_between_24_hours():
    """Test hours between for one day."""
    result = hoursBetween("2020-01-01T00:00:00Z", "2020-01-02T00:00:00Z")
    assert result == 24


def test_hours_between_partial():
    """Test hours between with partial hours."""
    result = hoursBetween("2020-01-01T00:00:00Z", "2020-01-01T05:30:00Z")
    assert result == 5  # Truncated to whole hours


def test_hours_between_null_start():
    """Test hours between with null start."""
    assert hoursBetween(None, "2020-01-01T00:00:00Z") is None


def test_hours_between_null_end():
    """Test hours between with null end."""
    assert hoursBetween("2020-01-01T00:00:00Z", None) is None


def test_hours_between_invalid_format():
    """Test hours between with invalid datetime format."""
    assert hoursBetween("not-datetime", "2020-01-01T00:00:00Z") is None


# ========================================
# minutesBetween tests
# ========================================

def test_minutes_between_positive():
    """Test minutes between positive difference."""
    result = minutesBetween("2020-01-01T00:00:00Z", "2020-01-01T01:30:00Z")
    assert result == 90


def test_minutes_between_one_hour():
    """Test minutes between for one hour."""
    result = minutesBetween("2020-01-01T00:00:00Z", "2020-01-01T01:00:00Z")
    assert result == 60


def test_minutes_between_partial():
    """Test minutes between with partial minutes."""
    result = minutesBetween("2020-01-01T00:00:00Z", "2020-01-01T00:05:30Z")
    assert result == 5  # Truncated to whole minutes


def test_minutes_between_null_start():
    """Test minutes between with null start."""
    assert minutesBetween(None, "2020-01-01T00:00:00Z") is None


def test_minutes_between_null_end():
    """Test minutes between with null end."""
    assert minutesBetween("2020-01-01T00:00:00Z", None) is None


# ========================================
# secondsBetween tests
# ========================================

def test_seconds_between_positive():
    """Test seconds between positive difference."""
    result = secondsBetween("2020-01-01T00:00:00Z", "2020-01-01T00:01:30Z")
    assert result == 90


def test_seconds_between_one_minute():
    """Test seconds between for one minute."""
    result = secondsBetween("2020-01-01T00:00:00Z", "2020-01-01T00:01:00Z")
    assert result == 60


def test_seconds_between_null_start():
    """Test seconds between with null start."""
    assert secondsBetween(None, "2020-01-01T00:00:00Z") is None


def test_seconds_between_null_end():
    """Test seconds between with null end."""
    assert secondsBetween("2020-01-01T00:00:00Z", None) is None


# ========================================
# millisecondsBetween tests
# ========================================

def test_milliseconds_between_one_second():
    """Test milliseconds between for one second."""
    result = millisecondsBetween("2020-01-01T00:00:00Z", "2020-01-01T00:00:01Z")
    assert result == 1000


def test_milliseconds_between_partial():
    """Test milliseconds between partial second."""
    result = millisecondsBetween("2020-01-01T00:00:00Z", "2020-01-01T00:00:00.500Z")
    assert result == 500


def test_milliseconds_between_null_start():
    """Test milliseconds between with null start."""
    assert millisecondsBetween(None, "2020-01-01T00:00:00Z") is None


def test_milliseconds_between_null_end():
    """Test milliseconds between with null end."""
    assert millisecondsBetween("2020-01-01T00:00:00Z", None) is None


# ========================================
# DuckDB Registration tests
# ========================================

def test_registration():
    """Test that UDFs can be registered with DuckDB."""
    con = duckdb.connect()
    # Use full register to get both macros and UDFs
    from ..import register
    register(con, include_fhirpath=False)

    # Test years between (macro - TitleCase)
    result = con.execute("SELECT YearsBetween(?, ?)", ["2020-01-01", "2025-01-01"]).fetchone()
    assert result[0] == 5

    # Test months between (macro - TitleCase)
    result = con.execute("SELECT MonthsBetween(?, ?)", ["2020-01-01", "2020-06-01"]).fetchone()
    assert result[0] == 5

    # Test days between (macro - TitleCase)
    result = con.execute("SELECT DaysBetween(?, ?)", ["2020-01-01", "2020-01-11"]).fetchone()
    assert result[0] == 10

    con.close()


def test_registration_null_handling():
    """Test null handling through DuckDB."""
    con = duckdb.connect()
    # Use full register to get both macros and UDFs
    from ..import register
    register(con, include_fhirpath=False)

    result = con.execute("SELECT YearsBetween(NULL, '2020-01-01')").fetchone()
    assert result[0] is None

    result = con.execute("SELECT DaysBetween(NULL, NULL)").fetchone()
    assert result[0] is None

    con.close()


def test_all_functions_registered():
    """Test that all datetime functions are properly registered."""
    con = duckdb.connect()
    # Use full register to get both macros and UDFs
    from ..import register
    register(con, include_fhirpath=False)

    start_date = "2020-01-01"
    end_date = "2025-06-15"
    start_datetime = "2020-01-01T00:00:00Z"
    end_datetime = "2020-01-02T12:30:45Z"

    # Macro functions (TitleCase)
    macro_functions = [
        ("YearsBetween", [start_date, end_date]),
        ("MonthsBetween", [start_date, end_date]),
        ("DaysBetween", [start_date, end_date]),
        ("HoursBetween", [start_datetime, end_datetime]),
        ("MinutesBetween", [start_datetime, end_datetime]),
        ("SecondsBetween", [start_datetime, end_datetime]),
    ]

    # UDF functions (camelCase - only these without macro equivalents)
    udf_functions = [
        ("weeksBetween", [start_date, end_date]),
        ("millisecondsBetween", [start_datetime, end_datetime]),
    ]

    for func_name, params in macro_functions:
        result = con.execute(f"SELECT {func_name}({', '.join(['?'] * len(params))})", params).fetchone()
        # Should not raise an error
        assert result is not None

    for func_name, params in udf_functions:
        result = con.execute(f"SELECT {func_name}({', '.join(['?'] * len(params))})", params).fetchone()
        # Should not raise an error
        assert result is not None

    con.close()


# ========================================
# Edge case tests
# ========================================

def test_datetime_with_timezone():
    """Test datetime parsing with timezone."""
    result = hoursBetween("2020-01-01T00:00:00+00:00", "2020-01-01T05:00:00+00:00")
    assert result == 5


def test_datetime_with_z_suffix():
    """Test datetime parsing with Z suffix."""
    result = hoursBetween("2020-01-01T00:00:00Z", "2020-01-01T05:00:00Z")
    assert result == 5


def test_date_truncation():
    """Test that dates are properly truncated to 10 chars."""
    # Should still work with datetime strings
    result = daysBetween("2020-01-01T10:00:00Z", "2020-01-11T10:00:00Z")
    assert result == 10


def test_empty_string_inputs():
    """Test with empty string inputs."""
    assert yearsBetween("", "2020-01-01") is None
    assert yearsBetween("2020-01-01", "") is None
