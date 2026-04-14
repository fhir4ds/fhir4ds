"""
Unit tests for CQL Interval UDFs.

Tests for interval operations:
- intervalStart, intervalEnd, intervalWidth
- intervalContains, intervalProperlyContains
- intervalOverlaps, intervalBefore, intervalAfter
- intervalMeets
"""

import pytest
import duckdb

from ..udf.interval import (
    intervalStart,
    intervalEnd,
    intervalWidth,
    intervalContains,
    intervalProperlyContains,
    intervalOverlaps,
    intervalBefore,
    intervalAfter,
    intervalMeets,
    registerIntervalUdfs,
)


@pytest.fixture
def closed_interval():
    """A closed interval [2024-01-01, 2024-12-31]."""
    return '{"low": "2024-01-01", "high": "2024-12-31", "lowClosed": true, "highClosed": true}'


@pytest.fixture
def open_interval():
    """An open interval (2024-01-01, 2024-12-31)."""
    return '{"low": "2024-01-01", "high": "2024-12-31", "lowClosed": false, "highClosed": false}'


@pytest.fixture
def left_closed_interval():
    """A left-closed interval [2024-01-01, 2024-12-31)."""
    return '{"low": "2024-01-01", "high": "2024-12-31", "lowClosed": true, "highClosed": false}'


@pytest.fixture
def datetime_interval():
    """A datetime interval."""
    return '{"low": "2024-01-01T00:00:00Z", "high": "2024-01-01T23:59:59Z", "lowClosed": true, "highClosed": true}'


# ========================================
# intervalStart tests
# ========================================

def test_interval_start_closed(closed_interval):
    """Test getting start of closed interval."""
    result = intervalStart(closed_interval)
    assert result == "2024-01-01"


def test_interval_start_datetime(datetime_interval):
    """Test getting start of datetime interval."""
    result = intervalStart(datetime_interval)
    assert "2024-01-01" in result


def test_interval_start_null():
    """Test interval start with null input."""
    assert intervalStart(None) is None


def test_interval_start_empty_string():
    """Test interval start with empty string."""
    assert intervalStart("") is None


def test_interval_start_invalid_json():
    """Test interval start with invalid JSON."""
    assert intervalStart("not json") is None


# ========================================
# intervalEnd tests
# ========================================

def test_interval_end_closed(closed_interval):
    """Test getting end of closed interval."""
    result = intervalEnd(closed_interval)
    assert result == "2024-12-31"


def test_interval_end_datetime(datetime_interval):
    """Test getting end of datetime interval."""
    result = intervalEnd(datetime_interval)
    assert "2024-01-01" in result


def test_interval_end_null():
    """Test interval end with null input."""
    assert intervalEnd(None) is None


def test_interval_end_empty_string():
    """Test interval end with empty string."""
    assert intervalEnd("") is None


# ========================================
# intervalWidth tests
# ========================================

def test_interval_width_year(closed_interval):
    """Test width of year-long interval."""
    result = intervalWidth(closed_interval)
    assert result == 365  # 2024 is a leap year


def test_interval_width_month():
    """Test width of month-long interval."""
    interval = '{"low": "2024-01-01", "high": "2024-01-31", "lowClosed": true, "highClosed": true}'
    result = intervalWidth(interval)
    assert result == 30


def test_interval_width_single_day():
    """Test width of single day interval."""
    interval = '{"low": "2024-01-01", "high": "2024-01-01", "lowClosed": true, "highClosed": true}'
    result = intervalWidth(interval)
    assert result == 0


def test_interval_width_null():
    """Test interval width with null input."""
    assert intervalWidth(None) is None


def test_interval_width_missing_bounds():
    """Test interval width with missing bounds."""
    interval = '{"low": null, "high": "2024-01-31"}'
    assert intervalWidth(interval) is None


# ========================================
# intervalContains tests
# ========================================

def test_interval_contains_point_in_middle(closed_interval):
    """Test contains with point in middle of interval."""
    result = intervalContains(closed_interval, "2024-06-15")
    assert result is True


def test_interval_contains_start_point_closed(closed_interval):
    """Test contains with start point in closed interval.

    Closed interval (lowClosed=True) should include the start point.
    """
    result = intervalContains(closed_interval, "2024-01-01")
    # Closed bound is inclusive - start point should be contained
    assert result is True


def test_interval_contains_end_point_closed(closed_interval):
    """Test contains with end point in closed interval.

    Closed interval (highClosed=True) should include the end point.
    """
    result = intervalContains(closed_interval, "2024-12-31")
    # Closed bound is inclusive - end point should be contained
    assert result is True


def test_interval_contains_start_point_open(open_interval):
    """Test contains with start point in open interval.

    Open interval (lowClosed=False) should NOT include the start point.
    """
    result = intervalContains(open_interval, "2024-01-01")
    # Open bound is exclusive - start point should NOT be contained
    assert result is False


def test_interval_contains_end_point_open(open_interval):
    """Test contains with end point in open interval.

    Open interval (highClosed=False) should NOT include the end point.
    """
    result = intervalContains(open_interval, "2024-12-31")
    # Open bound is exclusive - end point should NOT be contained
    assert result is False


def test_interval_contains_before(closed_interval):
    """Test contains with point before interval."""
    result = intervalContains(closed_interval, "2023-12-31")
    assert result is False


def test_interval_contains_after(closed_interval):
    """Test contains with point after interval."""
    result = intervalContains(closed_interval, "2025-01-01")
    assert result is False


def test_interval_contains_null_interval():
    """Test contains with null interval — CQL 3VL: null input → null output."""
    result = intervalContains(None, "2024-06-15")
    assert result is None


def test_interval_contains_null_point(closed_interval):
    """Test contains with null point — CQL 3VL: null input → null output."""
    result = intervalContains(closed_interval, None)
    assert result is None


def test_interval_contains_both_null():
    """Test contains with both null — CQL 3VL: null input → null output."""
    result = intervalContains(None, None)
    assert result is None


# ========================================
# intervalProperlyContains tests
# ========================================

def test_properly_contains_middle(closed_interval):
    """Test properly contains with point in middle."""
    result = intervalProperlyContains(closed_interval, "2024-06-15")
    assert result is True


def test_properly_contains_start(closed_interval):
    """Test properly contains with start point (should be False)."""
    result = intervalProperlyContains(closed_interval, "2024-01-01")
    assert result is False


def test_properly_contains_end(closed_interval):
    """Test properly contains with end point (should be False)."""
    result = intervalProperlyContains(closed_interval, "2024-12-31")
    assert result is False


def test_properly_contains_null():
    """Test properly contains with null — CQL 3VL: null input → null output."""
    result = intervalProperlyContains(None, "2024-06-15")
    assert result is None


# ========================================
# intervalOverlaps tests
# ========================================

def test_overlaps_partial():
    """Test overlapping intervals."""
    interval1 = '{"low": "2024-01-01", "high": "2024-06-30", "lowClosed": true, "highClosed": true}'
    interval2 = '{"low": "2024-06-01", "high": "2024-12-31", "lowClosed": true, "highClosed": true}'
    result = intervalOverlaps(interval1, interval2)
    assert result is True


def test_overlaps_contained():
    """Test when one interval contains the other."""
    interval1 = '{"low": "2024-01-01", "high": "2024-12-31", "lowClosed": true, "highClosed": true}'
    interval2 = '{"low": "2024-03-01", "high": "2024-06-30", "lowClosed": true, "highClosed": true}'
    result = intervalOverlaps(interval1, interval2)
    assert result is True


def test_overlaps_not_overlapping():
    """Test non-overlapping intervals."""
    interval1 = '{"low": "2024-01-01", "high": "2024-03-31", "lowClosed": true, "highClosed": true}'
    interval2 = '{"low": "2024-04-01", "high": "2024-12-31", "lowClosed": true, "highClosed": true}'
    result = intervalOverlaps(interval1, interval2)
    assert result is False


def test_overlaps_identical(closed_interval):
    """Test identical intervals."""
    result = intervalOverlaps(closed_interval, closed_interval)
    assert result is True


def test_overlaps_null_first():
    """Test overlaps with null first interval — CQL 3VL: null input → null output."""
    interval2 = '{"low": "2024-01-01", "high": "2024-12-31"}'
    result = intervalOverlaps(None, interval2)
    assert result is None


def test_overlaps_null_second(closed_interval):
    """Test overlaps with null second interval — CQL 3VL: null input → null output."""
    result = intervalOverlaps(closed_interval, None)
    assert result is None


# ========================================
# intervalBefore tests
# ========================================

def test_before_true():
    """Test interval before another."""
    interval1 = '{"low": "2024-01-01", "high": "2024-03-31", "lowClosed": true, "highClosed": true}'
    interval2 = '{"low": "2024-04-01", "high": "2024-12-31", "lowClosed": true, "highClosed": true}'
    result = intervalBefore(interval1, interval2)
    assert result is True


def test_before_false_overlapping():
    """Test interval before with overlapping intervals."""
    interval1 = '{"low": "2024-01-01", "high": "2024-06-30", "lowClosed": true, "highClosed": true}'
    interval2 = '{"low": "2024-06-01", "high": "2024-12-31", "lowClosed": true, "highClosed": true}'
    result = intervalBefore(interval1, interval2)
    assert result is False


def test_before_false_after():
    """Test interval before when interval1 is after interval2."""
    interval1 = '{"low": "2024-06-01", "high": "2024-12-31", "lowClosed": true, "highClosed": true}'
    interval2 = '{"low": "2024-01-01", "high": "2024-03-31", "lowClosed": true, "highClosed": true}'
    result = intervalBefore(interval1, interval2)
    assert result is False


def test_before_null_first():
    """Test before with null first interval — CQL 3VL: null input → null output."""
    interval2 = '{"low": "2024-01-01", "high": "2024-12-31"}'
    result = intervalBefore(None, interval2)
    assert result is None


# ========================================
# intervalAfter tests
# ========================================

def test_after_true():
    """Test interval after another."""
    interval1 = '{"low": "2024-04-01", "high": "2024-12-31", "lowClosed": true, "highClosed": true}'
    interval2 = '{"low": "2024-01-01", "high": "2024-03-31", "lowClosed": true, "highClosed": true}'
    result = intervalAfter(interval1, interval2)
    assert result is True


def test_after_false_overlapping():
    """Test interval after with overlapping intervals."""
    interval1 = '{"low": "2024-06-01", "high": "2024-12-31", "lowClosed": true, "highClosed": true}'
    interval2 = '{"low": "2024-01-01", "high": "2024-06-30", "lowClosed": true, "highClosed": true}'
    result = intervalAfter(interval1, interval2)
    assert result is False


def test_after_false_before():
    """Test interval after when interval1 is before interval2."""
    interval1 = '{"low": "2024-01-01", "high": "2024-03-31", "lowClosed": true, "highClosed": true}'
    interval2 = '{"low": "2024-04-01", "high": "2024-12-31", "lowClosed": true, "highClosed": true}'
    result = intervalAfter(interval1, interval2)
    assert result is False


def test_after_null():
    """Test after with null interval — CQL 3VL: null input → null output."""
    result = intervalAfter(None, '{"low": "2024-01-01", "high": "2024-12-31"}')
    assert result is None


# ========================================
# intervalMeets tests
# ========================================

def test_meets_true():
    """Test intervals that meet (end of one = start of other)."""
    interval1 = '{"low": "2024-01-01", "high": "2024-03-31", "lowClosed": true, "highClosed": true}'
    interval2 = '{"low": "2024-03-31", "high": "2024-12-31", "lowClosed": true, "highClosed": true}'
    result = intervalMeets(interval1, interval2)
    assert result is True


def test_meets_false_gap():
    """Test intervals that don't meet (gap between)."""
    interval1 = '{"low": "2024-01-01", "high": "2024-03-30", "lowClosed": true, "highClosed": true}'
    interval2 = '{"low": "2024-04-01", "high": "2024-12-31", "lowClosed": true, "highClosed": true}'
    result = intervalMeets(interval1, interval2)
    assert result is False


def test_meets_false_overlapping():
    """Test intervals that overlap (don't meet)."""
    interval1 = '{"low": "2024-01-01", "high": "2024-06-30", "lowClosed": true, "highClosed": true}'
    interval2 = '{"low": "2024-06-01", "high": "2024-12-31", "lowClosed": true, "highClosed": true}'
    result = intervalMeets(interval1, interval2)
    assert result is False


def test_meets_null():
    """Test meets with null interval — CQL 3VL: null input → null output."""
    result = intervalMeets(None, '{"low": "2024-01-01", "high": "2024-12-31"}')
    assert result is None


# ========================================
# DuckDB Registration tests
# ========================================

def test_registration():
    """Test that UDFs can be registered with DuckDB."""
    con = duckdb.connect()
    registerIntervalUdfs(con)

    interval = '{"low": "2024-01-01", "high": "2024-12-31", "lowClosed": true, "highClosed": true}'

    # Test interval_start
    result = con.execute("SELECT intervalStart(?)", [interval]).fetchone()
    assert result[0] == "2024-01-01"

    # Test interval_end
    result = con.execute("SELECT intervalEnd(?)", [interval]).fetchone()
    assert result[0] == "2024-12-31"

    # Test interval_contains
    result = con.execute("SELECT intervalContains(?, ?)", [interval, "2024-06-15"]).fetchone()
    assert result[0] is True

    con.close()


def test_registration_all_functions():
    """Test that all interval functions are properly registered."""
    con = duckdb.connect()
    registerIntervalUdfs(con)

    interval1 = '{"low": "2024-01-01", "high": "2024-06-30", "lowClosed": true, "highClosed": true}'
    interval2 = '{"low": "2024-04-01", "high": "2024-12-31", "lowClosed": true, "highClosed": true}'
    point = "2024-03-15"

    functions = [
        ("intervalStart", [interval1]),
        ("intervalEnd", [interval1]),
        ("intervalWidth", [interval1]),
        ("intervalContains", [interval1, point]),
        ("intervalProperlyContains", [interval1, point]),
        ("intervalOverlaps", [interval1, interval2]),
        ("intervalBefore", [interval1, interval2]),
        ("intervalAfter", [interval1, interval2]),
        ("intervalMeets", [interval1, interval2]),
    ]

    for func_name, params in functions:
        result = con.execute(f"SELECT {func_name}({', '.join(['?'] * len(params))})", params).fetchone()
        # Should not raise an error
        assert result is not None

    con.close()


# ========================================
# Edge case tests
# ========================================

def test_interval_default_bounds():
    """Test interval with default bounds (should be closed).

    Default bounds are closed (inclusive), so endpoints should be contained.
    """
    interval = '{"low": "2024-01-01", "high": "2024-12-31"}'
    # Default is closed (inclusive) - endpoints should be contained
    result = intervalContains(interval, "2024-01-01")
    assert result is True  # Closed bound includes start
    result = intervalContains(interval, "2024-12-31")
    assert result is True  # Closed bound includes end


def test_interval_invalid_json():
    """Test interval functions with invalid JSON."""
    invalid = "not valid json"
    assert intervalStart(invalid) is None
    assert intervalEnd(invalid) is None
    assert intervalWidth(invalid) is None
    assert intervalContains(invalid, "2024-01-01") is None  # CQL 3VL: unparseable → null


def test_interval_missing_bounds():
    """Test interval with missing low/high."""
    interval = '{"lowClosed": true, "highClosed": true}'
    assert intervalStart(interval) is None
    assert intervalEnd(interval) is None
    assert intervalWidth(interval) is None
