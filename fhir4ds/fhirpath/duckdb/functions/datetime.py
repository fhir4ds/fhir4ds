"""
FHIRPath Date/Time Functions

Implements date/time handling per FHIRPath specification:
- Date/time literals: @2019, @2019-01, @2019-01-01, @T12:30, @T12:30:00
- Date/time arithmetic: date + duration, date - duration, date - date
- Duration components: years, months, weeks, days, hours, minutes, seconds, milliseconds
- Component extraction: year(), month(), day(), hour(), minute(), second()
- Date/time parts: dateComponent(), timeComponent()
- Current time: now(), today(), timeOfDay()
- Comparison: <, >, <=, >=

Key FHIRPath semantics:
- Dates use ISO 8601 format
- Precision matters: @2019 != @2019-01-01
- Timezone handling per FHIR spec
- Empty collection propagation for invalid operations
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, time as dt_time, timedelta
from enum import Enum
from typing import TYPE_CHECKING, Any, Optional, Union

if TYPE_CHECKING:
    from collections.abc import Callable


class DatePrecision(Enum):
    """Precision level for date/datetime values."""

    YEAR = "year"
    MONTH = "month"
    DAY = "day"
    HOUR = "hour"
    MINUTE = "minute"
    SECOND = "second"
    MILLISECOND = "millisecond"


class TimePrecision(Enum):
    """Precision level for time values."""

    HOUR = "hour"
    MINUTE = "minute"
    SECOND = "second"
    MILLISECOND = "millisecond"


@dataclass
class FHIRDate:
    """
    FHIR date value with precision tracking.

    FHIR dates can have different precision levels:
    - @2019 (year only)
    - @2019-01 (year-month)
    - @2019-01-01 (full date)

    Attributes:
        value: The Python date value.
        precision: The precision of the date.
        timezone: Optional timezone offset as string (e.g., '+05:00', 'Z').
    """

    value: date
    precision: DatePrecision = DatePrecision.DAY
    timezone: Optional[str] = None

    def __str__(self) -> str:
        """Format date according to precision."""
        if self.precision == DatePrecision.YEAR:
            return self.value.strftime("%Y")
        elif self.precision == DatePrecision.MONTH:
            return self.value.strftime("%Y-%m")
        base = self.value.strftime("%Y-%m-%d")
        if self.timezone:
            return base + self.timezone
        return base

    def __repr__(self) -> str:
        return f"FHIRDate({self}, precision={self.precision.value})"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, FHIRDate):
            return False
        return self.value == other.value and self.precision == other.precision

    def __lt__(self, other: FHIRDate) -> bool:
        # Compare at the lower precision (the one with less information)
        min_precision = min(self.precision, other.precision, key=lambda p: p.value)
        result = self._compare_at_precision(other, min_precision)
        return result < 0

    def __le__(self, other: FHIRDate) -> bool:
        # Compare at the lower precision
        min_precision = min(self.precision, other.precision, key=lambda p: p.value)
        result = self._compare_at_precision(other, min_precision)
        return result <= 0

    def __gt__(self, other: FHIRDate) -> bool:
        # Compare at the lower precision
        min_precision = min(self.precision, other.precision, key=lambda p: p.value)
        result = self._compare_at_precision(other, min_precision)
        return result > 0

    def __ge__(self, other: FHIRDate) -> bool:
        # Compare at the lower precision
        min_precision = min(self.precision, other.precision, key=lambda p: p.value)
        result = self._compare_at_precision(other, min_precision)
        return result >= 0

    def _compare_at_precision(self, other: FHIRDate, precision: DatePrecision) -> int:
        """Compare dates at a specific precision level."""
        if precision == DatePrecision.YEAR:
            return (self.value.year - other.value.year)
        elif precision == DatePrecision.MONTH:
            diff = (self.value.year - other.value.year) * 12 + (self.value.month - other.value.month)
            return diff
        else:
            # Full date comparison
            if self.value < other.value:
                return -1
            elif self.value > other.value:
                return 1
            return 0

    @classmethod
    def from_string(cls, s: str) -> FHIRDate:
        """Parse a FHIR date string."""
        return DateTimeLiteral.parse_date(s)


@dataclass
class FHIRDateTime:
    """
    FHIR datetime value with precision and timezone tracking.

    FHIR datetimes can have different precision levels:
    - @2019 (year only)
    - @2019-01 (year-month)
    - @2019-01-01 (full date)
    - @2019-01-01T12 (with hour)
    - @2019-01-01T12:30 (with minute)
    - @2019-01-01T12:30:00 (with second)
    - @2019-01-01T12:30:00.000 (with millisecond)

    Attributes:
        value: The Python datetime value.
        precision: The precision of the datetime.
        timezone: Optional timezone offset as string.
    """

    value: datetime
    precision: DatePrecision = DatePrecision.DAY
    timezone: Optional[str] = None

    def __str__(self) -> str:
        """Format datetime according to precision."""
        if self.precision == DatePrecision.YEAR:
            base = self.value.strftime("%Y")
        elif self.precision == DatePrecision.MONTH:
            base = self.value.strftime("%Y-%m")
        elif self.precision == DatePrecision.DAY:
            base = self.value.strftime("%Y-%m-%d")
        elif self.precision == DatePrecision.HOUR:
            base = self.value.strftime("%Y-%m-%dT%H")
        elif self.precision == DatePrecision.MINUTE:
            base = self.value.strftime("%Y-%m-%dT%H:%M")
        elif self.precision == DatePrecision.SECOND:
            base = self.value.strftime("%Y-%m-%dT%H:%M:%S")
        else:  # MILLISECOND
            base = self.value.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3]

        if self.timezone and self.precision.value >= DatePrecision.HOUR.value:
            return base + self.timezone
        return base

    def __repr__(self) -> str:
        return f"FHIRDateTime({self}, precision={self.precision.value})"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, FHIRDateTime):
            return False
        return (self.value == other.value and
                self.precision == other.precision and
                self.timezone == other.timezone)

    def __lt__(self, other: FHIRDateTime) -> bool:
        # Compare at the lower precision (the one with less information/lower numeric value)
        min_precision = min(self.precision, other.precision,
                          key=lambda p: p.value)
        result = self._compare_at_precision(other, min_precision)
        # If equal at this precision, we can't say one is less than the other
        return result < 0

    def __le__(self, other: FHIRDateTime) -> bool:
        # Compare at the lower precision
        min_precision = min(self.precision, other.precision,
                          key=lambda p: p.value)
        result = self._compare_at_precision(other, min_precision)
        return result <= 0

    def __gt__(self, other: FHIRDateTime) -> bool:
        # Compare at the lower precision
        min_precision = min(self.precision, other.precision,
                          key=lambda p: p.value)
        result = self._compare_at_precision(other, min_precision)
        return result > 0

    def __ge__(self, other: FHIRDateTime) -> bool:
        # Compare at the lower precision
        min_precision = min(self.precision, other.precision,
                          key=lambda p: p.value)
        result = self._compare_at_precision(other, min_precision)
        return result >= 0

    def _compare_at_precision(self, other: FHIRDateTime, precision: DatePrecision) -> int:
        """Compare datetimes at a specific precision level."""
        if precision == DatePrecision.YEAR:
            return self.value.year - other.value.year
        elif precision == DatePrecision.MONTH:
            diff = (self.value.year - other.value.year) * 12 + (self.value.month - other.value.month)
            return diff
        elif precision == DatePrecision.DAY:
            if self.value.date() < other.value.date():
                return -1
            elif self.value.date() > other.value.date():
                return 1
            return 0
        elif precision == DatePrecision.HOUR:
            if self.value.year != other.value.year:
                return self.value.year - other.value.year
            if self.value.month != other.value.month:
                return self.value.month - other.value.month
            if self.value.day != other.value.day:
                return self.value.day - other.value.day
            return self.value.hour - other.value.hour
        elif precision == DatePrecision.MINUTE:
            if self.value.year != other.value.year:
                return self.value.year - other.value.year
            if self.value.month != other.value.month:
                return self.value.month - other.value.month
            if self.value.day != other.value.day:
                return self.value.day - other.value.day
            if self.value.hour != other.value.hour:
                return self.value.hour - other.value.hour
            return self.value.minute - other.value.minute
        elif precision == DatePrecision.SECOND:
            if self.value.year != other.value.year:
                return self.value.year - other.value.year
            if self.value.month != other.value.month:
                return self.value.month - other.value.month
            if self.value.day != other.value.day:
                return self.value.day - other.value.day
            if self.value.hour != other.value.hour:
                return self.value.hour - other.value.hour
            if self.value.minute != other.value.minute:
                return self.value.minute - other.value.minute
            return self.value.second - other.value.second
        else:  # MILLISECOND
            # Full comparison
            if self.value < other.value:
                return -1
            elif self.value > other.value:
                return 1
            return 0

    @property
    def date_component(self) -> FHIRDate:
        """Extract date component."""
        return FHIRDate(
            value=self.value.date(),
            precision=min(self.precision, DatePrecision.DAY, key=lambda p: p.value),
            timezone=self.timezone
        )

    @property
    def time_component(self) -> FHIRTime:
        """Extract time component."""
        precision = TimePrecision.HOUR
        if self.precision.value >= DatePrecision.MINUTE.value:
            precision = TimePrecision.MINUTE
        if self.precision.value >= DatePrecision.SECOND.value:
            precision = TimePrecision.SECOND
        if self.precision.value >= DatePrecision.MILLISECOND.value:
            precision = TimePrecision.MILLISECOND

        return FHIRTime(
            value=self.value.time(),
            precision=precision,
            timezone=self.timezone
        )

    @classmethod
    def from_string(cls, s: str) -> FHIRDateTime:
        """Parse a FHIR datetime string."""
        return DateTimeLiteral.parse_datetime(s)


@dataclass
class FHIRTime:
    """
    FHIR time value with precision tracking.

    FHIR times can have different precision levels:
    - @T12 (hour only)
    - @T12:30 (hour-minute)
    - @T12:30:00 (hour-minute-second)
    - @T12:30:00.000 (with millisecond)

    Attributes:
        value: The Python time value.
        precision: The precision of the time.
        timezone: Optional timezone offset as string.
    """

    value: dt_time
    precision: TimePrecision = TimePrecision.MINUTE
    timezone: Optional[str] = None

    def __str__(self) -> str:
        """Format time according to precision."""
        if self.precision == TimePrecision.HOUR:
            base = f"T{self.value.hour:02d}"
        elif self.precision == TimePrecision.MINUTE:
            base = self.value.strftime("T%H:%M")
        elif self.precision == TimePrecision.SECOND:
            base = self.value.strftime("T%H:%M:%S")
        else:  # MILLISECOND
            base = self.value.strftime("T%H:%M:%S.%f")[:-3]

        if self.timezone:
            return base + self.timezone
        return base

    def __repr__(self) -> str:
        return f"FHIRTime({self}, precision={self.precision.value})"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, FHIRTime):
            return False
        return (self.value == other.value and
                self.precision == other.precision)

    def __lt__(self, other: FHIRTime) -> bool:
        # Compare at the lower precision (the one with less information/lower numeric value)
        min_precision = min(self.precision, other.precision,
                          key=lambda p: p.value)
        result = self._compare_at_precision(other, min_precision)
        return result < 0

    def __le__(self, other: FHIRTime) -> bool:
        # Compare at the lower precision
        min_precision = min(self.precision, other.precision,
                          key=lambda p: p.value)
        result = self._compare_at_precision(other, min_precision)
        return result <= 0

    def __gt__(self, other: FHIRTime) -> bool:
        # Compare at the lower precision
        min_precision = min(self.precision, other.precision,
                          key=lambda p: p.value)
        result = self._compare_at_precision(other, min_precision)
        return result > 0

    def __ge__(self, other: FHIRTime) -> bool:
        # Compare at the lower precision
        min_precision = min(self.precision, other.precision,
                          key=lambda p: p.value)
        result = self._compare_at_precision(other, min_precision)
        return result >= 0

    def _compare_at_precision(self, other: FHIRTime, precision: TimePrecision) -> int:
        """Compare times at a specific precision level."""
        if precision == TimePrecision.HOUR:
            return (self.value.hour - other.value.hour)
        elif precision == TimePrecision.MINUTE:
            if self.value.hour != other.value.hour:
                return self.value.hour - other.value.hour
            return self.value.minute - other.value.minute
        elif precision == TimePrecision.SECOND:
            if self.value.hour != other.value.hour:
                return self.value.hour - other.value.hour
            if self.value.minute != other.value.minute:
                return self.value.minute - other.value.minute
            return self.value.second - other.value.second
        else:  # MILLISECOND
            # Compare as microseconds
            self_us = self.value.hour * 3600000000 + self.value.minute * 60000000 + \
                      self.value.second * 1000000 + self.value.microsecond
            other_us = other.value.hour * 3600000000 + other.value.minute * 60000000 + \
                       other.value.second * 1000000 + other.value.microsecond
            return self_us - other_us

    @classmethod
    def from_string(cls, s: str) -> FHIRTime:
        """Parse a FHIR time string."""
        return DateTimeLiteral.parse_time(s)


@dataclass
class FHIRDuration:
    """
    FHIR duration/period value.

    FHIRPath durations are specified as:
    - X years (or year)
    - X months (or month)
    - X weeks (or week)
    - X days (or day)
    - X hours (or hour)
    - X minutes (or minute)
    - X seconds (or second)
    - X milliseconds (or millisecond)

    Durations can be positive or negative.

    Attributes:
        years: Number of years.
        months: Number of months.
        weeks: Number of weeks.
        days: Number of days.
        hours: Number of hours.
        minutes: Number of minutes.
        seconds: Number of seconds.
        milliseconds: Number of milliseconds.
    """

    years: int = 0
    months: int = 0
    weeks: int = 0
    days: int = 0
    hours: int = 0
    minutes: int = 0
    seconds: int = 0
    milliseconds: int = 0

    def __str__(self) -> str:
        """Format duration as FHIRPath duration literal."""
        parts = []
        if self.years:
            parts.append(f"{self.years} year{'s' if abs(self.years) != 1 else ''}")
        if self.months:
            parts.append(f"{self.months} month{'s' if abs(self.months) != 1 else ''}")
        if self.weeks:
            parts.append(f"{self.weeks} week{'s' if abs(self.weeks) != 1 else ''}")
        if self.days:
            parts.append(f"{self.days} day{'s' if abs(self.days) != 1 else ''}")
        if self.hours:
            parts.append(f"{self.hours} hour{'s' if abs(self.hours) != 1 else ''}")
        if self.minutes:
            parts.append(f"{self.minutes} minute{'s' if abs(self.minutes) != 1 else ''}")
        if self.seconds:
            parts.append(f"{self.seconds} second{'s' if abs(self.seconds) != 1 else ''}")
        if self.milliseconds:
            parts.append(f"{self.milliseconds} millisecond{'s' if abs(self.milliseconds) != 1 else ''}")
        return " ".join(parts) if parts else "0 seconds"

    def __repr__(self) -> str:
        return f"FHIRDuration({self})"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, FHIRDuration):
            return False
        return (self.years == other.years and
                self.months == other.months and
                self.weeks == other.weeks and
                self.days == other.days and
                self.hours == other.hours and
                self.minutes == other.minutes and
                self.seconds == other.seconds and
                self.milliseconds == other.milliseconds)

    def __neg__(self) -> FHIRDuration:
        """Negate the duration."""
        return FHIRDuration(
            years=-self.years,
            months=-self.months,
            weeks=-self.weeks,
            days=-self.days,
            hours=-self.hours,
            minutes=-self.minutes,
            seconds=-self.seconds,
            milliseconds=-self.milliseconds,
        )

    def __add__(self, other: FHIRDuration) -> FHIRDuration:
        """Add two durations."""
        if not isinstance(other, FHIRDuration):
            raise TypeError(f"Cannot add {type(other)} to FHIRDuration")
        return FHIRDuration(
            years=self.years + other.years,
            months=self.months + other.months,
            weeks=self.weeks + other.weeks,
            days=self.days + other.days,
            hours=self.hours + other.hours,
            minutes=self.minutes + other.minutes,
            seconds=self.seconds + other.seconds,
            milliseconds=self.milliseconds + other.milliseconds,
        )

    def __sub__(self, other: FHIRDuration) -> FHIRDuration:
        """Subtract two durations."""
        return self + (-other)

    def to_timedelta(self) -> timedelta:
        """
        Convert to Python timedelta.

        Note: This is an approximation since timedelta doesn't support
        months or years (variable length). Years are approximated as 365 days
        and months as 30 days.
        """
        total_days = (
            self.days +
            self.weeks * 7 +
            self.months * 30 +  # Approximation
            self.years * 365    # Approximation
        )
        total_seconds = (
            self.hours * 3600 +
            self.minutes * 60 +
            self.seconds +
            self.milliseconds / 1000
        )
        return timedelta(days=total_days, seconds=total_seconds)

    @property
    def is_empty(self) -> bool:
        """Check if duration is zero."""
        return (self.years == 0 and self.months == 0 and
                self.weeks == 0 and self.days == 0 and
                self.hours == 0 and self.minutes == 0 and
                self.seconds == 0 and self.milliseconds == 0)


class DateTimeLiteral:
    """
    Parser and evaluator for FHIRPath date/time literals.

    Handles:
    - @2019 - year
    - @2019-01 - year-month
    - @2019-01-01 - full date
    - @T12:30 - time
    - @T12:30:00 - time with seconds
    - @2019-01-01T12:30:00 - datetime
    """

    # Regex patterns for date/time parsing
    DATE_PATTERN = re.compile(
        r'^@?(\d{4})(?:-(\d{2}))?(?:-(\d{2}))?$'
    )
    TIME_PATTERN = re.compile(
        r'^@?T(\d{2})(?::(\d{2}))?(?::(\d{2}))?(?:\.(\d{3}))?$'
    )
    DATETIME_PATTERN = re.compile(
        r'^@?(\d{4})-(\d{2})-(\d{2})T(\d{2})(?::(\d{2}))?(?::(\d{2}))?(?:\.(\d{3}))?$'
    )
    TIMEZONE_PATTERN = re.compile(r'([Z]|[+-]\d{2}:\d{2})$')

    @staticmethod
    def parse_date(s: str) -> FHIRDate:
        """
        Parse a FHIR date literal.

        Args:
            s: Date string like "@2019", "@2019-01", "@2019-01-01" or without @

        Returns:
            FHIRDate object.

        Raises:
            ValueError: If the date format is invalid.
        """
        # Extract timezone if present
        timezone = None
        tz_match = DateTimeLiteral.TIMEZONE_PATTERN.search(s)
        if tz_match:
            timezone = tz_match.group(1)
            s = s[:tz_match.start()]

        # Remove @ prefix if present
        if s.startswith('@'):
            s = s[1:]

        match = DateTimeLiteral.DATE_PATTERN.match(s)
        if not match:
            raise ValueError(f"Invalid date format: {s}")

        year = int(match.group(1))
        month = int(match.group(2)) if match.group(2) else 1
        day = int(match.group(3)) if match.group(3) else 1

        # Determine precision
        if match.group(3):
            precision = DatePrecision.DAY
        elif match.group(2):
            precision = DatePrecision.MONTH
        else:
            precision = DatePrecision.YEAR

        return FHIRDate(
            value=date(year, month, day),
            precision=precision,
            timezone=timezone
        )

    @staticmethod
    def parse_time(s: str) -> FHIRTime:
        """
        Parse a FHIR time literal.

        Args:
            s: Time string like "@T12:30", "@T12:30:00" or without @

        Returns:
            FHIRTime object.

        Raises:
            ValueError: If the time format is invalid.
        """
        # Extract timezone if present
        timezone = None
        tz_match = DateTimeLiteral.TIMEZONE_PATTERN.search(s)
        if tz_match:
            timezone = tz_match.group(1)
            s = s[:tz_match.start()]

        # Remove @ prefix if present
        if s.startswith('@'):
            s = s[1:]

        match = DateTimeLiteral.TIME_PATTERN.match(s)
        if not match:
            raise ValueError(f"Invalid time format: {s}")

        hour = int(match.group(1))
        minute = int(match.group(2)) if match.group(2) else 0
        second = int(match.group(3)) if match.group(3) else 0
        microsecond = int(match.group(4)) * 1000 if match.group(4) else 0

        # Determine precision
        if match.group(4):
            precision = TimePrecision.MILLISECOND
        elif match.group(3):
            precision = TimePrecision.SECOND
        elif match.group(2):
            precision = TimePrecision.MINUTE
        else:
            precision = TimePrecision.HOUR

        return FHIRTime(
            value=dt_time(hour, minute, second, microsecond),
            precision=precision,
            timezone=timezone
        )

    @staticmethod
    def parse_datetime(s: str) -> FHIRDateTime:
        """
        Parse a FHIR datetime literal.

        Args:
            s: Datetime string like "@2019-01-01T12:30:00" or without @

        Returns:
            FHIRDateTime object.

        Raises:
            ValueError: If the datetime format is invalid.
        """
        # Extract timezone if present
        timezone = None
        tz_match = DateTimeLiteral.TIMEZONE_PATTERN.search(s)
        if tz_match:
            timezone = tz_match.group(1)
            s = s[:tz_match.start()]

        # Remove @ prefix if present
        if s.startswith('@'):
            s = s[1:]

        # Try full datetime first
        match = DateTimeLiteral.DATETIME_PATTERN.match(s)
        if match:
            year = int(match.group(1))
            month = int(match.group(2))
            day = int(match.group(3))
            hour = int(match.group(4))
            minute = int(match.group(5)) if match.group(5) else 0
            second = int(match.group(6)) if match.group(6) else 0
            microsecond = int(match.group(7)) * 1000 if match.group(7) else 0

            # Determine precision
            if match.group(7):
                precision = DatePrecision.MILLISECOND
            elif match.group(6):
                precision = DatePrecision.SECOND
            elif match.group(5):
                precision = DatePrecision.MINUTE
            else:
                precision = DatePrecision.HOUR

            return FHIRDateTime(
                value=datetime(year, month, day, hour, minute, second, microsecond),
                precision=precision,
                timezone=timezone
            )

        # Try date-only format
        date_match = DateTimeLiteral.DATE_PATTERN.match(s)
        if date_match:
            fhir_date = DateTimeLiteral.parse_date(s)
            return FHIRDateTime(
                value=datetime.combine(fhir_date.value, dt_time(0, 0, 0)),
                precision=fhir_date.precision,
                timezone=fhir_date.timezone
            )

        # Try time-only format (today's date with time)
        time_match = DateTimeLiteral.TIME_PATTERN.match(s)
        if time_match:
            fhir_time = DateTimeLiteral.parse_time(s)
            return FHIRDateTime(
                value=datetime.combine(date.today(), fhir_time.value),
                precision=DatePrecision(fhir_time.precision.value),
                timezone=fhir_time.timezone
            )

        raise ValueError(f"Invalid datetime format: {s}")

    @staticmethod
    def parse(s: str) -> Union[FHIRDate, FHIRTime, FHIRDateTime]:
        """
        Parse any FHIR date/time literal.

        Auto-detects the format and returns the appropriate type.

        Args:
            s: Date/time string.

        Returns:
            FHIRDate, FHIRTime, or FHIRDateTime object.

        Raises:
            ValueError: If the format is invalid.
        """
        # Remove @ prefix if present
        stripped = s.lstrip('@')

        if stripped.startswith('T'):
            return DateTimeLiteral.parse_time(s)

        # Check if it's a datetime (has both date and time)
        if 'T' in stripped:
            return DateTimeLiteral.parse_datetime(s)

        # Check if it's a date
        if DateTimeLiteral.DATE_PATTERN.match(stripped):
            return DateTimeLiteral.parse_date(s)

        raise ValueError(f"Invalid date/time format: {s}")


class DateTimeDuration:
    """
    Parser and utilities for FHIRPath durations.

    Handles:
    - X years (or year)
    - X months (or month)
    - X weeks (or week)
    - X days (or day)
    - X hours (or hour)
    - X minutes (or minute)
    - X seconds (or second)
    - X milliseconds (or millisecond)
    """

    DURATION_PATTERN = re.compile(
        r'^(-?\d+)\s+(year|month|week|day|hour|minute|second|millisecond)s?$',
        re.IGNORECASE
    )

    @staticmethod
    def parse(s: str) -> FHIRDuration:
        """
        Parse a FHIR duration literal.

        Args:
            s: Duration string like "5 years", "3 days", "1 hour"

        Returns:
            FHIRDuration object.

        Raises:
            ValueError: If the format is invalid.
        """
        match = DateTimeDuration.DURATION_PATTERN.match(s.strip())
        if not match:
            raise ValueError(f"Invalid duration format: {s}")

        value = int(match.group(1))
        unit = match.group(2).lower()

        duration = FHIRDuration()
        if unit == 'year':
            duration.years = value
        elif unit == 'month':
            duration.months = value
        elif unit == 'week':
            duration.weeks = value
        elif unit == 'day':
            duration.days = value
        elif unit == 'hour':
            duration.hours = value
        elif unit == 'minute':
            duration.minutes = value
        elif unit == 'second':
            duration.seconds = value
        elif unit == 'millisecond':
            duration.milliseconds = value

        return duration

    @staticmethod
    def years(value: int) -> FHIRDuration:
        """Create a duration of years."""
        return FHIRDuration(years=value)

    @staticmethod
    def months(value: int) -> FHIRDuration:
        """Create a duration of months."""
        return FHIRDuration(months=value)

    @staticmethod
    def weeks(value: int) -> FHIRDuration:
        """Create a duration of weeks."""
        return FHIRDuration(weeks=value)

    @staticmethod
    def days(value: int) -> FHIRDuration:
        """Create a duration of days."""
        return FHIRDuration(days=value)

    @staticmethod
    def hours(value: int) -> FHIRDuration:
        """Create a duration of hours."""
        return FHIRDuration(hours=value)

    @staticmethod
    def minutes(value: int) -> FHIRDuration:
        """Create a duration of minutes."""
        return FHIRDuration(minutes=value)

    @staticmethod
    def seconds(value: int) -> FHIRDuration:
        """Create a duration of seconds."""
        return FHIRDuration(seconds=value)

    @staticmethod
    def milliseconds(value: int) -> FHIRDuration:
        """Create a duration of milliseconds."""
        return FHIRDuration(milliseconds=value)


class DateTimeArithmetic:
    """
    Date/time arithmetic operations.

    Handles:
    - date + duration
    - date - duration
    - date - date (difference)
    """

    @staticmethod
    def add(dt: Union[FHIRDate, FHIRDateTime], duration: FHIRDuration) -> Union[FHIRDate, FHIRDateTime]:
        """
        Add duration to date/datetime.

        Args:
            dt: FHIRDate or FHIRDateTime.
            duration: FHIRDuration to add.

        Returns:
            New FHIRDate or FHIRDateTime with duration added.
        """
        if isinstance(dt, FHIRDate):
            return DateTimeArithmetic._add_to_date(dt, duration)
        elif isinstance(dt, FHIRDateTime):
            return DateTimeArithmetic._add_to_datetime(dt, duration)
        else:
            raise TypeError(f"Cannot add duration to {type(dt)}")

    @staticmethod
    def subtract(dt: Union[FHIRDate, FHIRDateTime], duration: FHIRDuration) -> Union[FHIRDate, FHIRDateTime]:
        """
        Subtract duration from date/datetime.

        Args:
            dt: FHIRDate or FHIRDateTime.
            duration: FHIRDuration to subtract.

        Returns:
            New FHIRDate or FHIRDateTime with duration subtracted.
        """
        return DateTimeArithmetic.add(dt, -duration)

    @staticmethod
    def difference(dt1: Union[FHIRDate, FHIRDateTime],
                   dt2: Union[FHIRDate, FHIRDateTime]) -> FHIRDuration:
        """
        Calculate difference between two dates/datetimes.

        Args:
            dt1: First date/datetime.
            dt2: Second date/datetime.

        Returns:
            FHIRDuration representing the difference.
        """
        # Convert to datetime for calculation
        if isinstance(dt1, FHIRDate):
            dt1_dt = datetime.combine(dt1.value, dt_time(0, 0, 0))
        else:
            dt1_dt = dt1.value

        if isinstance(dt2, FHIRDate):
            dt2_dt = datetime.combine(dt2.value, dt_time(0, 0, 0))
        else:
            dt2_dt = dt2.value

        # Calculate difference
        delta = dt1_dt - dt2_dt

        # Convert to duration
        total_seconds = int(delta.total_seconds())
        days = delta.days

        # Calculate hours, minutes, seconds from remainder
        hours = abs(total_seconds) // 3600
        minutes = (abs(total_seconds) % 3600) // 60
        seconds = abs(total_seconds) % 60

        # Determine sign
        sign = -1 if delta.total_seconds() < 0 else 1

        return FHIRDuration(
            days=days,
            hours=sign * hours,
            minutes=sign * minutes,
            seconds=sign * seconds,
        )

    @staticmethod
    def _add_to_date(d: FHIRDate, duration: FHIRDuration) -> FHIRDate:
        """Add duration to date."""
        from dateutil.relativedelta import relativedelta

        # Use relativedelta for proper month/year handling
        delta = relativedelta(
            years=duration.years,
            months=duration.months,
            weeks=duration.weeks,
            days=duration.days
        )

        new_date = d.value + delta

        return FHIRDate(
            value=new_date,
            precision=d.precision,
            timezone=d.timezone
        )

    @staticmethod
    def _add_to_datetime(dt: FHIRDateTime, duration: FHIRDuration) -> FHIRDateTime:
        """Add duration to datetime."""
        from dateutil.relativedelta import relativedelta

        # Use relativedelta for proper month/year handling
        delta = relativedelta(
            years=duration.years,
            months=duration.months,
            weeks=duration.weeks,
            days=duration.days,
            hours=duration.hours,
            minutes=duration.minutes,
            seconds=duration.seconds,
            microseconds=duration.milliseconds * 1000
        )

        new_datetime = dt.value + delta

        return FHIRDateTime(
            value=new_datetime,
            precision=dt.precision,
            timezone=dt.timezone
        )


class DateTimeFunctions:
    """
    Date/time extraction and utility functions.

    Implements:
    - year(), month(), day() - extract date components
    - hour(), minute(), second() - extract time components
    - dateComponent() - extract date from datetime
    - timeComponent() - extract time from datetime
    - now() - current datetime
    - today() - current date
    - timeOfDay() - current time
    """

    @staticmethod
    def year(dt: Union[FHIRDate, FHIRDateTime]) -> Optional[int]:
        """
        Extract year from date/datetime.

        Args:
            dt: FHIRDate or FHIRDateTime.

        Returns:
            Year as integer, or None if input is None/empty.
        """
        if dt is None:
            return None
        if isinstance(dt, FHIRDate):
            return dt.value.year
        elif isinstance(dt, FHIRDateTime):
            return dt.value.year
        return None

    @staticmethod
    def month(dt: Union[FHIRDate, FHIRDateTime]) -> Optional[int]:
        """
        Extract month from date/datetime.

        Args:
            dt: FHIRDate or FHIRDateTime.

        Returns:
            Month as integer (1-12), or None if input is None/empty.
        """
        if dt is None:
            return None
        if isinstance(dt, FHIRDate):
            return dt.value.month
        elif isinstance(dt, FHIRDateTime):
            return dt.value.month
        return None

    @staticmethod
    def day(dt: Union[FHIRDate, FHIRDateTime]) -> Optional[int]:
        """
        Extract day from date/datetime.

        Args:
            dt: FHIRDate or FHIRDateTime.

        Returns:
            Day as integer (1-31), or None if input is None/empty.
        """
        if dt is None:
            return None
        if isinstance(dt, FHIRDate):
            return dt.value.day
        elif isinstance(dt, FHIRDateTime):
            return dt.value.day
        return None

    @staticmethod
    def hour(dt: Union[FHIRDateTime, FHIRTime]) -> Optional[int]:
        """
        Extract hour from datetime/time.

        Args:
            dt: FHIRDateTime or FHIRTime.

        Returns:
            Hour as integer (0-23), or None if input is None/empty.
        """
        if dt is None:
            return None
        if isinstance(dt, FHIRDateTime):
            return dt.value.hour
        elif isinstance(dt, FHIRTime):
            return dt.value.hour
        return None

    @staticmethod
    def minute(dt: Union[FHIRDateTime, FHIRTime]) -> Optional[int]:
        """
        Extract minute from datetime/time.

        Args:
            dt: FHIRDateTime or FHIRTime.

        Returns:
            Minute as integer (0-59), or None if input is None/empty.
        """
        if dt is None:
            return None
        if isinstance(dt, FHIRDateTime):
            return dt.value.minute
        elif isinstance(dt, FHIRTime):
            return dt.value.minute
        return None

    @staticmethod
    def second(dt: Union[FHIRDateTime, FHIRTime]) -> Optional[int]:
        """
        Extract second from datetime/time.

        Args:
            dt: FHIRDateTime or FHIRTime.

        Returns:
            Second as integer (0-59), or None if input is None/empty.
        """
        if dt is None:
            return None
        if isinstance(dt, FHIRDateTime):
            return dt.value.second
        elif isinstance(dt, FHIRTime):
            return dt.value.second
        return None

    @staticmethod
    def dateComponent(dt: FHIRDateTime) -> Optional[FHIRDate]:
        """
        Extract date component from datetime.

        Args:
            dt: FHIRDateTime.

        Returns:
            FHIRDate with the date portion, or None if input is None.
        """
        if dt is None:
            return None
        if isinstance(dt, FHIRDateTime):
            return dt.date_component
        return None

    @staticmethod
    def timeComponent(dt: FHIRDateTime) -> Optional[FHIRTime]:
        """
        Extract time component from datetime.

        Args:
            dt: FHIRDateTime.

        Returns:
            FHIRTime with the time portion, or None if input is None.
        """
        if dt is None:
            return None
        if isinstance(dt, FHIRDateTime):
            return dt.time_component
        return None

    @staticmethod
    def now(timezone: Optional[str] = None) -> FHIRDateTime:
        """
        Get current datetime.

        Args:
            timezone: Optional timezone string (not fully implemented).

        Returns:
            FHIRDateTime representing now.
        """
        return FHIRDateTime(
            value=datetime.now(),
            precision=DatePrecision.MILLISECOND,
            timezone=timezone
        )

    @staticmethod
    def today(timezone: Optional[str] = None) -> FHIRDate:
        """
        Get current date.

        Args:
            timezone: Optional timezone string (not fully implemented).

        Returns:
            FHIRDate representing today.
        """
        return FHIRDate(
            value=date.today(),
            precision=DatePrecision.DAY,
            timezone=timezone
        )

    @staticmethod
    def timeOfDay(timezone: Optional[str] = None) -> FHIRTime:
        """
        Get current time.

        Args:
            timezone: Optional timezone string (not fully implemented).

        Returns:
            FHIRTime representing current time.
        """
        now = datetime.now()
        return FHIRTime(
            value=now.time(),
            precision=TimePrecision.MILLISECOND,
            timezone=timezone
        )


class DateTimeComparisons:
    """
    Date/time comparison operations.

    Implements ordering comparisons for dates and times:
    - <, >, <=, >=

    Follows FHIRPath precision rules for comparisons.
    """

    @staticmethod
    def less_than(dt1: Union[FHIRDate, FHIRDateTime, FHIRTime],
                  dt2: Union[FHIRDate, FHIRDateTime, FHIRTime]) -> Optional[bool]:
        """
        Compare if first is less than second.

        Args:
            dt1: First date/datetime/time.
            dt2: Second date/datetime/time.

        Returns:
            True if dt1 < dt2, False otherwise.
            Returns None if either input is None (empty collection).
        """
        if dt1 is None or dt2 is None:
            return None

        try:
            return dt1 < dt2
        except TypeError:
            return None

    @staticmethod
    def less_or_equal(dt1: Union[FHIRDate, FHIRDateTime, FHIRTime],
                      dt2: Union[FHIRDate, FHIRDateTime, FHIRTime]) -> Optional[bool]:
        """
        Compare if first is less than or equal to second.

        Args:
            dt1: First date/datetime/time.
            dt2: Second date/datetime/time.

        Returns:
            True if dt1 <= dt2, False otherwise.
            Returns None if either input is None.
        """
        if dt1 is None or dt2 is None:
            return None

        try:
            return dt1 <= dt2
        except TypeError:
            return None

    @staticmethod
    def greater_than(dt1: Union[FHIRDate, FHIRDateTime, FHIRTime],
                     dt2: Union[FHIRDate, FHIRDateTime, FHIRTime]) -> Optional[bool]:
        """
        Compare if first is greater than second.

        Args:
            dt1: First date/datetime/time.
            dt2: Second date/datetime/time.

        Returns:
            True if dt1 > dt2, False otherwise.
            Returns None if either input is None.
        """
        if dt1 is None or dt2 is None:
            return None

        try:
            return dt1 > dt2
        except TypeError:
            return None

    @staticmethod
    def greater_or_equal(dt1: Union[FHIRDate, FHIRDateTime, FHIRTime],
                         dt2: Union[FHIRDate, FHIRDateTime, FHIRTime]) -> Optional[bool]:
        """
        Compare if first is greater than or equal to second.

        Args:
            dt1: First date/datetime/time.
            dt2: Second date/datetime/time.

        Returns:
            True if dt1 >= dt2, False otherwise.
            Returns None if either input is None.
        """
        if dt1 is None or dt2 is None:
            return None

        try:
            return dt1 >= dt2
        except TypeError:
            return None

    @staticmethod
    def equals(dt1: Union[FHIRDate, FHIRDateTime, FHIRTime],
               dt2: Union[FHIRDate, FHIRDateTime, FHIRTime]) -> Optional[bool]:
        """
        Compare if two date/time values are equal.

        Takes precision into account: @2019 != @2019-01-01.

        Args:
            dt1: First date/datetime/time.
            dt2: Second date/datetime/time.

        Returns:
            True if equal, False otherwise.
            Returns None if either input is None.
        """
        if dt1 is None or dt2 is None:
            return None

        try:
            return dt1 == dt2
        except TypeError:
            return False

    @staticmethod
    def not_equals(dt1: Union[FHIRDate, FHIRDateTime, FHIRTime],
                   dt2: Union[FHIRDate, FHIRDateTime, FHIRTime]) -> Optional[bool]:
        """
        Compare if two date/time values are not equal.

        Args:
            dt1: First date/datetime/time.
            dt2: Second date/datetime/time.

        Returns:
            True if not equal, False otherwise.
            Returns None if either input is None.
        """
        result = DateTimeComparisons.equals(dt1, dt2)
        if result is None:
            return None
        return not result
