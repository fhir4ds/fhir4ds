"""
Vectorized CQL Age Calculation UDFs

Implements all CQL age calculation functions (CQL 1.5 Appendix B, Clinical
Operators — Age, AgeAt, CalculateAge, CalculateAgeAt):

- AgeInYears(), AgeInMonths(), AgeInWeeks(), AgeInDays(),
  AgeInHours(), AgeInMinutes(), AgeInSeconds()
- AgeInYearsAt(asOf), ..., AgeInSecondsAt(asOf)
- CalculateAgeInYears(birthDate), ..., CalculateAgeInSeconds(birthDate)
- CalculateAgeInYearsAt(birthDate, asOf), ..., CalculateAgeInSecondsAt(birthDate, asOf)

Per the spec, every age operator is *defined in terms of a duration
calculation*: when the birthDate (or asOf) is specified below the precision
of the operator, the result is an uncertainty over the range of possible
values. All functions therefore delegate to the §22.21 duration engine and
return VARCHAR: an integer string when the result is certain, or a closed
interval JSON string ({"start":..,"end":..}) when uncertain.

Supports both scalar (row-by-row) and Arrow vectorized implementations.
"""

from __future__ import annotations

import os
from datetime import date, datetime, timezone
from typing import TYPE_CHECKING, Callable

import orjson
import pyarrow as pa

from .datetime import _duration_between_with_uncertainty

if TYPE_CHECKING:
    import duckdb


import logging

_logger = logging.getLogger(__name__)
# Feature flag for rollback
_USE_ARROW = os.environ.get("CQL_USE_ARROW_UDFS", "1") == "1"


_AGE_UNITS = ("years", "months", "weeks", "days", "hours", "minutes", "seconds")


def _age_unit_key(unit: str) -> str:
    normalized = unit.strip().lower()
    if normalized.endswith("s"):
        normalized = normalized[:-1]
    return normalized  # 'year' | 'month' | 'week' | 'day' | 'hour' | 'minute' | 'second'


def _age_current_reference(unit_key: str) -> str:
    """CQL §Age: AgeInYears/AgeInMonths use Today(); finer precisions use Now()."""
    now = datetime.now(timezone.utc)
    if unit_key in ("hour", "minute", "second", "millisecond"):
        return now.strftime("%Y-%m-%dT%H:%M:%S")
    return now.date().isoformat()


def _age_with_uncertainty(birth_text: str | None, unit: str, as_of_text: str | None) -> str | None:
    """CQL §Age/§CalculateAgeAt semantics via the §22.21 duration engine.

    Returns an integer string when the age is certain, a closed-interval
    JSON string when the birthDate/asOf precision is below the requested
    unit, or None for null inputs / unparseable values. A definitive
    negative age (asOf before birthDate at full precision) is clinically
    invalid and returns None; uncertain intervals spanning negative values
    are surfaced per spec.
    """
    if birth_text is None or as_of_text is None:
        return None
    try:
        result = _duration_between_with_uncertainty(str(birth_text), str(as_of_text), unit)
    except (ValueError, TypeError, OverflowError) as e:
        _logger.warning("_age_with_uncertainty failed: %s", e)
        return None
    if result is None:
        return None
    if result.lstrip("-").isdigit() and int(result) < 0:
        return None
    return result


def _extract_birthdate_text(resource: str | None) -> str | None:
    """Raw Patient.birthDate text (may be partial: 'YYYY' or 'YYYY-MM')."""
    if not resource:
        return None
    try:
        data = orjson.loads(resource)
        value = data.get("birthDate")
        return str(value) if value else None
    except (orjson.JSONDecodeError, ValueError) as e:
        _logger.warning("_extract_birthdate_text failed: %s", e)
        return None


# ========================================
# Scalar versions (fallback)
# ========================================

def _make_age_scalar(unit: str) -> Callable[[str | None], str | None]:
    unit_key = _age_unit_key(unit)

    def age_scalar(resource: str | None) -> str | None:
        return _age_with_uncertainty(
            _extract_birthdate_text(resource), unit_key, _age_current_reference(unit_key)
        )

    age_scalar.__doc__ = f"CQL AgeIn{unit.title().replace('In', 'In')}() - scalar version."
    age_scalar.__name__ = f"ageIn{unit[:-1].title() if False else unit.capitalize()}_scalar"
    return age_scalar


def _make_age_at_scalar(unit: str) -> Callable[[str | None, str], str | None]:
    unit_key = _age_unit_key(unit)

    def age_at_scalar(resource: str | None, as_of: str) -> str | None:
        if as_of is None:
            return None
        return _age_with_uncertainty(_extract_birthdate_text(resource), unit_key, str(as_of))

    age_at_scalar.__doc__ = f"CQL AgeIn{unit.title()}At(asOf) - scalar version."
    age_at_scalar.__name__ = f"ageIn{unit.capitalize()}At_scalar"
    return age_at_scalar


def _make_calculate_age(unit: str) -> Callable[[str | None], str | None]:
    unit_key = _age_unit_key(unit)

    def calculate_age(birth_date: str | None) -> str | None:
        return _age_with_uncertainty(birth_date, unit_key, _age_current_reference(unit_key))

    calculate_age.__doc__ = f"CQL CalculateAgeIn{unit.title()}(birthDate)."
    calculate_age.__name__ = f"calculateAgeIn{unit.title()}"
    return calculate_age


def _make_calculate_age_at(unit: str) -> Callable[[str | None, str | None], str | None]:
    unit_key = _age_unit_key(unit)

    def calculate_age_at(birth_date: str | None, as_of: str | None) -> str | None:
        """CQL CalculateAgeIn{unit}At — both operands required; null propagates."""
        if birth_date is None or as_of is None:
            return None
        return _age_with_uncertainty(str(birth_date), unit_key, str(as_of))

    calculate_age_at.__doc__ = f"CQL CalculateAgeIn{unit.title()}At(birthDate, asOf)."
    calculate_age_at.__name__ = f"calculateAgeIn{unit.title()}At"
    return calculate_age_at


for _unit in _AGE_UNITS:
    _title = _unit[:-1].title()  # Years -> Year
    globals()[f"ageIn{_title}s_scalar"] = _make_age_scalar(_unit)
    globals()[f"ageIn{_title}sAt_scalar"] = _make_age_at_scalar(_unit)
    globals()[f"calculateAgeIn{_title}s"] = _make_calculate_age(_unit)
    globals()[f"calculateAgeIn{_title}sAt"] = _make_calculate_age_at(_unit)


# ========================================
# Arrow vectorized versions (factory-based)
# ========================================

def _arrow_scalar_as_py(scalar: pa.Scalar):
    """Convert an Arrow scalar to a Python value without batch materialization."""
    return scalar.as_py() if scalar.is_valid else None


def _make_age_arrow_udf(unit_name: str) -> Callable:
    """Factory for age calculation Arrow UDFs (§Age uncertainty semantics)."""
    unit_key = _age_unit_key(unit_name)

    def age_arrow(resources: pa.StringArray) -> pa.Array:
        as_of = _age_current_reference(unit_key)
        ages = []
        for resource_scalar in resources:
            resource = _arrow_scalar_as_py(resource_scalar)
            if resource is None:
                ages.append(None)
                continue
            try:
                ages.append(
                    _age_with_uncertainty(_extract_birthdate_text(resource), unit_key, as_of)
                )
            except (ValueError, TypeError, ArithmeticError, OverflowError) as e:
                _logger.warning("UDF AgeIn%s_arrow failed for resource: %s", unit_name, e)
                ages.append(None)
        return pa.array(ages, type=pa.string())

    age_arrow.__doc__ = f"CQL AgeIn{unit_name}() - vectorized Arrow version."
    age_arrow.__name__ = f"ageIn{unit_name}_arrow"
    return age_arrow


ageInYears_arrow = _make_age_arrow_udf("years")
ageInMonths_arrow = _make_age_arrow_udf("months")
ageInDays_arrow = _make_age_arrow_udf("days")
ageInHours_arrow = _make_age_arrow_udf("hours")
ageInMinutes_arrow = _make_age_arrow_udf("minutes")
ageInSeconds_arrow = _make_age_arrow_udf("seconds")


# ========================================
# Registration with feature flag
# ========================================

def registerAgeUdfs(con: "duckdb.DuckDBPyConnection") -> None:
    """Register age UDFs (§Age uncertainty semantics, VARCHAR results)."""
    if _USE_ARROW:
        # Register Arrow versions - explicit return type required;
        # null_handling="special" because Arrow functions handle NULLs internally
        con.create_function("AgeInYears", ageInYears_arrow, type="arrow", return_type="VARCHAR", null_handling="special")
        con.create_function("AgeInMonths", ageInMonths_arrow, type="arrow", return_type="VARCHAR", null_handling="special")
        con.create_function("AgeInDays", ageInDays_arrow, type="arrow", return_type="VARCHAR", null_handling="special")
        con.create_function("AgeInWeeks", ageInWeeks_scalar, return_type="VARCHAR", null_handling="special")
        con.create_function("AgeInHours", ageInHours_arrow, type="arrow", return_type="VARCHAR", null_handling="special")
        con.create_function("AgeInMinutes", ageInMinutes_arrow, type="arrow", return_type="VARCHAR", null_handling="special")
        con.create_function("AgeInSeconds", ageInSeconds_arrow, type="arrow", return_type="VARCHAR", null_handling="special")
    else:
        # Scalar only
        con.create_function("AgeInYears", ageInYears_scalar, return_type="VARCHAR", null_handling="special")
        con.create_function("AgeInMonths", ageInMonths_scalar, return_type="VARCHAR", null_handling="special")
        con.create_function("AgeInDays", ageInDays_scalar, return_type="VARCHAR", null_handling="special")
        con.create_function("AgeInWeeks", ageInWeeks_scalar, return_type="VARCHAR", null_handling="special")
        con.create_function("AgeInHours", ageInHours_scalar, return_type="VARCHAR", null_handling="special")
        con.create_function("AgeInMinutes", ageInMinutes_scalar, return_type="VARCHAR", null_handling="special")
        con.create_function("AgeInSeconds", ageInSeconds_scalar, return_type="VARCHAR", null_handling="special")

    # At-time functions (scalar only for now)
    con.create_function("AgeInYearsAt", ageInYearsAt_scalar, return_type="VARCHAR", null_handling="special")
    con.create_function("AgeInMonthsAt", ageInMonthsAt_scalar, return_type="VARCHAR", null_handling="special")
    con.create_function("AgeInWeeksAt", ageInWeeksAt_scalar, return_type="VARCHAR", null_handling="special")
    con.create_function("AgeInDaysAt", ageInDaysAt_scalar, return_type="VARCHAR", null_handling="special")
    con.create_function("AgeInHoursAt", ageInHoursAt_scalar, return_type="VARCHAR", null_handling="special")
    con.create_function("AgeInMinutesAt", ageInMinutesAt_scalar, return_type="VARCHAR", null_handling="special")
    con.create_function("AgeInSecondsAt", ageInSecondsAt_scalar, return_type="VARCHAR", null_handling="special")
    con.create_function("CalculateAgeInYears", calculateAgeInYears, return_type="VARCHAR", null_handling="special")
    con.create_function("CalculateAgeInMonths", calculateAgeInMonths, return_type="VARCHAR", null_handling="special")
    con.create_function("CalculateAgeInWeeks", calculateAgeInWeeks, return_type="VARCHAR", null_handling="special")
    con.create_function("CalculateAgeInDays", calculateAgeInDays, return_type="VARCHAR", null_handling="special")
    con.create_function("CalculateAgeInHours", calculateAgeInHours, return_type="VARCHAR", null_handling="special")
    con.create_function("CalculateAgeInMinutes", calculateAgeInMinutes, return_type="VARCHAR", null_handling="special")
    con.create_function("CalculateAgeInSeconds", calculateAgeInSeconds, return_type="VARCHAR", null_handling="special")
    con.create_function("CalculateAgeInYearsAt", calculateAgeInYearsAt, return_type="VARCHAR", null_handling="special")
    con.create_function("CalculateAgeInMonthsAt", calculateAgeInMonthsAt, return_type="VARCHAR", null_handling="special")
    con.create_function("CalculateAgeInWeeksAt", calculateAgeInWeeksAt, return_type="VARCHAR", null_handling="special")
    con.create_function("CalculateAgeInDaysAt", calculateAgeInDaysAt, return_type="VARCHAR", null_handling="special")
    con.create_function("CalculateAgeInHoursAt", calculateAgeInHoursAt, return_type="VARCHAR", null_handling="special")
    con.create_function("CalculateAgeInMinutesAt", calculateAgeInMinutesAt, return_type="VARCHAR", null_handling="special")
    con.create_function("CalculateAgeInSecondsAt", calculateAgeInSecondsAt, return_type="VARCHAR", null_handling="special")


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
    "ageInWeeks_scalar",
    "ageInYearsAt_scalar",
    "ageInMonthsAt_scalar",
    "ageInWeeksAt_scalar",
    "ageInDaysAt_scalar",
    "ageInHoursAt_scalar",
    "ageInMinutesAt_scalar",
    "ageInSecondsAt_scalar",
    "calculateAgeInYears",
    "calculateAgeInMonths",
    "calculateAgeInWeeks",
    "calculateAgeInDays",
    "calculateAgeInHours",
    "calculateAgeInMinutes",
    "calculateAgeInSeconds",
    "calculateAgeInYearsAt",
    "calculateAgeInMonthsAt",
    "calculateAgeInWeeksAt",
    "calculateAgeInDaysAt",
    "calculateAgeInHoursAt",
    "calculateAgeInMinutesAt",
    "calculateAgeInSecondsAt",
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
