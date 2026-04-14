"""
Unit tests for new FHIRPath functions:
- lowBoundary()
- highBoundary()
- precision()
- sort()
- matchesFull()
- comparable()
"""

from __future__ import annotations

import pytest

from ...engine.nodes import FP_DateTime, FP_Time, FP_Date
from ...engine.invocations.datetime import lowBoundary, highBoundary, precision
from ...engine.invocations.collections import sort_fn, comparable
from ...engine.invocations.strings import matchesFull


class TestLowBoundary:
    """Tests for lowBoundary() function."""

    def test_low_boundary_year(self) -> None:
        """Test @2014.lowBoundary() -> @2014-01-01"""
        dt = FP_Date("2014")
        result = lowBoundary({}, [dt])
        assert len(result) == 1
        assert result[0] == "2014-01-01"

    def test_low_boundary_month(self) -> None:
        """Test @2014-01.lowBoundary() -> @2014-01-01"""
        dt = FP_Date("2014-01")
        result = lowBoundary({}, [dt])
        assert len(result) == 1
        assert result[0] == "2014-01-01"

    def test_low_boundary_day(self) -> None:
        """Test @2014-01-15.lowBoundary() -> @2014-01-15"""
        dt = FP_Date("2014-01-15")
        result = lowBoundary({}, [dt])
        assert len(result) == 1
        assert result[0] == "2014-01-15"

    def test_low_boundary_hour(self) -> None:
        """Test @2014-01-15T14.lowBoundary() -> full datetime with 00:00:00"""
        dt = FP_DateTime("2014-01-15T14")
        result = lowBoundary({}, [dt])
        assert len(result) == 1
        assert "T14:00:00" in str(result[0])

    def test_low_boundary_time_hour(self) -> None:
        """Test @T14.lowBoundary() -> @T14:00:00.000"""
        t = FP_Time("T14")
        result = lowBoundary({}, [t])
        assert len(result) == 1
        assert result[0] == "T14:00:00.000"

    def test_low_boundary_time_minute(self) -> None:
        """Test @T14:30.lowBoundary() -> @T14:30:00.000"""
        t = FP_Time("T14:30")
        result = lowBoundary({}, [t])
        assert len(result) == 1
        assert result[0] == "T14:30:00.000"

    def test_low_boundary_empty_collection(self) -> None:
        """Test lowBoundary on empty collection returns empty."""
        result = lowBoundary({}, [])
        assert result == []


class TestHighBoundary:
    """Tests for highBoundary() function."""

    def test_high_boundary_year(self) -> None:
        """Test @2014.highBoundary() -> @2014-12-31"""
        dt = FP_Date("2014")
        result = highBoundary({}, [dt])
        assert len(result) == 1
        assert result[0] == "2014-12-31"

    def test_high_boundary_month(self) -> None:
        """Test @2014-01.highBoundary() -> @2014-01-31"""
        dt = FP_Date("2014-01")
        result = highBoundary({}, [dt])
        assert len(result) == 1
        assert result[0] == "2014-01-31"

    def test_high_boundary_february_non_leap(self) -> None:
        """Test @2015-02.highBoundary() -> @2015-02-28"""
        dt = FP_Date("2015-02")
        result = highBoundary({}, [dt])
        assert len(result) == 1
        assert result[0] == "2015-02-28"

    def test_high_boundary_february_leap(self) -> None:
        """Test @2016-02.highBoundary() -> @2016-02-29"""
        dt = FP_Date("2016-02")
        result = highBoundary({}, [dt])
        assert len(result) == 1
        assert result[0] == "2016-02-29"

    def test_high_boundary_hour(self) -> None:
        """Test @2014-01-15T14.highBoundary() -> full datetime with 59:59:59.999"""
        dt = FP_DateTime("2014-01-15T14")
        result = highBoundary({}, [dt])
        assert len(result) == 1
        assert "T14:59:59.999" in str(result[0])

    def test_high_boundary_time_hour(self) -> None:
        """Test @T14.highBoundary() -> @T14:59:59.999"""
        t = FP_Time("T14")
        result = highBoundary({}, [t])
        assert len(result) == 1
        assert result[0] == "T14:59:59.999"

    def test_high_boundary_time_minute(self) -> None:
        """Test @T14:30.highBoundary() -> @T14:30:59.999"""
        t = FP_Time("T14:30")
        result = highBoundary({}, [t])
        assert len(result) == 1
        assert result[0] == "T14:30:59.999"

    def test_high_boundary_empty_collection(self) -> None:
        """Test highBoundary on empty collection returns empty."""
        result = highBoundary({}, [])
        assert result == []


class TestPrecision:
    """Tests for precision() function.

    Per FHIRPath spec, precision returns the count of digits in the representation.
    """

    def test_precision_year(self) -> None:
        """Test @2014.precision() -> 4 (4 digits in year)"""
        dt = FP_Date("2014")
        result = precision({}, [dt])
        assert len(result) == 1
        assert result[0] == 4

    def test_precision_month(self) -> None:
        """Test @2014-01.precision() -> 6 (YYYYMM = 6 digits)"""
        dt = FP_Date("2014-01")
        result = precision({}, [dt])
        assert len(result) == 1
        assert result[0] == 6

    def test_precision_day(self) -> None:
        """Test @2014-01-01.precision() -> 8 (YYYYMMDD = 8 digits)"""
        dt = FP_Date("2014-01-01")
        result = precision({}, [dt])
        assert len(result) == 1
        assert result[0] == 8

    def test_precision_hour(self) -> None:
        """Test @2014-01-01T14.precision() -> 10 (YYYYMMDDHH = 10 digits)"""
        dt = FP_DateTime("2014-01-01T14")
        result = precision({}, [dt])
        assert len(result) == 1
        assert result[0] == 10

    def test_precision_minute(self) -> None:
        """Test @2014-01-01T14:30.precision() -> 12 (YYYYMMDDHHMM = 12 digits)"""
        dt = FP_DateTime("2014-01-01T14:30")
        result = precision({}, [dt])
        assert len(result) == 1
        assert result[0] == 12

    def test_precision_second(self) -> None:
        """Test @2014-01-01T14:30:00.precision() -> 14 (YYYYMMDDHHMMSS = 14 digits)"""
        dt = FP_DateTime("2014-01-01T14:30:00")
        result = precision({}, [dt])
        assert len(result) == 1
        assert result[0] == 14

    def test_precision_time_hour(self) -> None:
        """Test @T14.precision() -> 2 (HH = 2 digits)"""
        t = FP_Time("T14")
        result = precision({}, [t])
        assert len(result) == 1
        assert result[0] == 2

    def test_precision_time_minute(self) -> None:
        """Test @T14:30.precision() -> 4 (HHMM = 4 digits)"""
        t = FP_Time("T14:30")
        result = precision({}, [t])
        assert len(result) == 1
        assert result[0] == 4

    def test_precision_empty_collection(self) -> None:
        """Test precision on empty collection returns empty."""
        result = precision({}, [])
        assert result == []


class TestSort:
    """Tests for sort() function."""

    def test_sort_numbers(self) -> None:
        """Test (3 | 1 | 2).sort() -> [1, 2, 3]"""
        result = sort_fn({}, [3, 1, 2])
        assert result == [1, 2, 3]

    def test_sort_strings(self) -> None:
        """Test ('c' | 'b' | 'a').sort() -> ['a', 'b', 'c']"""
        result = sort_fn({}, ["c", "b", "a"])
        assert result == ["a", "b", "c"]

    def test_sort_empty_collection(self) -> None:
        """Test empty collection sort returns empty."""
        result = sort_fn({}, [])
        assert result == []

    def test_sort_single_element(self) -> None:
        """Test single element sort returns same element."""
        result = sort_fn({}, [5])
        assert result == [5]

    def test_sort_already_sorted(self) -> None:
        """Test already sorted collection remains sorted."""
        result = sort_fn({}, [1, 2, 3])
        assert result == [1, 2, 3]

    def test_sort_reverse(self) -> None:
        """Test reverse sorted collection gets sorted."""
        result = sort_fn({}, [3, 2, 1])
        assert result == [1, 2, 3]

    def test_sort_with_duplicates(self) -> None:
        """Test sort with duplicates preserves duplicates."""
        result = sort_fn({}, [3, 1, 2, 1])
        assert result == [1, 1, 2, 3]


class TestMatchesFull:
    """Tests for matchesFull() function."""

    def test_matches_full_true(self) -> None:
        """Test full match returns true."""
        result = matchesFull({}, ["hello"], "hel.*")
        assert result is True

    def test_matches_full_false_partial(self) -> None:
        """Test partial match returns false."""
        result = matchesFull({}, ["hello"], "hel")
        assert result is False

    def test_matches_full_digits(self) -> None:
        """Test full match with digit pattern."""
        result = matchesFull({}, ["123-456"], r"\d{3}-\d{3}")
        assert result is True

    def test_matches_full_empty_string(self) -> None:
        """Test full match on empty string."""
        result = matchesFull({}, [""], "")
        assert result is True

    def test_matches_full_empty_collection(self) -> None:
        """Test matchesFull on empty collection returns empty."""
        result = matchesFull({}, [], r"\d+")
        assert result == []

    def test_matches_full_invalid_regex_raises(self) -> None:
        """Test matchesFull with invalid regex raises error."""
        with pytest.raises(Exception):
            matchesFull({}, ["test"], r"[invalid")


class TestComparable:
    """Tests for comparable() function."""

    def test_comparable_numbers_true(self) -> None:
        """Test 1.comparable(2) -> true"""
        result = comparable({}, [1], [2])
        assert result == [True]

    def test_comparable_number_string_false(self) -> None:
        """Test 1.comparable('a') -> false"""
        result = comparable({}, [1], ["a"])
        assert result == [False]

    def test_comparable_dates_true(self) -> None:
        """Test @2014.comparable(@2015) -> true"""
        dt1 = FP_Date("2014")
        dt2 = FP_Date("2015")
        result = comparable({}, [dt1], [dt2])
        assert result == [True]

    def test_comparable_times_true(self) -> None:
        """Test @T14.comparable(@T15) -> true"""
        t1 = FP_Time("T14")
        t2 = FP_Time("T15")
        result = comparable({}, [t1], [t2])
        assert result == [True]

    def test_comparable_datetime_time_false(self) -> None:
        """Test DateTime.comparable(Time) -> false"""
        dt = FP_DateTime("2014-01-01T14")
        t = FP_Time("T14")
        result = comparable({}, [dt], [t])
        assert result == [False]

    def test_comparable_strings_true(self) -> None:
        """Test 'a'.comparable('b') -> true"""
        result = comparable({}, ["a"], ["b"])
        assert result == [True]

    def test_comparable_booleans_true(self) -> None:
        """Test true.comparable(false) -> true"""
        result = comparable({}, [True], [False])
        assert result == [True]

    def test_comparable_empty_left(self) -> None:
        """Test empty collection on left returns empty."""
        result = comparable({}, [], [1])
        assert result == []

    def test_comparable_empty_right(self) -> None:
        """Test empty collection on right returns empty."""
        result = comparable({}, [1], [])
        assert result == []


class TestIntegration:
    """Integration tests verifying functions work with FHIRPath evaluation."""

    def test_low_boundary_high_boundary_range(self) -> None:
        """Test that lowBoundary and highBoundary create a valid range."""
        dt = FP_Date("2014-01")
        low = lowBoundary({}, [dt])[0]
        high = highBoundary({}, [dt])[0]
        assert low == "2014-01-01"
        assert high == "2014-01-31"

    def test_precision_matches_boundary_behavior(self) -> None:
        """Test that precision reflects the same precision used in boundaries."""
        dt_year = FP_Date("2014")
        assert precision({}, [dt_year])[0] == 4  # 4 digits in year
        assert lowBoundary({}, [dt_year])[0] == "2014-01-01"
        assert highBoundary({}, [dt_year])[0] == "2014-12-31"

        dt_month = FP_Date("2014-06")
        assert precision({}, [dt_month])[0] == 6  # 6 digits in YYYYMM
        assert lowBoundary({}, [dt_month])[0] == "2014-06-01"
        assert highBoundary({}, [dt_month])[0] == "2014-06-30"
