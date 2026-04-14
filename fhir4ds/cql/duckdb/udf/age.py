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
from datetime import date, datetime, timezone
from typing import TYPE_CHECKING, Any, Callable

import orjson
import pyarrow as pa

if TYPE_CHECKING:
    import duckdb


import logging

_logger = logging.getLogger(__name__)
# Feature flag for rollback
_USE_ARROW = os.environ.get("CQL_USE_ARROW_UDFS", "1") == "1"


def _extract_birthdate(resource: str) -> date | None:
    """Extract birthDate from a FHIR Patient resource."""
    if not resource:
        return None
    try:
        data = orjson.loads(resource)
        birth_date_str = data.get("birthDate")
        if birth_date_str:
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


# ========================================
# Scalar versions (fallback)
# ========================================

def ageInYears_scalar(resource: str | None) -> int | None:
    """CQL AgeInYears() - scalar version."""
    birth = _extract_birthdate(resource)
    if not birth:
        return None
    today = datetime.now(timezone.utc).date()
    age = today.year - birth.year
    if (today.month, today.day) < (birth.month, birth.day):
        age -= 1
    return age


def ageInMonths_scalar(resource: str | None) -> int | None:
    """CQL AgeInMonths() - scalar version."""
    birth = _extract_birthdate(resource)
    if not birth:
        return None
    today = datetime.now(timezone.utc).date()
    months = (today.year - birth.year) * 12 + (today.month - birth.month)
    if today.day < birth.day:
        months -= 1
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
    age = as_of_date.year - birth.year
    if (as_of_date.month, as_of_date.day) < (birth.month, birth.day):
        age -= 1
    return max(0, age)


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
    months = (as_of_date.year - birth.year) * 12 + (as_of_date.month - birth.month)
    if as_of_date.day < birth.day:
        months -= 1
    return max(0, months)


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
    return max(0, (as_of_date - birth).days)


# ========================================
# Arrow vectorized versions (factory-based)
# ========================================

def _arrow_scalar_as_py(scalar: pa.Scalar) -> Any:
    """Convert an Arrow scalar to a Python value without batch materialization."""
    return scalar.as_py() if scalar.is_valid else None


def _calc_years(birth: date, ref_date: date, ref_now: datetime) -> int:
    age = ref_date.year - birth.year
    if (ref_date.month, ref_date.day) < (birth.month, birth.day):
        age -= 1
    return age


def _calc_months(birth: date, ref_date: date, ref_now: datetime) -> int:
    months = (ref_date.year - birth.year) * 12 + (ref_date.month - birth.month)
    if ref_date.day < birth.day:
        months -= 1
    return months


def _calc_days(birth: date, ref_date: date, ref_now: datetime) -> int:
    return (ref_date - birth).days


def _calc_total_seconds_divisor(divisor: float) -> Callable[[date, date, datetime], int]:
    """Factory for hours/minutes/seconds calculators."""
    def calc(birth: date, ref_date: date, ref_now: datetime) -> int:
        delta = ref_now - datetime.combine(birth, datetime.min.time()).replace(tzinfo=timezone.utc)
        return int(delta.total_seconds() // divisor)
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
        con.create_function("AgeInHours", ageInHours_arrow, type="arrow", return_type="BIGINT", null_handling="special")
        con.create_function("AgeInMinutes", ageInMinutes_arrow, type="arrow", return_type="BIGINT", null_handling="special")
        con.create_function("AgeInSeconds", ageInSeconds_arrow, type="arrow", return_type="BIGINT", null_handling="special")
    else:
        # Scalar only
        con.create_function("AgeInYears", ageInYears_scalar, null_handling="special")
        con.create_function("AgeInMonths", ageInMonths_scalar, null_handling="special")
        con.create_function("AgeInDays", ageInDays_scalar, null_handling="special")
        con.create_function("AgeInHours", ageInHours_scalar, null_handling="special")
        con.create_function("AgeInMinutes", ageInMinutes_scalar, null_handling="special")
        con.create_function("AgeInSeconds", ageInSeconds_scalar, null_handling="special")

    # At-time functions (scalar only for now)
    con.create_function("AgeInYearsAt", ageInYearsAt_scalar, null_handling="special")
    con.create_function("AgeInMonthsAt", ageInMonthsAt_scalar, null_handling="special")
    con.create_function("AgeInDaysAt", ageInDaysAt_scalar, null_handling="special")


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
