"""
Unit tests for fhirpathpy DateTime timezone preservation.

Tests that DateTime operations preserve the original timezone information
as required by the FHIRPath specification.
"""

from __future__ import annotations

import pytest
import sys
from pathlib import Path

# Add src to path for imports

from ...engine.nodes import FP_DateTime, FP_Quantity


class TestDateTimeTimezonePreservation:
    """Tests for DateTime timezone preservation."""

    def test_timezone_stored_on_init(self) -> None:
        """Test that timezone is stored when DateTime is created."""
        dt = FP_DateTime("1973-12-25T00:00:00.000+10:00")
        assert dt._timezone == "+10:00"

    def test_timezone_z_stored(self) -> None:
        """Test that Z timezone is stored correctly."""
        dt = FP_DateTime("1973-12-25T00:00:00.000Z")
        assert dt._timezone == "Z"

    def test_timezone_negative_offset_stored(self) -> None:
        """Test that negative timezone offset is stored correctly."""
        dt = FP_DateTime("1973-12-25T00:00:00.000-05:00")
        assert dt._timezone == "-05:00"

    def test_no_timezone_stored_as_none(self) -> None:
        """Test that DateTime without timezone has None stored."""
        dt = FP_DateTime("1973-12-25T00:00:00.000")
        assert dt._timezone is None

    def test_plus_days_preserves_timezone_positive(self) -> None:
        """Test that adding days preserves positive timezone offset."""
        dt = FP_DateTime("1973-12-25T00:00:00.000+10:00")
        qty = FP_Quantity(7, "days")
        result = dt.plus(qty)
        assert result == "1974-01-01T00:00:00.000+10:00"

    def test_plus_days_preserves_timezone_z(self) -> None:
        """Test that adding days preserves Z timezone."""
        dt = FP_DateTime("1973-12-25T00:00:00.000Z")
        qty = FP_Quantity(7, "days")
        result = dt.plus(qty)
        assert result == "1974-01-01T00:00:00.000+00:00"

    def test_plus_days_preserves_timezone_negative(self) -> None:
        """Test that adding days preserves negative timezone offset."""
        dt = FP_DateTime("1973-12-25T00:00:00.000-05:00")
        qty = FP_Quantity(7, "days")
        result = dt.plus(qty)
        assert result == "1974-01-01T00:00:00.000-05:00"

    def test_plus_hours_preserves_timezone(self) -> None:
        """Test that adding hours preserves timezone."""
        dt = FP_DateTime("1973-12-25T00:00:00.000+10:00")
        qty = FP_Quantity(1, "hour")
        result = dt.plus(qty)
        assert result == "1973-12-25T01:00:00.000+10:00"

    def test_plus_minutes_preserves_timezone(self) -> None:
        """Test that adding minutes preserves timezone."""
        dt = FP_DateTime("1973-12-25T00:00:00.000+10:00")
        qty = FP_Quantity(1, "minute")
        result = dt.plus(qty)
        assert result == "1973-12-25T00:01:00.000+10:00"

    def test_plus_seconds_preserves_timezone(self) -> None:
        """Test that adding seconds preserves timezone."""
        dt = FP_DateTime("1973-12-25T00:00:00.000+10:00")
        qty = FP_Quantity(1, "second")
        result = dt.plus(qty)
        assert result == "1973-12-25T00:00:01.000+10:00"

    def test_plus_milliseconds_preserves_timezone(self) -> None:
        """Test that adding milliseconds preserves timezone."""
        dt = FP_DateTime("1973-12-25T00:00:00.000+10:00")
        qty = FP_Quantity(10, "millisecond")
        result = dt.plus(qty)
        assert result == "1973-12-25T00:00:00.010+10:00"

    def test_plus_weeks_preserves_timezone(self) -> None:
        """Test that adding weeks preserves timezone."""
        dt = FP_DateTime("1973-12-25T00:00:00.000+10:00")
        qty = FP_Quantity(1, "week")
        result = dt.plus(qty)
        assert result == "1974-01-01T00:00:00.000+10:00"

    def test_plus_months_preserves_timezone(self) -> None:
        """Test that adding months preserves timezone."""
        dt = FP_DateTime("1973-12-25T00:00:00.000+10:00")
        qty = FP_Quantity(1, "month")
        result = dt.plus(qty)
        assert result == "1974-01-25T00:00:00.000+10:00"

    def test_plus_years_preserves_timezone(self) -> None:
        """Test that adding years preserves timezone."""
        dt = FP_DateTime("1973-12-25T00:00:00.000+10:00")
        qty = FP_Quantity(1, "year")
        result = dt.plus(qty)
        assert result == "1974-12-25T00:00:00.000+10:00"


class TestDateTimePrecisionCalculation:
    """Tests for DateTime precision calculation."""

    def test_precision_with_positive_timezone(self) -> None:
        """Test precision calculation with positive timezone."""
        dt = FP_DateTime("1973-12-25T00:00:00.000+10:00")
        assert dt._precision == 7  # millisecond precision

    def test_precision_with_z_timezone(self) -> None:
        """Test precision calculation with Z timezone."""
        dt = FP_DateTime("1973-12-25T00:00:00.000Z")
        assert dt._precision == 7  # millisecond precision

    def test_precision_with_negative_timezone(self) -> None:
        """Test precision calculation with negative timezone."""
        dt = FP_DateTime("1973-12-25T00:00:00.000-05:00")
        assert dt._precision == 7  # millisecond precision

    def test_precision_without_timezone(self) -> None:
        """Test precision calculation without timezone."""
        dt = FP_DateTime("1973-12-25T00:00:00.000")
        assert dt._precision == 7  # millisecond precision

    def test_precision_date_only(self) -> None:
        """Test precision calculation for date-only (FP_Date)."""
        from ...engine.nodes import FP_Date
        dt = FP_Date("1973-12-25")
        assert dt._precision == 3  # day precision

    def test_precision_year_month_only(self) -> None:
        """Test precision calculation for year-month only (FP_Date)."""
        from ...engine.nodes import FP_Date
        dt = FP_Date("1973-12")
        assert dt._precision == 2  # month precision

    def test_precision_year_only(self) -> None:
        """Test precision calculation for year only (FP_Date)."""
        from ...engine.nodes import FP_Date
        dt = FP_Date("1973")
        assert dt._precision == 1  # year precision


class TestDateTimeComparison:
    """Tests for DateTime comparison with timezone awareness."""

    def test_equals_same_instant_different_timezone(self) -> None:
        """Test that datetimes representing the same instant are equal."""
        # 1973-12-25T00:00:00+10:00 = 1973-12-24T14:00:00Z
        dt1 = FP_DateTime("1973-12-25T00:00:00.000+10:00")
        dt2 = FP_DateTime("1973-12-24T14:00:00.000Z")
        assert dt1.equals(dt2) is True

    def test_compare_same_instant_different_timezone(self) -> None:
        """Test that comparison works correctly across timezones."""
        dt1 = FP_DateTime("1973-12-25T00:00:00.000+10:00")
        dt2 = FP_DateTime("1973-12-24T14:00:00.000Z")
        assert dt1.compare(dt2) == 0  # Equal

    def test_compare_different_times_same_date(self) -> None:
        """Test comparison of different times on same date."""
        dt1 = FP_DateTime("2020-01-01T00:00:00.000+10:00")
        dt2 = FP_DateTime("2020-01-01T00:00:00.000-05:00")
        # dt1 is 15 hours ahead of dt2 in absolute time
        assert dt1.compare(dt2) == -1  # dt1 < dt2


class TestDateTimeStringRepresentation:
    """Tests for DateTime string representation."""

    def test_str_preserves_timezone(self) -> None:
        """Test that string representation preserves timezone."""
        dt = FP_DateTime("1973-12-25T00:00:00.000+10:00")
        assert "+10:00" in str(dt)

    def test_str_z_timezone_shows_offset(self) -> None:
        """Test that Z timezone is shown as +00:00 in string."""
        dt = FP_DateTime("1973-12-25T00:00:00.000Z")
        # The string representation may show +00:00 for Z
        assert "Z" in str(dt) or "+00:00" in str(dt)

    def test_str_date_only_no_timezone(self) -> None:
        """Test that date-only (FP_Date) has no timezone in string."""
        from ...engine.nodes import FP_Date
        dt = FP_Date("1973-12-25")
        assert str(dt) == "1973-12-25"
