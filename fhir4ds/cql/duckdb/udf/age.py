"""
Vectorized CQL Age Calculation UDFs

Implements all CQL age calculation functions:
- AgeInYears(), AgeInMonths(), AgeInDays()
- AgeInHours(), AgeInMinutes(), AgeInSeconds()
- AgeInYearsAt(date), AgeInMonthsAt(date), AgeInDaysAt(date)
- CalculateAgeInYears(birthDate), CalculateAgeInYearsAt(birthDate, asOf)

Supports both scalar (row-by-row) and Arrow vectorized implementations.
"""

from __future__ import annotations

import os
from datetime import date, datetime, time, timezone
from typing import TYPE_CHECKING, Any, Callable

import orjson
import pyarrow as pa

if TYPE_CHECKING:
    import duckdb


import logging
import calendar

_logger = logging.getLogger(__name__)
# Feature flag for rollback
_USE_ARROW = os.environ.get("CQL_USE_ARROW_UDFS", "1") == "1"


def _extract_birthdate(resource: str) -> date | None:
    """Extract birthDate from a FHIR Patient resource.

    Handles partial dates per FHIR/CQL: year-only ('1990') assumes Jan 1,
    year-month ('1990-03') assumes day 1.
    """
    if not resource:
        return None
    try:
        data = orjson.loads(resource)
        birth_date_str = data.get("birthDate")
        if not birth_date_str:
            return None
        # Handle partial dates: YYYY or YYYY-MM
        if len(birth_date_str) == 4:
            return date(int(birth_date_str), 1, 1)
        if len(birth_date_str) == 7:
            parts = birth_date_str.split("-")
            return date(int(parts[0]), int(parts[1]), 1)
        return date.fromisoformat(birth_date_str)
    except (orjson.JSONDecodeError, ValueError) as e:
        _logger.warning("_extract_birthdate failed: %s", e)
    return None


def _parse_datetime(value: str) -> datetime | None:
    """Parse ISO 8601 datetime string."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as e:
        _logger.warning("_parse_datetime failed: %s", e)
        return None


def _parse_birthdate(value: str | None) -> date | None:
    if not value:
        return None
    try:
        if len(value) == 4:
            return date(int(value), 1, 1)
        if len(value) == 7:
            parts = value.split("-")
            return date(int(parts[0]), int(parts[1]), 1)
        return date.fromisoformat(value[:10])
    except (ValueError, TypeError) as e:
        _logger.warning("_parse_birthdate failed: %s", e)
    return None


def _parse_birth_datetime(value: str | None) -> datetime | None:
    """Parse a CQL Date/DateTime birth value for hour-or-finer age units."""
    if not value:
        return None
    try:
        text = value.replace("Z", "+00:00")
        if len(text) == 4:
            return datetime(int(text), 1, 1, tzinfo=timezone.utc)
        if len(text) == 7:
            year, month = text.split("-")
            return datetime(int(year), int(month), 1, tzinfo=timezone.utc)
        if "T" in text:
            parsed = datetime.fromisoformat(text)
            return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)
        parsed_date = date.fromisoformat(text[:10])
        return datetime.combine(parsed_date, time.min, tzinfo=timezone.utc)
    except (ValueError, TypeError) as e:
        _logger.warning("_parse_birth_datetime failed: %s", e)
        return None


def _reference_datetime(as_of: str | None = None) -> datetime | None:
    if as_of is None:
        return datetime.now(timezone.utc)
    try:
        text = as_of.replace("Z", "+00:00")
        if "T" in text:
            parsed = datetime.fromisoformat(text)
            return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)
        parsed_date = date.fromisoformat(text[:10])
        return datetime.combine(parsed_date, time.min, tzinfo=timezone.utc)
    except (ValueError, TypeError) as e:
        _logger.warning("_reference_datetime failed: %s", e)
        return None


def _reference_now(as_of: str | None = None) -> tuple[date, datetime] | None:
    if as_of is None:
        now = datetime.now(timezone.utc)
        return now.date(), now
    try:
        ref_date = date.fromisoformat(as_of[:10])
        ref_now = datetime.combine(ref_date, datetime.min.time()).replace(tzinfo=timezone.utc)
        return ref_date, ref_now
    except (ValueError, TypeError) as e:
        _logger.warning("_reference_now failed: %s", e)
        return None


def _calculate_age(birth_date: str | None, unit: str, as_of: str | None = None) -> int | None:
    if unit in {"hours", "minutes", "seconds"}:
        birth_dt = _parse_birth_datetime(birth_date)
        ref_dt = _reference_datetime(as_of)
        if birth_dt is None or ref_dt is None or ref_dt < birth_dt:
            return None
        delta_seconds = (ref_dt - birth_dt).total_seconds()
        divisor = {"hours": 3600, "minutes": 60, "seconds": 1}[unit]
        return int(delta_seconds // divisor)

    birth = _parse_birthdate(birth_date)
    ref = _reference_now(as_of)
    if birth is None or ref is None:
        return None
    ref_date, ref_now = ref
    if ref_date < birth:
        return None
    if unit == "years":
        return _calc_years(birth, ref_date, ref_now)
    if unit == "months":
        return _calc_months(birth, ref_date, ref_now)
    if unit == "weeks":
        return (ref_date - birth).days // 7
    if unit == "days":
        return _calc_days(birth, ref_date, ref_now)
    if unit == "hours":
        return _calc_hours(birth, ref_date, ref_now)
    if unit == "minutes":
        return _calc_minutes(birth, ref_date, ref_now)
    if unit == "seconds":
        return _calc_seconds(birth, ref_date, ref_now)
    return None


def _calculate_age_at(birth_date: str | None, unit: str, as_of: str | None) -> int | None:
    """Calculate age at an explicit reference date.

    The CQL CalculateAgeIn*At functions require both operands.  A NULL
    reference date propagates to NULL instead of silently using the current
    date/time.
    """
    if birth_date is None or as_of is None:
        return None
    return _calculate_age(birth_date, unit, as_of)


# ========================================
# Scalar versions (fallback)
# ========================================

def ageInYears_scalar(resource: str | None) -> int | None:
    """CQL AgeInYears() - scalar version."""
    birth = _extract_birthdate(resource)
    if not birth:
        return None
    today = datetime.now(timezone.utc).date()
    age = _calc_years(birth, today, datetime.now(timezone.utc))
    return age if age >= 0 else None


def ageInMonths_scalar(resource: str | None) -> int | None:
    """CQL AgeInMonths() - scalar version."""
    birth = _extract_birthdate(resource)
    if not birth:
        return None
    today = datetime.now(timezone.utc).date()
    months = _calc_months(birth, today, datetime.now(timezone.utc))
    return months


def ageInDays_scalar(resource: str | None) -> int | None:
    """CQL AgeInDays() - scalar version."""
    birth = _extract_birthdate(resource)
    if not birth:
        return None
    today = datetime.now(timezone.utc).date()
    return (today - birth).days


def ageInHours_scalar(resource: str | None) -> int | None:
    """CQL AgeInHours() - scalar version (approximate)."""
    birth = _extract_birthdate(resource)
    if not birth:
        return None
    now = datetime.now(timezone.utc)
    delta = now - datetime.combine(birth, datetime.min.time()).replace(tzinfo=timezone.utc)
    return int(delta.total_seconds() // 3600)


def ageInMinutes_scalar(resource: str | None) -> int | None:
    """CQL AgeInMinutes() - scalar version."""
    birth = _extract_birthdate(resource)
    if not birth:
        return None
    now = datetime.now(timezone.utc)
    delta = now - datetime.combine(birth, datetime.min.time()).replace(tzinfo=timezone.utc)
    return int(delta.total_seconds() // 60)


def ageInSeconds_scalar(resource: str | None) -> int | None:
    """CQL AgeInSeconds() - scalar version."""
    birth = _extract_birthdate(resource)
    if not birth:
        return None
    now = datetime.now(timezone.utc)
    delta = now - datetime.combine(birth, datetime.min.time()).replace(tzinfo=timezone.utc)
    return int(delta.total_seconds())


def ageInYearsAt_scalar(resource: str | None, as_of: str) -> int | None:
    """CQL AgeInYearsAt(date) - scalar version."""
    birth = _extract_birthdate(resource)
    if not birth or not as_of:
        return None
    try:
        as_of_date = date.fromisoformat(as_of[:10])
    except (ValueError, TypeError) as e:
        _logger.warning("UDF ageInYearsAt failed to parse date: %s", e)
        return None
    age = _calc_years(
        birth,
        as_of_date,
        datetime.combine(as_of_date, time.min, tzinfo=timezone.utc),
    )
    return age if age >= 0 else None


def ageInMonthsAt_scalar(resource: str | None, as_of: str) -> int | None:
    """CQL AgeInMonthsAt(date) - scalar version."""
    birth = _extract_birthdate(resource)
    if not birth or not as_of:
        return None
    try:
        as_of_date = date.fromisoformat(as_of[:10])
    except (ValueError, TypeError) as e:
        _logger.warning("UDF ageInMonthsAt failed to parse date: %s", e)
        return None
    months = _calc_months(
        birth,
        as_of_date,
        datetime.combine(as_of_date, time.min, tzinfo=timezone.utc),
    )
    return months if months >= 0 else None


def ageInDaysAt_scalar(resource: str | None, as_of: str) -> int | None:
    """CQL AgeInDaysAt(date) - scalar version."""
    birth = _extract_birthdate(resource)
    if not birth or not as_of:
        return None
    try:
        as_of_date = date.fromisoformat(as_of[:10])
    except (ValueError, TypeError) as e:
        _logger.warning("UDF ageInDaysAt failed to parse date: %s", e)
        return None
    days = (as_of_date - birth).days
    return days if days >= 0 else None


def ageInWeeks_scalar(resource: str | None) -> int | None:
    """CQL AgeInWeeks() - scalar version."""
    birth = _extract_birthdate(resource)
    if not birth:
        return None
    today = datetime.now(timezone.utc).date()
    return (today - birth).days // 7


def ageInWeeksAt_scalar(resource: str | None, as_of: str) -> int | None:
    """CQL AgeInWeeksAt(date) - scalar version."""
    birth = _extract_birthdate(resource)
    ref = _reference_now(as_of)
    if not birth or ref is None:
        return None
    days = (ref[0] - birth).days
    return days // 7 if days >= 0 else None


def ageInHoursAt_scalar(resource: str | None, as_of: str) -> int | None:
    birth = _extract_birthdate(resource)
    ref_dt = _reference_datetime(as_of)
    if not birth or ref_dt is None:
        return None
    birth_dt = datetime.combine(birth, time.min, tzinfo=timezone.utc)
    if ref_dt < birth_dt:
        return None
    return int((ref_dt - birth_dt).total_seconds() // 3600)


def ageInMinutesAt_scalar(resource: str | None, as_of: str) -> int | None:
    birth = _extract_birthdate(resource)
    ref_dt = _reference_datetime(as_of)
    if not birth or ref_dt is None:
        return None
    birth_dt = datetime.combine(birth, time.min, tzinfo=timezone.utc)
    if ref_dt < birth_dt:
        return None
    return int((ref_dt - birth_dt).total_seconds() // 60)


def ageInSecondsAt_scalar(resource: str | None, as_of: str) -> int | None:
    birth = _extract_birthdate(resource)
    ref_dt = _reference_datetime(as_of)
    if not birth or ref_dt is None:
        return None
    birth_dt = datetime.combine(birth, time.min, tzinfo=timezone.utc)
    if ref_dt < birth_dt:
        return None
    return int((ref_dt - birth_dt).total_seconds())


def calculateAgeInYears(birth_date: str | None) -> int | None:
    return _calculate_age(birth_date, "years")


def calculateAgeInMonths(birth_date: str | None) -> int | None:
    return _calculate_age(birth_date, "months")


def calculateAgeInWeeks(birth_date: str | None) -> int | None:
    return _calculate_age(birth_date, "weeks")


def calculateAgeInDays(birth_date: str | None) -> int | None:
    return _calculate_age(birth_date, "days")


def calculateAgeInHours(birth_date: str | None) -> int | None:
    return _calculate_age(birth_date, "hours")


def calculateAgeInMinutes(birth_date: str | None) -> int | None:
    return _calculate_age(birth_date, "minutes")


def calculateAgeInSeconds(birth_date: str | None) -> int | None:
    return _calculate_age(birth_date, "seconds")


def calculateAgeInYearsAt(birth_date: str | None, as_of: str | None) -> int | None:
    return _calculate_age_at(birth_date, "years", as_of)


def calculateAgeInMonthsAt(birth_date: str | None, as_of: str | None) -> int | None:
    return _calculate_age_at(birth_date, "months", as_of)


def calculateAgeInWeeksAt(birth_date: str | None, as_of: str | None) -> int | None:
    return _calculate_age_at(birth_date, "weeks", as_of)


def calculateAgeInDaysAt(birth_date: str | None, as_of: str | None) -> int | None:
    return _calculate_age_at(birth_date, "days", as_of)


def calculateAgeInHoursAt(birth_date: str | None, as_of: str | None) -> int | None:
    return _calculate_age_at(birth_date, "hours", as_of)


def calculateAgeInMinutesAt(birth_date: str | None, as_of: str | None) -> int | None:
    return _calculate_age_at(birth_date, "minutes", as_of)


def calculateAgeInSecondsAt(birth_date: str | None, as_of: str | None) -> int | None:
    return _calculate_age_at(birth_date, "seconds", as_of)


# ========================================
# Arrow vectorized versions (factory-based)
# ========================================

def _arrow_scalar_as_py(scalar: pa.Scalar) -> Any:
    """Convert an Arrow scalar to a Python value without batch materialization."""
    return scalar.as_py() if scalar.is_valid else None


def _days_in_month(year: int, month: int) -> int:
    return calendar.monthrange(year, month)[1]


def _add_calendar_months(value: date, months: int) -> date:
    month_index = value.year * 12 + (value.month - 1) + months
    year, month_zero = divmod(month_index, 12)
    month = month_zero + 1
    day = min(value.day, _days_in_month(year, month))
    return date(year, month, day)


def _calc_years(birth: date, ref_date: date, ref_now: datetime) -> int:
    age = ref_date.year - birth.year
    if _add_calendar_months(birth, age * 12) > ref_date:
        age -= 1
    return age


def _calc_months(birth: date, ref_date: date, ref_now: datetime) -> int:
    months = (ref_date.year - birth.year) * 12 + (ref_date.month - birth.month)
    if _add_calendar_months(birth, months) > ref_date:
        months -= 1
    return months


def _calc_days(birth: date, ref_date: date, ref_now: datetime) -> int:
    return (ref_date - birth).days


def _calc_total_seconds_divisor(divisor: float) -> Callable[[date, date, datetime], int]:
    """Factory for hours/minutes/seconds calculators."""
    def calc(birth: date, ref_date: date, ref_now: datetime) -> int:
        delta = ref_now - datetime.combine(birth, datetime.min.time()).replace(tzinfo=timezone.utc)
        return int(delta.total_seconds() / divisor)
    return calc


_calc_hours = _calc_total_seconds_divisor(3600)
_calc_minutes = _calc_total_seconds_divisor(60)
_calc_seconds = _calc_total_seconds_divisor(1)


def _make_age_arrow_udf(unit_name: str, calc_fn: Callable[[date, date, datetime], int]):
    """Factory for age calculation Arrow UDFs."""
    def age_arrow(resources: pa.StringArray) -> pa.Int64Array:
        now = datetime.now(timezone.utc)
        today = now.date()
        ages = []

        for resource_scalar in resources:
            resource = _arrow_scalar_as_py(resource_scalar)
            if resource is None:
                ages.append(None)
                continue

            birth = _extract_birthdate(resource)
            if birth is None:
                ages.append(None)
                continue

            try:
                ages.append(calc_fn(birth, today, now))
            except (ValueError, TypeError, ArithmeticError, OverflowError) as e:
                _logger.warning("UDF AgeIn%s_arrow failed for resource: %s", unit_name, e)
                ages.append(None)

        return pa.array(ages, type=pa.int64())

    age_arrow.__doc__ = f"CQL AgeIn{unit_name}() - vectorized Arrow version."
    age_arrow.__name__ = f"ageIn{unit_name}_arrow"
    return age_arrow


ageInYears_arrow = _make_age_arrow_udf("Years", _calc_years)
ageInMonths_arrow = _make_age_arrow_udf("Months", _calc_months)
ageInDays_arrow = _make_age_arrow_udf("Days", _calc_days)
ageInHours_arrow = _make_age_arrow_udf("Hours", _calc_hours)
ageInMinutes_arrow = _make_age_arrow_udf("Minutes", _calc_minutes)
ageInSeconds_arrow = _make_age_arrow_udf("Seconds", _calc_seconds)


# ========================================
# Registration with feature flag
# ========================================

def registerAgeUdfs(con: "duckdb.DuckDBPyConnection") -> None:
    """Register age UDFs with Arrow or scalar based on feature flag."""
    if _USE_ARROW:
        # Register Arrow versions with proper casing - explicit return type required
        # null_handling="special" needed because Arrow functions handle NULL values internally
        con.create_function("AgeInYears", ageInYears_arrow, type="arrow", return_type="BIGINT", null_handling="special")
        con.create_function("AgeInMonths", ageInMonths_arrow, type="arrow", return_type="BIGINT", null_handling="special")
        con.create_function("AgeInDays", ageInDays_arrow, type="arrow", return_type="BIGINT", null_handling="special")
        con.create_function("AgeInWeeks", ageInWeeks_scalar, null_handling="special")
        con.create_function("AgeInHours", ageInHours_arrow, type="arrow", return_type="BIGINT", null_handling="special")
        con.create_function("AgeInMinutes", ageInMinutes_arrow, type="arrow", return_type="BIGINT", null_handling="special")
        con.create_function("AgeInSeconds", ageInSeconds_arrow, type="arrow", return_type="BIGINT", null_handling="special")
    else:
        # Scalar only
        con.create_function("AgeInYears", ageInYears_scalar, null_handling="special")
        con.create_function("AgeInMonths", ageInMonths_scalar, null_handling="special")
        con.create_function("AgeInDays", ageInDays_scalar, null_handling="special")
        con.create_function("AgeInWeeks", ageInWeeks_scalar, null_handling="special")
        con.create_function("AgeInHours", ageInHours_scalar, null_handling="special")
        con.create_function("AgeInMinutes", ageInMinutes_scalar, null_handling="special")
        con.create_function("AgeInSeconds", ageInSeconds_scalar, null_handling="special")

    # At-time functions (scalar only for now)
    con.create_function("AgeInYearsAt", ageInYearsAt_scalar, null_handling="special")
    con.create_function("AgeInMonthsAt", ageInMonthsAt_scalar, null_handling="special")
    con.create_function("AgeInWeeksAt", ageInWeeksAt_scalar, null_handling="special")
    con.create_function("AgeInDaysAt", ageInDaysAt_scalar, null_handling="special")
    con.create_function("AgeInHoursAt", ageInHoursAt_scalar, null_handling="special")
    con.create_function("AgeInMinutesAt", ageInMinutesAt_scalar, null_handling="special")
    con.create_function("AgeInSecondsAt", ageInSecondsAt_scalar, null_handling="special")
    con.create_function("CalculateAgeInYears", calculateAgeInYears, null_handling="special")
    con.create_function("CalculateAgeInMonths", calculateAgeInMonths, null_handling="special")
    con.create_function("CalculateAgeInWeeks", calculateAgeInWeeks, null_handling="special")
    con.create_function("CalculateAgeInDays", calculateAgeInDays, null_handling="special")
    con.create_function("CalculateAgeInHours", calculateAgeInHours, null_handling="special")
    con.create_function("CalculateAgeInMinutes", calculateAgeInMinutes, null_handling="special")
    con.create_function("CalculateAgeInSeconds", calculateAgeInSeconds, null_handling="special")
    con.create_function("CalculateAgeInYearsAt", calculateAgeInYearsAt, null_handling="special")
    con.create_function("CalculateAgeInMonthsAt", calculateAgeInMonthsAt, null_handling="special")
    con.create_function("CalculateAgeInWeeksAt", calculateAgeInWeeksAt, null_handling="special")
    con.create_function("CalculateAgeInDaysAt", calculateAgeInDaysAt, null_handling="special")
    con.create_function("CalculateAgeInHoursAt", calculateAgeInHoursAt, null_handling="special")
    con.create_function("CalculateAgeInMinutesAt", calculateAgeInMinutesAt, null_handling="special")
    con.create_function("CalculateAgeInSecondsAt", calculateAgeInSecondsAt, null_handling="special")


# Legacy aliases for backward compatibility
ageInYears = ageInYears_scalar
ageInMonths = ageInMonths_scalar
ageInDays = ageInDays_scalar
ageInHours = ageInHours_scalar
ageInMinutes = ageInMinutes_scalar
ageInSeconds = ageInSeconds_scalar
ageInYearsAt = ageInYearsAt_scalar
ageInMonthsAt = ageInMonthsAt_scalar
ageInDaysAt = ageInDaysAt_scalar


__all__ = [
    # Feature flag
    "_USE_ARROW",
    # Registration
    "registerAgeUdfs",
    # Scalar functions
    "ageInYears_scalar",
    "ageInMonths_scalar",
    "ageInDays_scalar",
    "ageInHours_scalar",
    "ageInMinutes_scalar",
    "ageInSeconds_scalar",
    "ageInYearsAt_scalar",
    "ageInMonthsAt_scalar",
    "ageInDaysAt_scalar",
    # Arrow functions
    "ageInYears_arrow",
    "ageInMonths_arrow",
    "ageInDays_arrow",
    "ageInHours_arrow",
    "ageInMinutes_arrow",
    "ageInSeconds_arrow",
    # Legacy aliases
    "ageInYears",
    "ageInMonths",
    "ageInDays",
    "ageInHours",
    "ageInMinutes",
    "ageInSeconds",
    "ageInYearsAt",
    "ageInMonthsAt",
    "ageInDaysAt",
]
