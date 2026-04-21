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
    """Parse date from ISO 8601 string.

    Handles partial-precision strings: year-only ('2014') and
    year-month ('2014-01') by padding to full date.
    """
    if not value:
        return None
    try:
        val = value.strip()
        # Year-only: '2014' → date(2014, 1, 1)
        if len(val) == 4 and val.isdigit():
            return date(int(val), 1, 1)
        # Year-month: '2014-01' → date(2014, 1, 1)
        if len(val) == 7 and val[4] == '-' and val[:4].isdigit() and val[5:7].isdigit():
            return date(int(val[:4]), int(val[5:7]), 1)
        return date.fromisoformat(val[:10])
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
    """Parse datetime from ISO 8601 string.

    Handles partial-precision strings by padding to minimum valid datetime.
    """
    if not value:
        return None
    try:
        val = value.strip().replace("Z", "+00:00")

        # Handle partial-precision strings
        # Year-only with T suffix: '2014T' → datetime(2014, 1, 1)
        if val.endswith('T') and len(val) == 5 and val[:4].isdigit():
            return datetime(int(val[:4]), 1, 1)
        # Year-month with T suffix: '2014-01T' → datetime(2014, 1, 1)
        if val.endswith('T') and len(val) == 8 and val[4] == '-':
            return datetime(int(val[:4]), int(val[5:7]), 1)
        # Year-only: '2014' → datetime(2014, 1, 1)
        if len(val) == 4 and val.isdigit():
            return datetime(int(val), 1, 1)
        # Year-month: '2014-01' → datetime(2014, 1, 1)
        if len(val) == 7 and val[4] == '-' and val[:4].isdigit() and val[5:7].isdigit():
            return datetime(int(val[:4]), int(val[5:7]), 1)
        # Date-only: '2014-01-15' → datetime(2014, 1, 15)
        if len(val) == 10 and val[4] == '-' and val[7] == '-':
            d = date.fromisoformat(val)
            return datetime(d.year, d.month, d.day)
        # Hour-only: '2014-01-15T10' → datetime(2014, 1, 15, 10, 0, 0)
        if len(val) == 13 and 'T' in val:
            date_part = val[:10]
            hour = int(val[11:13])
            d = date.fromisoformat(date_part)
            return datetime(d.year, d.month, d.day, hour)

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


def _parse_to_datetime(iso_str: str) -> datetime | None:
    """Parse any ISO 8601 string (date, datetime, or time) to a datetime object.

    Handles Time-only strings ('T10:30:00', '10:30:00') by placing time
    components on epoch day (0001-01-01).
    """
    if iso_str is None:
        return None
    s = iso_str.strip()
    is_time = s.startswith('T') or (len(s) < 10 and ':' in s and '-' not in s)
    if is_time:
        comps = _parse_components(s)
        return datetime(comps['year'], comps['month'], comps['day'],
                        comps['hour'], comps['minute'], comps['second'],
                        comps['millisecond'] * 1000)
    result = _parse_datetime(s) or _parse_date(s)
    if result is None:
        return None
    if isinstance(result, date) and not isinstance(result, datetime):
        return datetime(result.year, result.month, result.day)
    return result


def _low_boundary(iso_str: str) -> datetime:
    """Compute the lowest possible datetime for a partial-precision ISO string.

    CQL §22.9: LowBoundary fills unspecified components with their minimum values.
    """
    comps = _parse_components(iso_str)
    return datetime(comps['year'], comps['month'], comps['day'],
                    comps['hour'], comps['minute'], comps['second'],
                    comps['millisecond'] * 1000)


def _high_boundary(iso_str: str) -> datetime:
    """Compute the highest possible datetime for a partial-precision ISO string.

    CQL §22.10: HighBoundary fills unspecified components with their maximum values.
    """
    prec = _infer_precision(iso_str)
    prec_idx = _PRECISION_INDEX.get(prec, 6)
    comps = _parse_components(iso_str)
    y, mo, d = comps['year'], comps['month'], comps['day']
    h, mi, s, ms = comps['hour'], comps['minute'], comps['second'], comps['millisecond']
    if prec_idx < 6:  # millisecond
        ms = 999
    if prec_idx < 5:  # second
        s = 59
    if prec_idx < 4:  # minute
        mi = 59
    if prec_idx < 3:  # hour
        h = 23
    if prec_idx < 2:  # day
        d = calendar.monthrange(y, mo)[1]
    if prec_idx < 1:  # month
        mo = 12
        d = 31
    return datetime(y, mo, d, h, mi, s, ms * 1000)


def _compute_duration(s: datetime, e: datetime, unit: str, is_week: bool) -> int:
    """Compute integer duration between two datetimes in the given unit.

    CQL §22.21: returns the number of whole calendar periods, truncated
    toward zero (not floored).
    """
    if unit in ('year', 'years'):
        years = e.year - s.year
        if (e.month, e.day, e.hour, e.minute, e.second, e.microsecond) < \
           (s.month, s.day, s.hour, s.minute, s.second, s.microsecond):
            years -= 1
        return years
    if unit in ('month', 'months'):
        months = (e.year - s.year) * 12 + (e.month - s.month)
        if (e.day, e.hour, e.minute, e.second, e.microsecond) < \
           (s.day, s.hour, s.minute, s.second, s.microsecond):
            months -= 1
        return months
    diff = e - s
    total_seconds = diff.total_seconds()
    # Use int(x / divisor) for truncation toward zero, NOT // (floor)
    if is_week or unit in ('week', 'weeks'):
        return int(total_seconds / 86400 / 7)
    if unit in ('day', 'days'):
        return int(total_seconds / 86400)
    if unit in ('hour', 'hours'):
        return int(total_seconds / 3600)
    if unit in ('minute', 'minutes'):
        return int(total_seconds / 60)
    if unit in ('second', 'seconds'):
        return int(total_seconds)
    if unit in ('millisecond', 'milliseconds'):
        return int(total_seconds * 1000)
    return int(total_seconds / 86400)


def _duration_between_with_uncertainty(start_str: str, end_str: str, unit: str) -> str:
    """CQL §22.21 DurationBetween with uncertainty interval support.

    Always returns VARCHAR: either an integer string or a JSON interval string.
    """
    s_prec = _infer_precision(start_str)
    e_prec = _infer_precision(end_str)

    unit_key = unit.rstrip('s')
    is_week = unit_key == 'week'
    if is_week:
        unit_key = 'day'

    unit_idx = _PRECISION_INDEX.get(unit_key, 2)
    s_idx = _PRECISION_INDEX.get(s_prec, 0)
    e_idx = _PRECISION_INDEX.get(e_prec, 0)

    # CQL §22.21: If both arguments have precision <= the unit precision,
    # result is an uncertainty interval. If at least one has finer precision,
    # the result is certain (computed using low boundaries for partial values).
    if s_idx > unit_idx or e_idx > unit_idx:
        # Both have sufficient precision — certain result
        s = _parse_to_datetime(start_str)
        e = _parse_to_datetime(end_str)
        if s is None or e is None:
            return None
        return str(_compute_duration(s, e, unit, is_week))

    # Uncertainty: compute min/max by using low/high boundaries
    s_low = _low_boundary(start_str)
    s_high = _high_boundary(start_str)
    e_low = _low_boundary(end_str)
    e_high = _high_boundary(end_str)

    # Min duration: start at highest, end at lowest
    min_val = _compute_duration(s_high, e_low, unit, is_week)
    # Max duration: start at lowest, end at highest
    max_val = _compute_duration(s_low, e_high, unit, is_week)

    if min_val == max_val:
        return str(min_val)

    return orjson.dumps({
        "start": min_val, "end": max_val,
        "lowClosed": True, "highClosed": True
    }).decode('utf-8')


def yearsBetween(start: str | None, end: str | None) -> int | None:
    """CQL years between two dates (integer result for backward compat)."""
    s, e = _parse_date(start), _parse_date(end)
    if not s or not e:
        return None
    years = e.year - s.year
    if (e.month, e.day) < (s.month, s.day):
        years -= 1
    return years


def monthsBetween(start: str | None, end: str | None) -> int | None:
    """CQL months between two dates (integer result)."""
    s, e = _parse_date(start), _parse_date(end)
    if not s or not e:
        return None
    months = (e.year - s.year) * 12 + (e.month - s.month)
    if e.day < s.day:
        months -= 1
    return months


def weeksBetween(start: str | None, end: str | None) -> int | None:
    """CQL weeks between two dates (integer result)."""
    s, e = _parse_date(start), _parse_date(end)
    if not s or not e:
        return None
    return (e - s).days // 7


def daysBetween(start: str | None, end: str | None) -> int | None:
    """CQL days between two dates (integer result)."""
    s, e = _parse_date(start), _parse_date(end)
    if not s or not e:
        return None
    return (e - s).days


def hoursBetween(start: str | None, end: str | None) -> int | None:
    """CQL hours between two datetimes (integer result)."""
    s, e = _parse_datetime(start), _parse_datetime(end)
    if not s or not e:
        return None
    return int((e - s).total_seconds() // 3600)


def minutesBetween(start: str | None, end: str | None) -> int | None:
    """CQL minutes between two datetimes (integer result)."""
    s, e = _parse_datetime(start), _parse_datetime(end)
    if not s or not e:
        return None
    return int((e - s).total_seconds() // 60)


def secondsBetween(start: str | None, end: str | None) -> int | None:
    """CQL seconds between two datetimes (integer result)."""
    s, e = _parse_datetime(start), _parse_datetime(end)
    if not s or not e:
        return None
    return int((e - s).total_seconds())


def millisecondsBetween(start: str | None, end: str | None) -> int | None:
    """CQL milliseconds between two datetimes (integer result)."""
    s, e = _parse_datetime(start), _parse_datetime(end)
    if not s or not e:
        return None
    return int((e - s).total_seconds() * 1000)


# ==============================================
# Uncertainty-aware DurationBetween (returns VARCHAR)
# CQL §22.21: Used by translator for DurationBetween/DifferenceBetween
# expressions where partial precision may produce uncertainty intervals.
# ==============================================

def cqlDurationBetween(start_str: str | None, end_str: str | None, unit: str | None) -> str | None:
    """CQL §22.21 DurationBetween with uncertainty interval support.

    Always returns VARCHAR: integer string if certain, JSON interval string if uncertain.
    """
    if start_str is None or end_str is None or unit is None:
        return None
    try:
        return _duration_between_with_uncertainty(str(start_str), str(end_str), str(unit))
    except (ValueError, TypeError):
        return None


def _parse_int_or_interval(val: str) -> int | dict:
    """Parse a Between result: integer string → int, JSON interval → dict."""
    try:
        return int(val)
    except (ValueError, TypeError):
        return orjson.loads(val)


def cqlUncertainAdd(a: str | None, b: str | None) -> str | None:
    """Add two values that may be integers or uncertainty intervals.

    CQL uncertainty arithmetic: Interval[a,b] + Interval[c,d] = Interval[a+c, b+d]
    """
    if a is None or b is None:
        return None
    try:
        av = _parse_int_or_interval(str(a))
        bv = _parse_int_or_interval(str(b))
    except Exception:
        return None
    a_is_int = isinstance(av, int)
    b_is_int = isinstance(bv, int)
    if a_is_int and b_is_int:
        return str(av + bv)
    a_low = av if a_is_int else av.get('start', 0)
    a_high = av if a_is_int else av.get('end', 0)
    b_low = bv if b_is_int else bv.get('start', 0)
    b_high = bv if b_is_int else bv.get('end', 0)
    return orjson.dumps({
        "start": a_low + b_low, "end": a_high + b_high,
        "lowClosed": True, "highClosed": True
    }).decode('utf-8')


def cqlUncertainSubtract(a: str | None, b: str | None) -> str | None:
    """Subtract two values that may be integers or uncertainty intervals.

    CQL: Interval[a,b] - Interval[c,d] = Interval[a-d, b-c]
    """
    if a is None or b is None:
        return None
    try:
        av = _parse_int_or_interval(str(a))
        bv = _parse_int_or_interval(str(b))
    except Exception:
        return None
    a_is_int = isinstance(av, int)
    b_is_int = isinstance(bv, int)
    if a_is_int and b_is_int:
        return str(av - bv)
    a_low = av if a_is_int else av.get('start', 0)
    a_high = av if a_is_int else av.get('end', 0)
    b_low = bv if b_is_int else bv.get('start', 0)
    b_high = bv if b_is_int else bv.get('end', 0)
    return orjson.dumps({
        "start": a_low - b_high, "end": a_high - b_low,
        "lowClosed": True, "highClosed": True
    }).decode('utf-8')


def cqlUncertainMultiply(a: str | None, b: str | None) -> str | None:
    """Multiply two values that may be integers or uncertainty intervals.

    CQL: Products of all endpoint combinations, take min/max.
    """
    if a is None or b is None:
        return None
    try:
        av = _parse_int_or_interval(str(a))
        bv = _parse_int_or_interval(str(b))
    except Exception:
        return None
    a_is_int = isinstance(av, int)
    b_is_int = isinstance(bv, int)
    if a_is_int and b_is_int:
        return str(av * bv)
    a_low = av if a_is_int else av.get('start', 0)
    a_high = av if a_is_int else av.get('end', 0)
    b_low = bv if b_is_int else bv.get('start', 0)
    b_high = bv if b_is_int else bv.get('end', 0)
    products = [a_low * b_low, a_low * b_high, a_high * b_low, a_high * b_high]
    return orjson.dumps({
        "start": min(products), "end": max(products),
        "lowClosed": True, "highClosed": True
    }).decode('utf-8')


def cqlUncertainCompare(a: str | None, b: str | None, op: str | None) -> bool | None:
    """Compare integer-or-interval with integer-or-interval.

    CQL three-valued logic: If ranges overlap for the comparison, return null.
    E.g., Interval[4,16] > 5 → null (could be 4 which is not > 5, or 16 which is).
    """
    if a is None or b is None:
        return None
    try:
        av = _parse_int_or_interval(str(a))
        bv = _parse_int_or_interval(str(b))
    except Exception:
        return None
    a_is_int = isinstance(av, int)
    b_is_int = isinstance(bv, int)
    a_low = av if a_is_int else av.get('start', 0)
    a_high = av if a_is_int else av.get('end', 0)
    b_low = bv if b_is_int else bv.get('start', 0)
    b_high = bv if b_is_int else bv.get('end', 0)
    op_str = str(op) if op else '>'
    if op_str == '>':
        if a_low > b_high:
            return True
        if a_high <= b_low:
            return False
        return None
    if op_str == '>=':
        if a_low >= b_high:
            return True
        if a_high < b_low:
            return False
        return None
    if op_str == '<':
        if a_high < b_low:
            return True
        if a_low >= b_high:
            return False
        return None
    if op_str == '<=':
        if a_high <= b_low:
            return True
        if a_low > b_high:
            return False
        return None
    if op_str in ('=', '=='):
        if a_low == a_high == b_low == b_high:
            return True
        if a_high < b_low or a_low > b_high:
            return False
        return None
    return None


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


def _format_result_at_input_precision(result: datetime, input_str: str) -> str:
    """Format a datetime result preserving the precision of the input string.

    CQL §18.9: The result of date/time arithmetic preserves the precision
    of the input.  E.g. adding hours to a day-precision date returns a
    day-precision result.
    """
    prec = _infer_precision(input_str)
    prec_idx = _PRECISION_INDEX.get(prec, 6)

    # Check for timezone in input
    tz_suffix = ''
    stripped = input_str.strip()
    for tz_char in ('+', 'Z'):
        idx = stripped.find(tz_char, 10) if len(stripped) > 10 else -1
        if idx > 0:
            # Preserve original timezone offset in result
            tz_suffix = stripped[idx:]
            break
    # Check for negative tz offset
    if not tz_suffix and len(stripped) > 10:
        for i in range(len(stripped) - 1, 9, -1):
            if stripped[i] == '-' and i > 10:
                tz_suffix = stripped[i:]
                break

    # Build ISO 8601 string at the input precision level
    iso = f"{result.year:04d}"
    if prec_idx >= 1:
        iso += f"-{result.month:02d}"
    if prec_idx >= 2:
        iso += f"-{result.day:02d}"
    if prec_idx >= 3:
        iso += f"T{result.hour:02d}"
    if prec_idx >= 4:
        iso += f":{result.minute:02d}"
    if prec_idx >= 5:
        iso += f":{result.second:02d}"
    if prec_idx >= 6:
        ms = result.microsecond // 1000
        iso += f".{ms:03d}"
    if tz_suffix:
        iso += tz_suffix
    return iso


def dateAddQuantity(date_val: str | None, quantity_json: str | None) -> str | None:
    """Add a quantity to a date/datetime.

    CQL §5.6.4: Arithmetic is performed at the precision of the input.
    If the quantity's unit is below the input's precision, the quantity is
    converted to the input precision level using CQL conversion factors
    (1 year=12 months, 1 month=30 days, 1 day=24 hours, 1 hour=60 min,
    1 min=60 sec, 1 sec=1000 ms). Integer division truncates the remainder.

    Args:
        date_val: ISO date/datetime string
        quantity_json: JSON string with {value, unit}

    Returns:
        ISO string at the input's precision, or None.
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

        # Time-only value (e.g. 'T15:59:59.999')
        t = _parse_time(date_val)
        if t is not None:
            from datetime import time as _time_class
            ref_dt = _dt_class(2000, 1, 1, t.hour, t.minute, t.second, t.microsecond)
            if unit_lower in _TIMEDELTA_UNITS:
                result_dt = ref_dt + timedelta(**{_TIMEDELTA_UNITS[unit_lower]: value})
                result_time = result_dt.time()
                ms = result_time.microsecond // 1000
                return f"T{result_time.hour:02d}:{result_time.minute:02d}:{result_time.second:02d}.{ms:03d}"
            return None

        input_prec = _infer_precision(date_val)
        input_prec_idx = _PRECISION_INDEX.get(input_prec, 6)

        dt = _parse_datetime(date_val)
        if dt is None:
            dt = _parse_date(date_val)
            if dt is None:
                return None
            dt = _dt_class.combine(dt, _dt_class.min.time())

        # Map unit to its precision level
        _unit_to_prec_idx = {
            'year': 0, 'years': 0, 'a': 0,
            'month': 1, 'months': 1, 'mo': 1,
            'week': 2, 'weeks': 2, 'wk': 2,
            'day': 2, 'days': 2, 'd': 2,
            'hour': 3, 'hours': 3, 'h': 3,
            'minute': 4, 'minutes': 4, 'min': 4,
            'second': 5, 'seconds': 5, 's': 5,
            'millisecond': 6, 'milliseconds': 6, 'ms': 6,
        }
        unit_prec_idx = _unit_to_prec_idx.get(unit_lower, 6)

        # CQL conversion factors: how many of the finer unit per coarser unit
        # Index i → how many units at level i+1 per 1 unit at level i
        _conversion = {
            0: 12,     # 1 year = 12 months
            1: 30,     # 1 month = 30 days
            2: 24,     # 1 day = 24 hours
            3: 60,     # 1 hour = 60 minutes
            4: 60,     # 1 minute = 60 seconds
            5: 1000,   # 1 second = 1000 ms
        }

        # Convert quantity to input precision if quantity is finer
        effective_value = value
        effective_unit = unit_lower

        if unit_prec_idx > input_prec_idx:
            # Convert from finer to coarser by dividing through
            # E.g., 25 months → years: 25 / 12 = 2
            # E.g., 33 days → months: 33 / 30 = 1
            divisor = 1
            for lvl in range(input_prec_idx, unit_prec_idx):
                divisor *= _conversion[lvl]
            effective_value = int(int(value) / divisor) if divisor > 0 else int(value)
            # Map to the input precision unit
            prec_to_unit = {0: 'years', 1: 'months', 2: 'days', 3: 'hours',
                           4: 'minutes', 5: 'seconds', 6: 'milliseconds'}
            effective_unit = prec_to_unit.get(input_prec_idx, unit_lower)

        # Perform arithmetic at the effective precision
        if effective_unit in _YEAR_UNITS or effective_unit in ('years',):
            target_year = dt.year + int(effective_value)
            max_day = calendar.monthrange(target_year, dt.month)[1]
            result = dt.replace(year=target_year, day=min(dt.day, max_day))
        elif effective_unit in _MONTH_UNITS or effective_unit in ('months',):
            new_month = dt.month + int(effective_value)
            new_year = dt.year + (new_month - 1) // 12
            new_month = ((new_month - 1) % 12) + 1
            max_day = calendar.monthrange(new_year, new_month)[1]
            result = dt.replace(year=new_year, month=new_month, day=min(dt.day, max_day))
        elif effective_unit in ('weeks', 'week', 'wk'):
            result = dt + timedelta(weeks=int(effective_value))
        elif effective_unit in _TIMEDELTA_UNITS:
            result = dt + timedelta(**{_TIMEDELTA_UNITS[effective_unit]: effective_value})
        elif effective_unit in ('days',):
            result = dt + timedelta(days=int(effective_value))
        elif effective_unit in ('hours',):
            result = dt + timedelta(hours=int(effective_value))
        elif effective_unit in ('minutes',):
            result = dt + timedelta(minutes=int(effective_value))
        elif effective_unit in ('seconds',):
            result = dt + timedelta(seconds=int(effective_value))
        elif effective_unit in ('milliseconds',):
            result = dt + timedelta(milliseconds=int(effective_value))
        else:
            return None

        return _format_result_at_input_precision(result, date_val)
    except (orjson.JSONDecodeError, ValueError, TypeError, OverflowError) as e:
        raise ValueError(f"DateTime arithmetic overflow: {e}") from e


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
        raise ValueError(f"DateTime arithmetic overflow: {e}") from e


# ========================================
# Precision-Aware Temporal Operations
# CQL §18.4 (Uncertainty), §19.15-16 (Comparison with precision)
# ========================================

# Precision levels ordered from coarsest to finest
_PRECISION_ORDER = ('year', 'month', 'day', 'hour', 'minute', 'second', 'millisecond')
_PRECISION_INDEX = {p: i for i, p in enumerate(_PRECISION_ORDER)}


def _infer_precision(iso_str: str) -> str:
    """Infer CQL precision from an ISO 8601 datetime string's length/format.

    CQL §18.2: Precision is determined by the number of specified components.
    '2014'           → year
    '2014-01'        → month
    '2014-01-15'     → day
    '2014-01-15T10'  → hour  (rare but valid)
    '2014-01-15T10:30' → minute
    '2014-01-15T10:30:00' → second
    '2014-01-15T10:30:00.000' → millisecond
    """
    s = iso_str.strip()
    # Strip timezone suffix for length calculation
    for tz_char in ('+', '-', 'Z'):
        idx = s.find(tz_char, 10) if len(s) > 10 else -1
        if idx > 0:
            s = s[:idx]
            break

    # Time-only: T-prefixed or bare HH:MM:SS
    if s.startswith('T') or (len(s) < 10 and ':' in s and '-' not in s):
        s = s.lstrip('T')
        if '.' in s:
            return 'millisecond'
        parts = s.split(':')
        if len(parts) >= 3:
            return 'second'
        if len(parts) >= 2:
            return 'minute'
        return 'hour'

    # Date/DateTime
    if 'T' in s or ' ' in s:
        sep = 'T' if 'T' in s else ' '
        date_part, time_part = s.split(sep, 1)
        if not time_part:
            # 'T' suffix with no time components (e.g., '2014T') — use date precision
            dashes = date_part.count('-')
            if dashes >= 2:
                return 'day'
            if dashes == 1:
                return 'month'
            return 'year'
        if '.' in time_part:
            return 'millisecond'
        parts = time_part.split(':')
        if len(parts) >= 3:
            return 'second'
        if len(parts) >= 2:
            return 'minute'
        return 'hour'

    # Date only
    dashes = s.count('-')
    if dashes >= 2:
        return 'day'
    if dashes == 1:
        return 'month'
    return 'year'


def _parse_components(iso_str: str) -> dict:
    """Parse ISO 8601 string into component dict with precision."""
    s = iso_str.strip()

    # Detect Time-only strings: 'T'-prefixed or bare HH:MM:SS patterns
    is_time_only = s.startswith('T') or (len(s) < 10 and ':' in s and '-' not in s)
    if is_time_only:
        time_s = s.lstrip('T')
        comps = {'year': 1, 'month': 1, 'day': 1, 'hour': 0, 'minute': 0,
                 'second': 0, 'millisecond': 0, 'tz': ''}
        time_parts = time_s.split(':')
        if len(time_parts) >= 1:
            comps['hour'] = int(time_parts[0])
        if len(time_parts) >= 2:
            comps['minute'] = int(time_parts[1])
        if len(time_parts) >= 3:
            sec_parts = time_parts[2].split('.')
            comps['second'] = int(sec_parts[0])
            if len(sec_parts) > 1:
                ms_str = sec_parts[1][:3].ljust(3, '0')
                comps['millisecond'] = int(ms_str)
        return comps

    tz_suffix = ''
    # Extract timezone
    for tz_char in ('+', 'Z'):
        idx = s.find(tz_char, 10) if len(s) > 10 else -1
        if idx > 0:
            tz_suffix = s[idx:]
            s = s[:idx]
            break
    # Check for negative tz offset (after pos 10 to avoid date dash)
    if len(s) > 10:
        for i in range(len(s) - 1, 9, -1):
            if s[i] == '-' and i > 10:
                tz_suffix = s[i:]
                s = s[:i]
                break

    comps = {'year': 1, 'month': 1, 'day': 1, 'hour': 0, 'minute': 0,
             'second': 0, 'millisecond': 0, 'tz': tz_suffix}

    # Handle 'T' or space separator
    time_str = None
    if 'T' in s:
        date_str, time_str = s.split('T', 1)
    elif ' ' in s:
        date_str, time_str = s.split(' ', 1)
    else:
        date_str = s

    # Parse date part
    date_parts = date_str.split('-')
    if len(date_parts) >= 1 and date_parts[0]:
        comps['year'] = int(date_parts[0])
    if len(date_parts) >= 2:
        comps['month'] = int(date_parts[1])
    if len(date_parts) >= 3:
        comps['day'] = int(date_parts[2])

    # Parse time part
    if time_str:
        time_parts = time_str.split(':')
        if len(time_parts) >= 1:
            comps['hour'] = int(time_parts[0])
        if len(time_parts) >= 2:
            comps['minute'] = int(time_parts[1])
        if len(time_parts) >= 3:
            sec_parts = time_parts[2].split('.')
            comps['second'] = int(sec_parts[0])
            if len(sec_parts) > 1:
                ms_str = sec_parts[1][:3].ljust(3, '0')
                comps['millisecond'] = int(ms_str)

    return comps


def _format_at_precision(comps: dict, precision: str) -> str:
    """Format datetime components back to ISO 8601 at the given precision."""
    prec_idx = _PRECISION_INDEX.get(precision, 6)
    result = f"{comps['year']:04d}"
    if prec_idx >= 1:
        result += f"-{comps['month']:02d}"
    if prec_idx >= 2:
        result += f"-{comps['day']:02d}"
    if prec_idx >= 3:
        result += f"T{comps['hour']:02d}"
    if prec_idx >= 4:
        result += f":{comps['minute']:02d}"
    if prec_idx >= 5:
        result += f":{comps['second']:02d}"
    if prec_idx >= 6:
        result += f".{comps['millisecond']:03d}"
    tz = comps.get('tz', '')
    if tz:
        result += tz
    return result


def _normalize_to_utc(comps: dict) -> dict:
    """Normalize datetime components to UTC using timezone offset.

    CQL §22.1: Timezone-aware datetimes are compared by normalizing to UTC.
    If no timezone is present, the components are returned unchanged.
    """
    tz = comps.get('tz', '')
    if not tz or tz == 'Z':
        result = dict(comps)
        result['tz'] = ''
        return result

    # Parse offset: +HH:MM or -HH:MM
    sign = 1 if tz[0] == '+' else -1
    tz_parts = tz[1:].split(':')
    tz_hours = int(tz_parts[0])
    tz_minutes = int(tz_parts[1]) if len(tz_parts) > 1 else 0
    offset_minutes = sign * (tz_hours * 60 + tz_minutes)

    # Convert to UTC by subtracting the offset
    from datetime import datetime, timedelta
    dt = datetime(
        comps['year'], comps['month'], comps['day'],
        comps['hour'], comps['minute'], comps['second'],
        comps['millisecond'] * 1000,  # microseconds
    )
    dt_utc = dt - timedelta(minutes=offset_minutes)

    return {
        'year': dt_utc.year,
        'month': dt_utc.month,
        'day': dt_utc.day,
        'hour': dt_utc.hour,
        'minute': dt_utc.minute,
        'second': dt_utc.second,
        'millisecond': dt_utc.microsecond // 1000,
        'tz': '',
    }


def cqlNormalizeTZ(dt: str | None) -> str | None:
    """Normalize a timezone-aware ISO 8601 datetime string to UTC.

    CQL §22.1: Timezone-aware values are compared by normalizing to UTC.
    Preserves the original precision (e.g., hour-precision stays hour-precision).
    If no timezone is present, returns the value unchanged.
    Time-only values (HH:MM:SS or THH:MM:SS) are returned unchanged.
    """
    if dt is None:
        return None
    s = str(dt).strip()
    # Time-only values don't have timezone context — pass through
    if s.startswith('T') or (len(s) <= 12 and ':' in s and '-' not in s[:4]):
        return s
    comps = _parse_components(s)
    tz = comps.get('tz', '')
    if not tz or tz == 'Z':
        return s.replace('Z', '').rstrip('+')  # strip 'Z' for clean comparison
    prec = _infer_precision(s)
    utc_comps = _normalize_to_utc(comps)
    return _format_at_precision(utc_comps, prec)


def _compare_at_min_precision(a_str: str, b_str: str) -> tuple:
    """Compare two datetime strings at min(a_precision, b_precision).

    Returns (result, is_certain):
    - result: -1 (a < b), 0 (a == b), 1 (a > b)
    - is_certain: True if result is definite; False if uncertain (should return NULL)

    CQL §19.15: When values have differing precisions, comparison proceeds
    component by component. If one value is specified at a precision and the
    other is not, the result is null (uncertain).
    """
    # Guard: reject non-datetime strings (interval JSON, quantity JSON, etc.)
    for s in (a_str, b_str):
        stripped = s.strip()
        if stripped.startswith('{') or stripped.startswith('['):
            raise ValueError(f"Not a datetime string: {stripped[:50]}")

    a_prec = _infer_precision(a_str)
    b_prec = _infer_precision(b_str)
    a_idx = _PRECISION_INDEX[a_prec]
    b_idx = _PRECISION_INDEX[b_prec]
    min_idx = min(a_idx, b_idx)

    a_comps = _parse_components(a_str)
    b_comps = _parse_components(b_str)

    # CQL §22.1: Normalize timezone-aware values to UTC before comparing
    if a_comps.get('tz') or b_comps.get('tz'):
        a_comps = _normalize_to_utc(a_comps)
        b_comps = _normalize_to_utc(b_comps)

    for i, field in enumerate(_PRECISION_ORDER[:min_idx + 1]):
        a_val = a_comps[field]
        b_val = b_comps[field]
        if a_val < b_val:
            return (-1, True)
        if a_val > b_val:
            return (1, True)

    # All compared components are equal
    # If precisions differ, the result is uncertain (CQL §18.4)
    if a_idx != b_idx:
        # CQL §7.1.3: Type promotion — Date to DateTime.
        # When one operand is DateTime (has 'T' separator with time components)
        # and the other is a Date (YYYY-MM-DD, no 'T', exactly 10 chars),
        # promote the Date by adding T00:00:00.000 (start of day) and re-compare.
        # This only applies when the Date has full day precision (10 chars).
        a_has_time_sep = 'T' in a_str or ' ' in a_str[10:11]
        b_has_time_sep = 'T' in b_str or ' ' in b_str[10:11]
        a_is_date_only = (not a_has_time_sep and len(a_str.split('+')[0].split('Z')[0]) == 10)
        b_is_date_only = (not b_has_time_sep and len(b_str.split('+')[0].split('Z')[0]) == 10)

        if a_is_date_only and b_has_time_sep and not b_is_date_only:
            # Promote a (Date) to DateTime with midnight
            promoted = a_str + 'T00:00:00.000'
            a_comps2 = _parse_components(promoted)
            b_comps2 = b_comps
            if a_comps2.get('tz') or b_comps2.get('tz'):
                a_comps2 = _normalize_to_utc(a_comps2)
                b_comps2 = _normalize_to_utc(b_comps2)
            new_max = _PRECISION_INDEX[_infer_precision(promoted)]
            compare_to = min(new_max, b_idx)
            for i, field in enumerate(_PRECISION_ORDER[:compare_to + 1]):
                av = a_comps2[field]
                bv = b_comps2[field]
                if av < bv:
                    return (-1, True)
                if av > bv:
                    return (1, True)
            return (0, True)

        if b_is_date_only and a_has_time_sep and not a_is_date_only:
            # Promote b (Date) to DateTime with midnight
            promoted = b_str + 'T00:00:00.000'
            a_comps2 = a_comps
            b_comps2 = _parse_components(promoted)
            if a_comps2.get('tz') or b_comps2.get('tz'):
                a_comps2 = _normalize_to_utc(a_comps2)
                b_comps2 = _normalize_to_utc(b_comps2)
            new_max = _PRECISION_INDEX[_infer_precision(promoted)]
            compare_to = min(a_idx, new_max)
            for i, field in enumerate(_PRECISION_ORDER[:compare_to + 1]):
                av = a_comps2[field]
                bv = b_comps2[field]
                if av < bv:
                    return (-1, True)
                if av > bv:
                    return (1, True)
            return (0, True)

        return (0, False)  # equal so far, but uncertain due to unspecified components

    return (0, True)  # fully equal at same precision


def cqlSameOrBefore(a: str | None, b: str | None) -> bool | None:
    """CQL SameOrBefore without explicit precision (§19.16).

    Returns True if a <= b at min precision, None if uncertain.
    """
    if a is None or b is None:
        return None
    a_s, b_s = str(a), str(b)
    try:
        cmp, certain = _compare_at_min_precision(a_s, b_s)
    except (ValueError, KeyError):
        return None
    if cmp < 0:
        return True
    if cmp > 0:
        return False
    # cmp == 0: equal at compared precision
    if not certain:
        return None  # uncertain — different precisions
    return True  # same at same precision → True


def cqlSameOrAfter(a: str | None, b: str | None) -> bool | None:
    """CQL SameOrAfter without explicit precision (§19.17)."""
    if a is None or b is None:
        return None
    a_s, b_s = str(a), str(b)
    try:
        cmp, certain = _compare_at_min_precision(a_s, b_s)
    except (ValueError, KeyError):
        return None
    if cmp > 0:
        return True
    if cmp < 0:
        return False
    if not certain:
        return None
    return True


def cqlBefore(a: str | None, b: str | None) -> bool | None:
    """CQL Before without explicit precision (§19.20)."""
    if a is None or b is None:
        return None
    a_s, b_s = str(a), str(b)
    try:
        cmp, certain = _compare_at_min_precision(a_s, b_s)
    except (ValueError, KeyError):
        return None
    if cmp < 0:
        return True
    if cmp > 0:
        return False
    if not certain:
        return None
    return False


def cqlAfter(a: str | None, b: str | None) -> bool | None:
    """CQL After without explicit precision (§19.21)."""
    if a is None or b is None:
        return None
    a_s, b_s = str(a), str(b)
    try:
        cmp, certain = _compare_at_min_precision(a_s, b_s)
    except (ValueError, KeyError):
        return None
    if cmp > 0:
        return True
    if cmp < 0:
        return False
    if not certain:
        return None
    return False


def cqlDateTimeEqual(a: str | None, b: str | None) -> bool | None:
    """CQL DateTime equality (§12.1). Returns null if uncertain."""
    if a is None or b is None:
        return None
    a_s, b_s = str(a), str(b)
    cmp, certain = _compare_at_min_precision(a_s, b_s)
    if cmp != 0:
        return False
    if not certain:
        return None
    return True


def _compare_at_specified_precision(a_str: str, b_str: str, precision: str) -> tuple:
    """Compare two datetime strings at a specific precision.

    CQL §19.15: When precision is specified, compare components up to that
    precision. If either operand has coarser precision than specified,
    the result is uncertain (null).

    Returns (result, is_certain):
    - result: -1 (a < b), 0 (a == b), 1 (a > b)
    - is_certain: False if either operand is coarser than the target precision
    """
    a_comps = _parse_components(a_str)
    b_comps = _parse_components(b_str)

    # Normalize timezone to UTC for comparison
    if a_comps.get('tz') or b_comps.get('tz'):
        a_comps = _normalize_to_utc(a_comps)
        b_comps = _normalize_to_utc(b_comps)

    a_prec = _infer_precision(a_str)
    b_prec = _infer_precision(b_str)
    a_idx = _PRECISION_INDEX.get(a_prec, 0)
    b_idx = _PRECISION_INDEX.get(b_prec, 0)
    target_idx = _PRECISION_INDEX.get(precision, 2)

    # If either operand is coarser than the target precision, uncertain
    if a_idx < target_idx or b_idx < target_idx:
        # Compare what we can, then report uncertainty
        usable_idx = min(a_idx, b_idx, target_idx)
        for i, field in enumerate(_PRECISION_ORDER[:usable_idx + 1]):
            a_val = a_comps[field]
            b_val = b_comps[field]
            if a_val < b_val:
                return (-1, True)  # definitely less even with uncertainty
            if a_val > b_val:
                return (1, True)  # definitely greater
        return (0, False)  # equal at shared precision, but uncertain at target

    # Both have sufficient precision — compare up to target
    for i, field in enumerate(_PRECISION_ORDER[:target_idx + 1]):
        a_val = a_comps[field]
        b_val = b_comps[field]
        if a_val < b_val:
            return (-1, True)
        if a_val > b_val:
            return (1, True)

    return (0, True)


def cqlSameOrBeforeP(a: str | None, b: str | None, precision: str | None) -> bool | None:
    """CQL SameOrBefore at specified precision (§19.16)."""
    if a is None or b is None:
        return None
    try:
        cmp, certain = _compare_at_specified_precision(str(a), str(b), str(precision))
    except (ValueError, KeyError):
        return None
    if cmp < 0:
        return True
    if cmp > 0:
        return False
    if not certain:
        return None
    return True


def cqlSameOrAfterP(a: str | None, b: str | None, precision: str | None) -> bool | None:
    """CQL SameOrAfter at specified precision (§19.17)."""
    if a is None or b is None:
        return None
    try:
        cmp, certain = _compare_at_specified_precision(str(a), str(b), str(precision))
    except (ValueError, KeyError):
        return None
    if cmp > 0:
        return True
    if cmp < 0:
        return False
    if not certain:
        return None
    return True


def cqlBeforeP(a: str | None, b: str | None, precision: str | None) -> bool | None:
    """CQL Before at specified precision (§19.20)."""
    if a is None or b is None:
        return None
    try:
        cmp, certain = _compare_at_specified_precision(str(a), str(b), str(precision))
    except (ValueError, KeyError):
        return None
    if cmp < 0:
        return True
    if cmp > 0:
        return False
    if not certain:
        return None
    return False


def cqlAfterP(a: str | None, b: str | None, precision: str | None) -> bool | None:
    """CQL After at specified precision (§19.21)."""
    if a is None or b is None:
        return None
    try:
        cmp, certain = _compare_at_specified_precision(str(a), str(b), str(precision))
    except (ValueError, KeyError):
        return None
    if cmp > 0:
        return True
    if cmp < 0:
        return False
    if not certain:
        return None
    return False


def cqlSameAsP(a: str | None, b: str | None, precision: str | None) -> bool | None:
    """CQL SameAs at specified precision (§19.14)."""
    if a is None or b is None:
        return None
    try:
        cmp, certain = _compare_at_specified_precision(str(a), str(b), str(precision))
    except (ValueError, KeyError):
        return None
    if cmp != 0:
        return False
    if not certain:
        return None
    return True


def cqlDateTimeAdd(dt_str: str | None, qty_json: str | None) -> str | None:
    """CQL DateTime add with precision preservation (§18.9).

    Adds a quantity to a datetime, preserving the input precision in the result.
    E.g., adding 5 hours to '2014-01-01' (day precision) returns '2014-01-01'
    (day precision preserved), not '2014-01-01T05:00:00'.
    """
    if dt_str is None or qty_json is None:
        return None

    # Delegate to dateAddQuantity for the actual computation
    full_result = dateAddQuantity(str(dt_str), str(qty_json))
    if full_result is None:
        return None

    # Preserve the input precision in the output
    input_prec = _infer_precision(str(dt_str))
    result_comps = _parse_components(full_result)
    return _format_at_precision(result_comps, input_prec)


def cqlDateTimeSubtract(dt_str: str | None, qty_json: str | None) -> str | None:
    """CQL DateTime subtract with precision preservation (§18.10).

    Subtracts a quantity from a datetime, preserving the input precision.
    E.g., subtracting 25 months from '2014-06' (month precision) returns
    '2012' (year precision if remainder).
    """
    if dt_str is None or qty_json is None:
        return None

    # Delegate to dateSubtractQuantity for the actual computation
    full_result = dateSubtractQuantity(str(dt_str), str(qty_json))
    if full_result is None:
        return None

    # Preserve the input precision in the output
    input_prec = _infer_precision(str(dt_str))
    result_comps = _parse_components(full_result)
    return _format_at_precision(result_comps, input_prec)


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
    - cqlSameOrBefore, cqlSameOrAfter, cqlBefore, cqlAfter (precision-aware)
    """
    # Register ALL Between functions as Python UDFs (macros removed —
    # Python UDFs handle partial ISO 8601 strings and return uncertainty
    # intervals per CQL §22.21).
    # DuckDB function names are case-insensitive — register once only.
    con.create_function("YearsBetween", yearsBetween, null_handling="special")
    con.create_function("MonthsBetween", monthsBetween, null_handling="special")
    con.create_function("WeeksBetween", weeksBetween, null_handling="special")
    con.create_function("DaysBetween", daysBetween, null_handling="special")
    con.create_function("HoursBetween", hoursBetween, null_handling="special")
    con.create_function("MinutesBetween", minutesBetween, null_handling="special")
    con.create_function("SecondsBetween", secondsBetween, null_handling="special")
    con.create_function("MillisecondsBetween", millisecondsBetween, null_handling="special")
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
    # Precision-aware temporal comparison UDFs (CQL §18.4, §19.15-16)
    con.create_function("cqlSameOrBefore", cqlSameOrBefore, null_handling="special")
    con.create_function("cqlSameOrAfter", cqlSameOrAfter, null_handling="special")
    con.create_function("cqlBefore", cqlBefore, null_handling="special")
    con.create_function("cqlAfter", cqlAfter, null_handling="special")
    con.create_function("cqlDateTimeEqual", cqlDateTimeEqual, null_handling="special")
    # Precision-aware arithmetic (preserves input precision in output)
    con.create_function("cqlDateTimeAdd", cqlDateTimeAdd, null_handling="special")
    con.create_function("cqlDateTimeSubtract", cqlDateTimeSubtract, null_handling="special")
    # Timezone normalization (CQL §22.1)
    con.create_function("cqlNormalizeTZ", cqlNormalizeTZ, null_handling="special")
    # Precision-qualified temporal comparison UDFs (CQL §19.14-21)
    con.create_function("cqlSameOrBeforeP", cqlSameOrBeforeP, null_handling="special")
    con.create_function("cqlSameOrAfterP", cqlSameOrAfterP, null_handling="special")
    con.create_function("cqlBeforeP", cqlBeforeP, null_handling="special")
    con.create_function("cqlAfterP", cqlAfterP, null_handling="special")
    con.create_function("cqlSameAsP", cqlSameAsP, null_handling="special")
    # Uncertainty arithmetic UDFs (CQL §22.21 — interval propagation)
    con.create_function("cqlUncertainAdd", cqlUncertainAdd, null_handling="special")
    con.create_function("cqlUncertainSubtract", cqlUncertainSubtract, null_handling="special")
    con.create_function("cqlUncertainMultiply", cqlUncertainMultiply, null_handling="special")
    con.create_function("cqlUncertainCompare", cqlUncertainCompare, null_handling="special")
    # Uncertainty-aware DurationBetween (returns VARCHAR — int string or interval JSON)
    con.create_function("cqlDurationBetween", cqlDurationBetween, null_handling="special")


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