"""
CQL Date/Time Difference UDFs

Implements all CQL date/time difference functions:
- yearsBetween(a, b), monthsBetween(a, b), daysBetween(a, b)
- hoursBetween(a, b), minutesBetween(a, b), secondsBetween(a, b)
- millisecondsBetween(a, b)
- weeksBetween(a, b)
"""

from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING

import orjson

if TYPE_CHECKING:
    import duckdb



import calendar
import logging
from datetime import timedelta, datetime as _dt_class

_logger = logging.getLogger(__name__)

# Unit aliases for dateAddQuantity - maps unit string to (handler_type, timedelta_key)
_TIMEDELTA_UNITS: dict[str, str] = {
    "week": "weeks", "weeks": "weeks", "wk": "weeks",
    "day": "days", "days": "days", "d": "days",
    "hour": "hours", "hours": "hours", "h": "hours",
    "minute": "minutes", "minutes": "minutes", "min": "minutes",
    "second": "seconds", "seconds": "seconds", "s": "seconds",
    "millisecond": "milliseconds", "milliseconds": "milliseconds", "ms": "milliseconds",
}
_YEAR_UNITS = frozenset(("year", "years", "a"))
_MONTH_UNITS = frozenset(("month", "months", "mo"))
def _parse_date(value: str) -> date | None:
    """Parse date from ISO 8601 string."""
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError as e:
        _logger.warning("_parse_date failed: %s", e)
        return None


def _parse_time(value: str) -> "time | None":
    """Parse time from ISO 8601 / CQL time string (e.g. '15:59:59.999' or 'T15:59:59.999')."""
    from datetime import time as _time_class
    if not value:
        return None
    try:
        s = value.lstrip("T").strip()
        # Normalize fractional seconds to 6 digits for fromisoformat compatibility
        if '.' in s:
            base, frac = s.split('.', 1)
            frac = frac.ljust(6, '0')[:6]
            s = f"{base}.{frac}"
        return _time_class.fromisoformat(s)
    except (ValueError, TypeError):
        return None


def _parse_datetime(value: str) -> datetime | None:
    """Parse datetime from ISO 8601 string."""
    if not value:
        return None
    try:
        val = value.replace("Z", "+00:00")
        # Normalize partial fractional seconds (.4 → .400000) for Python 3.10 compat
        if '.' in val:
            dot_idx = val.rindex('.')
            end = dot_idx + 1
            while end < len(val) and val[end].isdigit():
                end += 1
            frac = val[dot_idx+1:end]
            frac = frac.ljust(6, '0')[:6]
            val = val[:dot_idx+1] + frac + val[end:]
        # Handle space-separated datetime
        if ' ' in val and 'T' not in val:
            val = val.replace(' ', 'T', 1)
        return datetime.fromisoformat(val)
    except ValueError as e:
        _logger.warning("_parse_datetime failed: %s", e)
        return None


def yearsBetween(start: str | None, end: str | None) -> int | None:
    """CQL years between two dates."""
    s, e = _parse_date(start), _parse_date(end)
    if not s or not e:
        return None
    years = e.year - s.year
    if (e.month, e.day) < (s.month, s.day):
        years -= 1
    return years


def monthsBetween(start: str | None, end: str | None) -> int | None:
    """CQL months between two dates."""
    s, e = _parse_date(start), _parse_date(end)
    if not s or not e:
        return None
    months = (e.year - s.year) * 12 + (e.month - s.month)
    if e.day < s.day:
        months -= 1
    return months


def weeksBetween(start: str | None, end: str | None) -> int | None:
    """CQL weeks between two dates."""
    s, e = _parse_date(start), _parse_date(end)
    if not s or not e:
        return None
    return (e - s).days // 7


def daysBetween(start: str | None, end: str | None) -> int | None:
    """CQL days between two dates."""
    s, e = _parse_date(start), _parse_date(end)
    if not s or not e:
        return None
    return (e - s).days


def hoursBetween(start: str | None, end: str | None) -> int | None:
    """CQL hours between two datetimes."""
    s, e = _parse_datetime(start), _parse_datetime(end)
    if not s or not e:
        return None
    return int((e - s).total_seconds() // 3600)


def minutesBetween(start: str | None, end: str | None) -> int | None:
    """CQL minutes between two datetimes."""
    s, e = _parse_datetime(start), _parse_datetime(end)
    if not s or not e:
        return None
    return int((e - s).total_seconds() // 60)


def secondsBetween(start: str | None, end: str | None) -> int | None:
    """CQL seconds between two datetimes."""
    s, e = _parse_datetime(start), _parse_datetime(end)
    if not s or not e:
        return None
    return int((e - s).total_seconds())


def millisecondsBetween(start: str | None, end: str | None) -> int | None:
    """CQL milliseconds between two datetimes."""
    s, e = _parse_datetime(start), _parse_datetime(end)
    if not s or not e:
        return None
    return int((e - s).total_seconds() * 1000)


# ========================================
# Now/Today/TimeOfDay Functions
# ========================================

def dateTimeNow() -> str:
    """CQL Now() - current datetime."""
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def dateTimeToday() -> str:
    """CQL Today() - current date."""
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).date().isoformat()


def dateTimeTimeOfDay() -> str:
    """CQL TimeOfDay() - current time."""
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).time().isoformat()


# ========================================
# DifferenceBetween UDFs (boundary crossings)
# ========================================

def differenceInYears(start: str | None, end: str | None) -> int | None:
    """
    Calculate difference in years (boundary crossings).

    Example: difference between 2023-12-31 and 2024-01-01 = 1
    (crossed a year boundary, even though not a full year)
    """
    if start is None or end is None:
        return None
    try:
        s = _parse_date(start)
        e = _parse_date(end)
        if not s or not e:
            return None
        return e.year - s.year
    except (ValueError, TypeError, AttributeError) as e:
        _logger.warning("UDF differenceInYears failed: %s", e)
        return None


def differenceInMonths(start: str | None, end: str | None) -> int | None:
    """Calculate difference in months (boundary crossings)."""
    if start is None or end is None:
        return None
    try:
        s = _parse_date(start)
        e = _parse_date(end)
        if not s or not e:
            return None
        return (e.year - s.year) * 12 + (e.month - s.month)
    except (ValueError, TypeError, AttributeError) as e:
        _logger.warning("UDF differenceInMonths failed: %s", e)
        return None


def differenceInDays(start: str | None, end: str | None) -> int | None:
    """Calculate difference in days (boundary crossings)."""
    if start is None or end is None:
        return None
    try:
        s = _parse_date(start)
        e = _parse_date(end)
        if not s or not e:
            return None
        return (e - s).days
    except (ValueError, TypeError, AttributeError) as e:
        _logger.warning("UDF differenceInDays failed: %s", e)
        return None


def differenceInWeeks(start: str | None, end: str | None) -> int | None:
    """Calculate difference in weeks (CQL §19.2 — boundary crossings)."""
    days = differenceInDays(start, end)
    if days is None:
        return None
    return days // 7


def differenceInHours(start: str | None, end: str | None) -> int | None:
    """Calculate difference in hours (boundary crossings)."""
    if start is None or end is None:
        return None
    try:
        s = _parse_datetime(start) or (_dt_class.combine(date(2000, 1, 1), _parse_time(start)) if _parse_time(start) else None)
        e = _parse_datetime(end) or (_dt_class.combine(date(2000, 1, 1), _parse_time(end)) if _parse_time(end) else None)
        if not s or not e:
            return None
        delta = e - s
        return int(delta.total_seconds()) // 3600
    except (ValueError, TypeError, AttributeError) as ex:
        _logger.warning("UDF differenceInHours failed: %s", ex)
        return None


def differenceInMinutes(start: str | None, end: str | None) -> int | None:
    """Calculate difference in minutes (boundary crossings)."""
    if start is None or end is None:
        return None
    try:
        s = _parse_datetime(start) or (_dt_class.combine(date(2000, 1, 1), _parse_time(start)) if _parse_time(start) else None)
        e = _parse_datetime(end) or (_dt_class.combine(date(2000, 1, 1), _parse_time(end)) if _parse_time(end) else None)
        if not s or not e:
            return None
        delta = e - s
        return int(delta.total_seconds()) // 60
    except (ValueError, TypeError, AttributeError) as ex:
        _logger.warning("UDF differenceInMinutes failed: %s", ex)
        return None


def differenceInSeconds(start: str | None, end: str | None) -> int | None:
    """Calculate difference in seconds (boundary crossings)."""
    if start is None or end is None:
        return None
    try:
        s = _parse_datetime(start) or (_dt_class.combine(date(2000, 1, 1), _parse_time(start)) if _parse_time(start) else None)
        e = _parse_datetime(end) or (_dt_class.combine(date(2000, 1, 1), _parse_time(end)) if _parse_time(end) else None)
        if not s or not e:
            return None
        delta = e - s
        return int(delta.total_seconds())
    except (ValueError, TypeError, AttributeError) as ex:
        _logger.warning("UDF differenceInSeconds failed: %s", ex)
        return None


def differenceInMilliseconds(start: str | None, end: str | None) -> int | None:
    """Calculate difference in milliseconds (boundary crossings)."""
    if start is None or end is None:
        return None
    try:
        s = _parse_datetime(start) or (_dt_class.combine(date(2000, 1, 1), _parse_time(start)) if _parse_time(start) else None)
        e = _parse_datetime(end) or (_dt_class.combine(date(2000, 1, 1), _parse_time(end)) if _parse_time(end) else None)
        if not s or not e:
            return None
        delta = e - s
        return int(delta.total_seconds() * 1000)
    except (ValueError, TypeError, AttributeError) as ex:
        _logger.warning("UDF differenceInMilliseconds failed: %s", ex)
        return None


def dateComponent(value: str | None, component: str) -> int | None:
    """
    Extract a date/time component.

    Args:
        value: ISO date/datetime string
        component: 'year', 'month', 'day', 'hour', 'minute', 'second'

    Returns:
        Integer component value or None if invalid
    """
    if value is None:
        return None
    try:
        dt = _parse_datetime(value)
        if not dt:
            dt = _parse_date(value)
            if not dt:
                return None
            # It's a date, only year/month/day available
            component_map = {
                'year': dt.year,
                'month': dt.month,
                'day': dt.day,
            }
        else:
            component_map = {
                'year': dt.year,
                'month': dt.month,
                'day': dt.day,
                'hour': dt.hour,
                'minute': dt.minute,
                'second': dt.second,
                'millisecond': dt.microsecond // 1000,
            }
        return component_map.get(component.lower())
    except (ValueError, TypeError, AttributeError, KeyError) as e:
        _logger.warning("UDF dateComponent failed: %s", e)
        return None


# ========================================
# DateTime Comparison UDFs (SameAs, SameOrBefore, SameOrAfter)
# ========================================

def dateTimeSameAs(a: str | None, b: str | None, precision: str | None = None) -> bool | None:
    """
    Check if two datetimes are the same at the specified precision.

    Args:
        a: First datetime (ISO format)
        b: Second datetime (ISO format)
        precision: Comparison precision ('year', 'month', 'day', 'hour', 'minute', 'second', 'millisecond')

    Returns:
        True if same at precision, False if not, None if either is null
    """
    if a is None or b is None:
        return None

    dt_a = _parse_datetime(a) or _parse_date(a)
    dt_b = _parse_datetime(b) or _parse_date(b)

    if dt_a is None or dt_b is None:
        return None

    precision_map = {
        'year': ['year'],
        'month': ['year', 'month'],
        'day': ['year', 'month', 'day'],
        'hour': ['year', 'month', 'day', 'hour'],
        'minute': ['year', 'month', 'day', 'hour', 'minute'],
        'second': ['year', 'month', 'day', 'hour', 'minute', 'second'],
        'millisecond': ['year', 'month', 'day', 'hour', 'minute', 'second', 'microsecond'],
    }

    fields = precision_map.get(precision.lower() if precision else 'day', ['year', 'month', 'day'])

    for field in fields:
        if getattr(dt_a, field, None) != getattr(dt_b, field, None):
            return False

    return True


def dateTimeSameOrBefore(a: str | None, b: str | None, precision: str | None = None) -> bool | None:
    """
    Check if A is the same as or before B at the specified precision.
    A same or before B means: A <= B (at precision)
    """
    if a is None or b is None:
        return None

    dt_a = _parse_datetime(a) or _parse_date(a)
    dt_b = _parse_datetime(b) or _parse_date(b)

    if dt_a is None or dt_b is None:
        return None

    precision_order = ['year', 'month', 'day', 'hour', 'minute', 'second', 'microsecond']
    target_precision = precision.lower() if precision else 'day'

    if target_precision in precision_order:
        idx = precision_order.index(target_precision)
        for i, field in enumerate(precision_order[:idx + 1]):
            a_val = getattr(dt_a, field, None)
            b_val = getattr(dt_b, field, None)
            if a_val is not None and b_val is not None:
                if a_val < b_val:
                    return True
                if a_val > b_val:
                    return False

    return True


def dateTimeSameOrAfter(a: str | None, b: str | None, precision: str | None = None) -> bool | None:
    """
    Check if A is the same as or after B at the specified precision.
    A same or after B means: A >= B (at precision)
    """
    if a is None or b is None:
        return None

    dt_a = _parse_datetime(a) or _parse_date(a)
    dt_b = _parse_datetime(b) or _parse_date(b)

    if dt_a is None or dt_b is None:
        return None

    precision_order = ['year', 'month', 'day', 'hour', 'minute', 'second', 'microsecond']
    target_precision = precision.lower() if precision else 'day'

    if target_precision in precision_order:
        idx = precision_order.index(target_precision)
        for i, field in enumerate(precision_order[:idx + 1]):
            a_val = getattr(dt_a, field, None)
            b_val = getattr(dt_b, field, None)
            if a_val is not None and b_val is not None:
                if a_val > b_val:
                    return True
                if a_val < b_val:
                    return False

    return True


# ========================================
# Quantity to Interval Conversion
# ========================================

# Mapping from UCUM time units to DuckDB INTERVAL components
UCUM_TIME_UNITS = {
    "year": ("year", "years"),
    "years": ("year", "years"),
    "a": ("year", "years"),  # UCUM for year
    "month": ("month", "months"),
    "months": ("month", "months"),
    "mo": ("month", "months"),  # UCUM for month
    "week": ("day", "days"),  # Weeks converted to days (7 days per week)
    "weeks": ("day", "days"),
    "wk": ("day", "days"),  # UCUM for week
    "day": ("day", "days"),
    "days": ("day", "days"),
    "d": ("day", "days"),  # UCUM for day
    "hour": ("hour", "hours"),
    "hours": ("hour", "hours"),
    "h": ("hour", "hours"),  # UCUM for hour
    "minute": ("minute", "minutes"),
    "minutes": ("minute", "minutes"),
    "min": ("minute", "minutes"),  # UCUM for minute
    "second": ("second", "seconds"),
    "seconds": ("second", "seconds"),
    "s": ("second", "seconds"),  # UCUM for second
    "millisecond": ("millisecond", "milliseconds"),
    "milliseconds": ("millisecond", "milliseconds"),
    "ms": ("millisecond", "milliseconds"),  # UCUM for millisecond
}


def quantityToInterval(quantity_json: str | None) -> str | None:
    """
    Convert a FHIR Quantity to a DuckDB INTERVAL expression string.

    This function extracts the value and unit from a quantity JSON and
    returns a string that can be used with DuckDB's date arithmetic.

    Args:
        quantity_json: JSON string representing a FHIR Quantity

    Returns:
        A string like "INTERVAL 6 MONTH" or None if invalid
    """
    if quantity_json is None:
        return None

    try:
        import orjson
        data = orjson.loads(quantity_json)
        value = data.get("value")
        unit = data.get("unit") or data.get("code")

        if value is None or unit is None:
            return None

        # Normalize unit to lowercase for lookup
        unit_lower = unit.lower()

        if unit_lower not in UCUM_TIME_UNITS:
            # Not a time unit - can't convert to interval
            return None

        # Get singular/plural forms
        singular, plural = UCUM_TIME_UNITS[unit_lower]

        # DuckDB INTERVAL syntax uses the plural form for values > 1
        interval_unit = plural if abs(float(value)) != 1 else singular

        # Special handling for weeks (convert to days since DuckDB doesn't have WEEK interval)
        if unit_lower in ("week", "weeks", "wk"):
            value = float(value) * 7
            interval_unit = "days" if abs(value) != 1 else "day"

        # Return the INTERVAL expression as a string
        # The caller will use this in date arithmetic
        return f"INTERVAL {int(value)} {interval_unit.upper()}"
    except (orjson.JSONDecodeError, ValueError, TypeError, KeyError) as e:
        _logger.warning("UDF quantityToInterval failed: %s", e)
        return None


def dateAddQuantity(date_val: str | None, quantity_json: str | None) -> str | None:
    """
    Add a quantity to a date/datetime.

    Args:
        date_val: ISO date/datetime string
        quantity_json: JSON string representing a FHIR Quantity with time unit

    Returns:
        Resulting date/datetime as ISO string, or None if invalid
    """
    if date_val is None or quantity_json is None:
        return None

    try:
        data = orjson.loads(quantity_json)
        value = data.get("value")
        unit = data.get("unit") or data.get("code")

        if value is None or unit is None:
            return None

        value = float(value)
        unit_lower = unit.lower()

        # Try time-only value first (e.g. '15:59:59.999')
        t = _parse_time(date_val)
        if t is not None:
            # Anchor to a reference date for arithmetic, then extract time
            from datetime import time as _time_class
            ref_dt = _dt_class(2000, 1, 1, t.hour, t.minute, t.second, t.microsecond)
            if unit_lower in _TIMEDELTA_UNITS:
                result_dt = ref_dt + timedelta(**{_TIMEDELTA_UNITS[unit_lower]: value})
                result_time = result_dt.time()
                # Format as CQL Time string with milliseconds
                ms = result_time.microsecond // 1000
                return f"T{result_time.hour:02d}:{result_time.minute:02d}:{result_time.second:02d}.{ms:03d}"
            return None

        dt = _parse_datetime(date_val)
        if dt is None:
            dt = _parse_date(date_val)
            if dt is None:
                return None
            dt = _dt_class.combine(dt, _dt_class.min.time())

        if unit_lower in _YEAR_UNITS:
            target_year = dt.year + int(value)
            max_day = calendar.monthrange(target_year, dt.month)[1]
            result = dt.replace(year=target_year, day=min(dt.day, max_day))
        elif unit_lower in _MONTH_UNITS:
            new_month = dt.month + int(value)
            new_year = dt.year + (new_month - 1) // 12
            new_month = ((new_month - 1) % 12) + 1
            max_day = calendar.monthrange(new_year, new_month)[1]
            result = dt.replace(year=new_year, month=new_month, day=min(dt.day, max_day))
        elif unit_lower in _TIMEDELTA_UNITS:
            result = dt + timedelta(**{_TIMEDELTA_UNITS[unit_lower]: value})
        else:
            return None

        return result.isoformat()
    except (orjson.JSONDecodeError, ValueError, TypeError, OverflowError) as e:
        _logger.warning("UDF dateAddQuantity failed: %s", e)
        return None


def dateSubtractQuantity(date_val: str | None, quantity_json: str | None) -> str | None:
    """
    Subtract a quantity from a date/datetime.

    Args:
        date_val: ISO date/datetime string
        quantity_json: JSON string representing a FHIR Quantity with time unit

    Returns:
        Resulting date/datetime as ISO string, or None if invalid
    """
    if quantity_json is None:
        return None

    try:
        data = orjson.loads(quantity_json)
        data["value"] = -float(data.get("value", 0))
        negated_json = orjson.dumps(data).decode("utf-8")
        return dateAddQuantity(date_val, negated_json)
    except (orjson.JSONDecodeError, ValueError, TypeError) as e:
        _logger.warning("UDF dateSubtractQuantity failed: %s", e)
        return None


# ========================================
# Registration
# ========================================

def registerDatetimeUdfs(con: "duckdb.DuckDBPyConnection") -> None:
    """
    Register datetime UDFs.

    Note: Functions covered by macros (YearsBetween, MonthsBetween, DaysBetween,
    HoursBetween, MinutesBetween, SecondsBetween, Now, Today, TimeOfDay, Year,
    Month, Day, Hour, Minute, Second) are NOT registered here to avoid conflicts.
    DuckDB function names are case-insensitive.

    Only functions NOT covered by macros are registered here:
    - weeksBetween, millisecondsBetween (no macro equivalents)
    - dateTimeNow, dateTimeToday, dateTimeTimeOfDay (different names)
    - differenceInYears, differenceInMonths, differenceInDays (different semantics)
    - dateComponent (dynamic component extraction)
    - dateTimeSameAs, dateTimeSameOrBefore, dateTimeSameOrAfter (precision-based comparison)
    """
    # Functions NOT covered by macros — use null_handling="special" for
    # all UDFs that can legitimately return None.
    con.create_function("weeksBetween", weeksBetween, null_handling="special")
    con.create_function("millisecondsBetween", millisecondsBetween, null_handling="special")
    # Now/Today/TimeOfDay with different names (not conflicting with macros)
    con.create_function("dateTimeNow", dateTimeNow, null_handling="special")
    con.create_function("dateTimeToday", dateTimeToday, null_handling="special")
    con.create_function("dateTimeTimeOfDay", dateTimeTimeOfDay, null_handling="special")
    # Difference functions (different semantics than Between functions)
    con.create_function("differenceInYears", differenceInYears, null_handling="special")
    con.create_function("differenceInMonths", differenceInMonths, null_handling="special")
    con.create_function("differenceInDays", differenceInDays, null_handling="special")
    con.create_function("differenceInWeeks", differenceInWeeks, null_handling="special")
    con.create_function("differenceInHours", differenceInHours, null_handling="special")
    con.create_function("differenceInMinutes", differenceInMinutes, null_handling="special")
    con.create_function("differenceInSeconds", differenceInSeconds, null_handling="special")
    con.create_function("differenceInMilliseconds", differenceInMilliseconds, null_handling="special")
    con.create_function("dateComponent", dateComponent, null_handling="special")
    # DateTime comparison with precision
    con.create_function("dateTimeSameAs", dateTimeSameAs, null_handling="special")
    con.create_function("dateTimeSameOrBefore", dateTimeSameOrBefore, null_handling="special")
    con.create_function("dateTimeSameOrAfter", dateTimeSameOrAfter, null_handling="special")
    # Date arithmetic with quantity
    con.create_function("quantityToInterval", quantityToInterval, null_handling="special")
    con.create_function("dateAddQuantity", dateAddQuantity, null_handling="special")
    con.create_function("dateSubtractQuantity", dateSubtractQuantity, null_handling="special")


__all__ = [
    "registerDatetimeUdfs",
    "yearsBetween",
    "monthsBetween",
    "weeksBetween",
    "daysBetween",
    "hoursBetween",
    "minutesBetween",
    "secondsBetween",
    "millisecondsBetween",
    # Now/Today/TimeOfDay functions
    "dateTimeNow",
    "dateTimeToday",
    "dateTimeTimeOfDay",
    # DifferenceBetween functions
    "differenceInYears",
    "differenceInMonths",
    "differenceInDays",
    "dateComponent",
    # DateTime comparison functions
    "dateTimeSameAs",
    "dateTimeSameOrBefore",
    "dateTimeSameOrAfter",
    # Date arithmetic with quantity
    "quantityToInterval",
    "dateAddQuantity",
    "dateSubtractQuantity",
]