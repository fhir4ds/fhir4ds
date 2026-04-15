"""
CQL Interval UDFs

Implements CQL interval operations:
- intervalContains(interval, value)
- intervalOverlaps(interval1, interval2)
- intervalBefore(interval1, interval2)
- intervalAfter(interval1, interval2)
- intervalMeets(interval1, interval2)
- intervalStarts(interval, point)
- intervalEnds(interval, point)
- intervalWidth(interval)
- intervalStart(interval)
- intervalEnd(interval)

Interval format: JSON string {"low": "2024-01-01", "high": "2024-12-31", "lowClosed": true, "highClosed": true}
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING, Any

import orjson
from orjson import JSONDecodeError

if TYPE_CHECKING:
    import duckdb


import logging

_logger = logging.getLogger(__name__)


def _successor(value: Any) -> Any:
    """CQL successor: smallest value greater than the given value."""
    if isinstance(value, int):
        return value + 1
    if isinstance(value, float):
        import math
        return math.nextafter(value, float('inf'))
    if isinstance(value, datetime):
        return value + timedelta(milliseconds=1)
    if isinstance(value, date) and not isinstance(value, datetime):
        return value + timedelta(days=1)
    return None


def _predecessor(value: Any) -> Any:
    """CQL predecessor: largest value less than the given value."""
    if isinstance(value, int):
        return value - 1
    if isinstance(value, float):
        import math
        return math.nextafter(value, float('-inf'))
    if isinstance(value, datetime):
        return value - timedelta(milliseconds=1)
    if isinstance(value, date) and not isinstance(value, datetime):
        return value - timedelta(days=1)
    return None


def _effective_end(iv: dict) -> Any:
    """Get the last value contained in the interval (handles open/closed)."""
    if iv["high"] is None:
        return None
    if iv.get("high_closed", True):
        return iv["high"]
    return _predecessor(iv["high"])


def _effective_start(iv: dict) -> Any:
    """Get the first value contained in the interval (handles open/closed)."""
    if iv["low"] is None:
        return None
    if iv.get("low_closed", True):
        return iv["low"]
    return _successor(iv["low"])
# Pattern matching valid point values: dates, datetimes, numbers
_POINT_VALUE_RE = re.compile(
    r'^\d{4}(-\d{2}(-\d{2}(T\d{2}:\d{2}(:\d{2})?)?)?)?([+-]\d{2}:\d{2}|Z)?$'
    r'|^-?\d+(\.\d+)?$'
)


def _parse_interval_bound(value: Any) -> Any:
    """Parse string/date-like interval bounds, preserving non-string scalars.

    Handles numeric strings (integers/decimals) in addition to dates/datetimes.
    Date parsing is tried first so that year-only strings like "2024" are not
    misinterpreted as integers.
    """
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        # Try date/datetime first so year-only dates like "2024" aren't
        # mistaken for integers.
        parsed = _parse_date_or_datetime(value)
        if parsed is not None:
            return parsed
        # Then try numeric parsing (integers/decimals)
        try:
            if '.' in value and 'T' not in value and '-' not in value[1:]:
                return float(value)
            stripped = value.strip()
            if stripped.lstrip('-').isdigit():
                return int(stripped)
        except (ValueError, OverflowError):
            pass
    return value


def _parse_point(value: str | None) -> Any:
    """Parse a point value which may be a date, datetime, integer, or decimal."""
    if value is None:
        return None
    if not isinstance(value, str):
        return value
    stripped = value.strip()
    if not stripped:
        return None
    # Try numeric first
    try:
        if '.' in stripped and 'T' not in stripped and '-' not in stripped[1:]:
            return float(stripped)
        if stripped.lstrip('-').isdigit():
            return int(stripped)
    except (ValueError, OverflowError):
        pass
    # Then try date/datetime
    return _parse_date_or_datetime(stripped)


def _parse_interval(value: str) -> dict | None:
    """Parse interval JSON to dict with date objects."""
    if not value:
        return None
    try:
        data = orjson.loads(value)
    except JSONDecodeError:
        # Upstream may return Python repr (single quotes) instead of JSON.
        # Use ast.literal_eval for safe parsing of Python dict literals.
        try:
            import ast
            data = ast.literal_eval(value)
        except (ValueError, SyntaxError) as e:
            _logger.warning("_parse_interval parse failed: %s", e)
            return None
    if not isinstance(data, dict):
        _logger.warning("_parse_interval structure parse failed: expected object, got %s", type(data).__name__)
        return None
    # Support both CQL interval format (low/high) and FHIR Period (start/end)
    low_val = data.get("low") or data.get("start")
    high_val = data.get("high") or data.get("end")
    return {
        "low": _parse_interval_bound(low_val),
        "high": _parse_interval_bound(high_val),
        "low_closed": data.get("lowClosed", True),
        "high_closed": data.get("highClosed", True),
    }


def _parse_date_or_datetime(value: str | date | datetime | None) -> date | datetime | None:
    """Parse date or datetime from ISO string."""
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return value
    if not isinstance(value, str):
        _logger.warning("_parse_date_or_datetime expected str/date/datetime, got %s", type(value).__name__)
        return None
    try:
        if "T" in value:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        # Handle space-separated datetime from DuckDB CAST(TIMESTAMP AS VARCHAR)
        # e.g. "2024-10-01 00:00:00"
        if " " in value and ":" in value:
            return datetime.fromisoformat(value.replace(" ", "T").replace("Z", "+00:00"))
        return date.fromisoformat(value)
    except ValueError as e:
        _logger.warning("_parse_date_or_datetime failed: %s", e)
        return None


def intervalStart(interval: str | None) -> str | None:
    """Get the start of an interval.

    Per CQL spec: for a closed interval with null low boundary,
    returns the minimum value of the point type.
    For non-interval point values, returns the value itself.
    """
    if not interval:
        return None
    # Non-JSON values that look like dates/numbers are point values
    stripped = interval.strip()
    if not stripped.startswith('{'):
        return stripped if _POINT_VALUE_RE.match(stripped) else None
    iv = _parse_interval(interval)
    if not iv:
        return None
    if iv["low"] is None:
        # Check raw JSON for non-date low bound (e.g., integer strings)
        try:
            raw = orjson.loads(interval)
            raw_low = raw.get("low") or raw.get("start")
            if raw_low is not None:
                return str(raw_low)
        except JSONDecodeError as e:
            _logger.warning("intervalStart raw JSON fallback failed: %s", e)
        if iv.get("low_closed", True) and iv["high"] is not None:
            # CQL: closed interval with null low but real high → min value of point type
            return "0001-01-01T00:00:00.000+00:00"
        return None
    v = iv["low"]
    return v.isoformat() if isinstance(v, (date, datetime)) else str(v)


def intervalEnd(interval: str | None) -> str | None:
    """Get the end of an interval.

    Per CQL spec: for a closed interval with null high boundary,
    returns the maximum value of the point type.
    For non-interval point values, returns the value itself.
    """
    if not interval:
        return None
    # Non-JSON values that look like dates/numbers are point values
    stripped = interval.strip()
    if not stripped.startswith('{'):
        return stripped if _POINT_VALUE_RE.match(stripped) else None
    iv = _parse_interval(interval)
    if not iv:
        return None
    if iv["high"] is None:
        # Check raw JSON for non-date high bound (e.g., integer strings)
        try:
            raw = orjson.loads(interval)
            raw_high = raw.get("high") or raw.get("end")
            if raw_high is not None:
                return str(raw_high)
        except JSONDecodeError as e:
            _logger.warning("intervalEnd raw JSON fallback failed: %s", e)
        if iv.get("high_closed", True) and iv["low"] is not None:
            # CQL: closed interval with null high → max value of point type
            return "9999-12-31T23:59:59.999+00:00"
        return None
    v = iv["high"]
    return v.isoformat() if isinstance(v, (date, datetime)) else str(v)


def intervalWidth(interval: str | None) -> int | float | None:
    """Get the width of an interval (days for dates, numeric difference for numbers)."""
    iv = _parse_interval(interval)
    if not iv or iv["low"] is None or iv["high"] is None:
        return None

    low = iv["low"]
    high = iv["high"]

    # Numeric intervals
    if isinstance(low, (int, float)) and isinstance(high, (int, float)):
        return high - low

    # Convert to date for calculation
    if isinstance(low, datetime):
        low = low.date()
    if isinstance(high, datetime):
        high = high.date()

    return (high - low).days


def intervalContains(interval: str | None, point: str | None) -> bool | None:
    """Check if interval contains a point or another interval.

    Per CQL spec:
    - ``Interval<T> contains T`` → point containment
    - ``Interval<T> contains Interval<T>`` → equivalent to ``includes``

    The translator emits ``intervalContains(B, A)`` for both ``A during B``
    (interval in interval) and point-in-interval checks.  When *point* is
    actually an interval JSON string, delegate to ``intervalIncludes``.

    Returns None (NULL) for null/unparseable inputs per CQL three-valued logic.
    """
    if not point:
        return None

    # Detect whether the second argument is an interval (JSON object) or a
    # scalar point value.
    stripped = point.strip() if point else ""
    if stripped.startswith("{"):
        # Second argument is an interval → use "includes" semantics
        return intervalIncludes(interval, point)

    iv = _parse_interval(interval)
    pt = _parse_point(point)

    if not iv or pt is None:
        return None

    low, high = iv["low"], iv["high"]

    # Check bounds — None means unbounded (always satisfies that side)
    low_ok = True
    if low is not None:
        low_n, pt_low = _normalize_for_compare(low, pt)
        low_ok = pt_low >= low_n if iv["low_closed"] else pt_low > low_n
    high_ok = True
    if high is not None:
        pt_high, high_n = _normalize_for_compare(pt, high)
        high_ok = pt_high <= high_n if iv["high_closed"] else pt_high < high_n

    return low_ok and high_ok


def intervalProperlyContains(interval: str | None, point: str | None) -> bool | None:
    """Check if interval properly contains a point or another interval.

    When the second argument is an interval, delegates to
    ``intervalProperlyIncludes``.

    Returns None (NULL) for null/unparseable inputs per CQL three-valued logic.
    """
    if not point:
        return None

    stripped = point.strip() if point else ""
    if stripped.startswith("{"):
        return intervalProperlyIncludes(interval, point)

    iv = _parse_interval(interval)
    pt = _parse_point(point)

    if not iv or pt is None:
        return None

    low, high = iv["low"], iv["high"]

    # Proper contains = strict comparison; None bound means unbounded (strict always true)
    low_ok = True
    if low is not None:
        low_n, pt_low = _normalize_for_compare(low, pt)
        low_ok = pt_low > low_n
    high_ok = True
    if high is not None:
        pt_high, high_n = _normalize_for_compare(pt, high)
        high_ok = pt_high < high_n
    return low_ok and high_ok


def _normalize_for_compare(a, b):
    """Normalize date/datetime pair for comparison.
    
    Per CQL spec, when comparing values of different precisions (date vs datetime),
    comparison is done at the precision of the less precise operand. So when one is
    a date and the other is a datetime, we truncate the datetime to date precision.
    """
    # Guard: incompatible types (e.g. datetime vs int) cannot be compared.
    # Coerce the int to a date (treating it as a year) when the other is a date/datetime.
    if isinstance(a, (date, datetime)) and isinstance(b, int):
        b = date(b, 1, 1)
    elif isinstance(b, (date, datetime)) and isinstance(a, int):
        a = date(a, 1, 1)

    if isinstance(a, datetime) and isinstance(b, date) and not isinstance(b, datetime):
        a = a.date() if isinstance(a, datetime) else a
    elif isinstance(b, datetime) and isinstance(a, date) and not isinstance(a, datetime):
        b = b.date() if isinstance(b, datetime) else b
    # Normalize timezone awareness: strip tzinfo if one is aware and other is naive
    if isinstance(a, datetime) and isinstance(b, datetime):
        if a.tzinfo is not None and b.tzinfo is None:
            a = a.replace(tzinfo=None)
        elif b.tzinfo is not None and a.tzinfo is None:
            b = b.replace(tzinfo=None)
    return a, b


def intervalOverlaps(interval1: str | None, interval2: str | None) -> bool | None:
    """Check if two intervals overlap.

    Returns None (NULL) for null/unparseable inputs per CQL three-valued logic.
    """
    iv1 = _parse_interval(interval1)
    iv2 = _parse_interval(interval2)

    if not iv1 or not iv2:
        return None

    # Intervals overlap if neither ends before the other starts
    # (end1 >= start2) AND (end2 >= start1)
    # If any bound is None, treat as unbounded (always satisfies that side)
    if iv1["high"] is None or iv2["low"] is None:
        end1_after_start2 = True
    else:
        h1, l2 = _normalize_for_compare(iv1["high"], iv2["low"])
        # Both boundaries must be closed for equality to count as overlap
        end1_after_start2 = h1 > l2 if not (iv1["high_closed"] and iv2["low_closed"]) else h1 >= l2
    if iv2["high"] is None or iv1["low"] is None:
        end2_after_start1 = True
    else:
        h2, l1 = _normalize_for_compare(iv2["high"], iv1["low"])
        end2_after_start1 = h2 > l1 if not (iv2["high_closed"] and iv1["low_closed"]) else h2 >= l1

    return end1_after_start2 and end2_after_start1


def intervalBefore(interval1: str | None, interval2: str | None) -> bool | None:
    """Check if interval1 ends before interval2 starts.

    Returns None (NULL) for null/unparseable inputs per CQL three-valued logic.
    """
    iv1 = _parse_interval(interval1)
    iv2 = _parse_interval(interval2)

    if not iv1 or not iv2:
        return None

    # iv1.high < iv2.low (strictly before)
    if iv1["high"] is None or iv2["low"] is None:
        return None
    h1, l2 = _normalize_for_compare(iv1["high"], iv2["low"])
    if iv1["high_closed"] and iv2["low_closed"]:
        return h1 < l2
    else:
        return h1 <= l2


def intervalAfter(interval1: str | None, interval2: str | None) -> bool | None:
    """Check if interval1 starts after interval2 ends.

    Returns None (NULL) for null/unparseable inputs per CQL three-valued logic.
    """
    iv1 = _parse_interval(interval1)
    iv2 = _parse_interval(interval2)

    if not iv1 or not iv2:
        return None

    # iv1.low > iv2.high (strictly after)
    if iv1["low"] is None or iv2["high"] is None:
        return None
    l1, h2 = _normalize_for_compare(iv1["low"], iv2["high"])
    if iv1["low_closed"] and iv2["high_closed"]:
        return l1 > h2
    else:
        return l1 >= h2


def intervalMeets(interval1: str | None, interval2: str | None) -> bool | None:
    """Check if two intervals are contiguous (no gap, no overlap).

    Per CQL spec, meets is true when successor(end of X) == start of Y
    OR successor(end of Y) == start of X.

    Returns None (NULL) for null/unparseable inputs per CQL three-valued logic.
    """
    iv1 = _parse_interval(interval1)
    iv2 = _parse_interval(interval2)

    if not iv1 or not iv2:
        return None

    # Check iv1 meets iv2: successor(effective end of iv1) == effective start of iv2
    end1 = _effective_end(iv1)
    start2 = _effective_start(iv2)
    if end1 is not None and start2 is not None:
        succ = _successor(end1)
        if succ is not None:
            s, t = _normalize_for_compare(succ, start2)
            if s == t:
                return True

    # Check iv2 meets iv1: successor(effective end of iv2) == effective start of iv1
    end2 = _effective_end(iv2)
    start1 = _effective_start(iv1)
    if end2 is not None and start1 is not None:
        succ = _successor(end2)
        if succ is not None:
            s, t = _normalize_for_compare(succ, start1)
            if s == t:
                return True

    return False


def intervalIncludes(interval1: str | None, interval2: str | None) -> bool | None:
    """Check if interval1 fully includes interval2.

    Respects open/closed boundaries per CQL spec.
    Returns None (NULL) for null/unparseable inputs per CQL three-valued logic.
    """
    iv1 = _parse_interval(interval1)
    iv2 = _parse_interval(interval2)
    if not iv1 or not iv2:
        return None
    # Use effective boundaries (accounts for open/closed)
    start1 = _effective_start(iv1)
    end1 = _effective_end(iv1)
    start2 = _effective_start(iv2)
    end2 = _effective_end(iv2)
    if start1 is None or end1 is None or start2 is None or end2 is None:
        return None
    s1, s2 = _normalize_for_compare(start1, start2)
    e1, e2 = _normalize_for_compare(end1, end2)
    return s1 <= s2 and e1 >= e2


def intervalIncludedIn(interval1: str | None, interval2: str | None) -> bool:
    """Check if interval1 is included in interval2."""
    return intervalIncludes(interval2, interval1)


def intervalProperlyIncludes(interval1: str | None, interval2: str | None) -> bool | None:
    """Check if interval1 properly includes interval2 (includes AND not equal).

    Respects open/closed boundaries per CQL spec.
    Returns None (NULL) for null/unparseable inputs per CQL three-valued logic.
    """
    iv1 = _parse_interval(interval1)
    iv2 = _parse_interval(interval2)
    if not iv1 or not iv2:
        return None
    start1 = _effective_start(iv1)
    end1 = _effective_end(iv1)
    start2 = _effective_start(iv2)
    end2 = _effective_end(iv2)
    if start1 is None or end1 is None or start2 is None or end2 is None:
        return None
    s1, s2 = _normalize_for_compare(start1, start2)
    e1, e2 = _normalize_for_compare(end1, end2)
    includes = s1 <= s2 and e1 >= e2
    is_equal = s1 == s2 and e1 == e2
    return includes and not is_equal


def intervalProperlyIncludedIn(interval1: str | None, interval2: str | None) -> bool:
    """Check if interval1 is properly included in interval2."""
    return intervalProperlyIncludes(interval2, interval1)


def intervalOverlapsBefore(interval1: str | None, interval2: str | None) -> bool | None:
    """Check if interval1 overlaps interval2 and starts before it (CQL overlaps before).

    Returns None (NULL) for null/unparseable inputs per CQL three-valued logic.
    """
    iv1 = _parse_interval(interval1)
    iv2 = _parse_interval(interval2)
    if not iv1 or not iv2:
        return None
    # Must overlap AND iv1 starts before iv2
    overlaps = intervalOverlaps(interval1, interval2)
    if not overlaps:
        return False
    # Compare starts: None low means -infinity (always before)
    if iv1["low"] is None:
        return True  # -infinity is before any start
    if iv2["low"] is None:
        return False  # can't start before -infinity
    l1, l2 = _normalize_for_compare(iv1["low"], iv2["low"])
    return l1 < l2


def intervalOverlapsAfter(interval1: str | None, interval2: str | None) -> bool | None:
    """Check if interval1 overlaps interval2 and ends after it (CQL overlaps after).

    Returns None (NULL) for null/unparseable inputs per CQL three-valued logic.
    """
    iv1 = _parse_interval(interval1)
    iv2 = _parse_interval(interval2)
    if not iv1 or not iv2:
        return None
    # Must overlap AND iv1 ends after iv2
    overlaps = intervalOverlaps(interval1, interval2)
    if not overlaps:
        return False
    # Compare ends: None high means +infinity (always after)
    if iv1["high"] is None:
        return True  # +infinity is after any end
    if iv2["high"] is None:
        return False  # can't end after +infinity
    h1, h2 = _normalize_for_compare(iv1["high"], iv2["high"])
    return h1 > h2


def intervalMeetsBefore(interval1: str | None, interval2: str | None) -> bool | None:
    """Check if interval1 meets interval2 from before (successor(end1) == start2).

    Uses CQL successor semantics for contiguity.
    Returns None (NULL) for null/unparseable inputs per CQL three-valued logic.
    """
    iv1 = _parse_interval(interval1)
    iv2 = _parse_interval(interval2)
    if not iv1 or not iv2:
        return None
    end1 = _effective_end(iv1)
    start2 = _effective_start(iv2)
    if end1 is None or start2 is None:
        return None
    succ = _successor(end1)
    if succ is None:
        return None
    s, t = _normalize_for_compare(succ, start2)
    return s == t


def intervalMeetsAfter(interval1: str | None, interval2: str | None) -> bool:
    """Check if interval2 ends exactly when interval1 starts (iv2 meets iv1 from before)."""
    return intervalMeetsBefore(interval2, interval1)


def intervalStartsSame(interval1: str | None, interval2: str | None) -> bool | None:
    """Check if two intervals start at the same point.

    Returns None (NULL) for null/unparseable inputs per CQL three-valued logic.
    """
    iv1 = _parse_interval(interval1)
    iv2 = _parse_interval(interval2)
    if not iv1 or not iv2:
        return None
    if iv1["low"] is None or iv2["low"] is None:
        return None
    return iv1["low"] == iv2["low"]


def intervalEndsSame(interval1: str | None, interval2: str | None) -> bool | None:
    """Check if two intervals end at the same point.

    Returns None (NULL) for null/unparseable inputs per CQL three-valued logic.
    """
    iv1 = _parse_interval(interval1)
    iv2 = _parse_interval(interval2)
    if not iv1 or not iv2:
        return None
    if iv1["high"] is None or iv2["high"] is None:
        return None
    return iv1["high"] == iv2["high"]


def intervalFromBounds(low: str | None, high: str | None, lowClosed: bool = True, highClosed: bool = False) -> str | None:
    """Create an interval from bounds."""
    import json
    return json.dumps({
        "low": low,
        "high": high,
        "lowClosed": lowClosed,
        "highClosed": highClosed
    })


def collapse_intervals(intervals_json: str | None) -> str | None:
    """Collapse a list of intervals into non-overlapping, merged intervals.

    In CQL, ``collapse`` merges overlapping or adjacent intervals into a
    minimal set of disjoint intervals.

    Args:
        intervals_json: JSON array of interval objects, each with
            ``low``, ``high``, ``lowClosed``, ``highClosed`` keys.

    Returns:
        JSON array of collapsed interval objects, or None on invalid input.
    """
    import json as _json

    if not intervals_json:
        return None
    try:
        raw_list = orjson.loads(intervals_json)
    except JSONDecodeError as e:
        _logger.warning("collapse_intervals JSON parse failed: %s", e)
        return None
    if not isinstance(raw_list, list) or len(raw_list) == 0:
        return None

    parsed = []
    for item in raw_list:
        if isinstance(item, str):
            iv = _parse_interval(item)
        elif isinstance(item, dict):
            low_val = item.get("low") or item.get("start")
            high_val = item.get("high") or item.get("end")
            iv = {
                "low": _parse_interval_bound(low_val),
                "high": _parse_interval_bound(high_val),
                "low_closed": item.get("lowClosed", True),
                "high_closed": item.get("highClosed", True),
            }
        else:
            iv = None
        if iv and iv["low"] is not None:
            parsed.append(iv)

    if not parsed:
        return None

    parsed.sort(key=lambda x: x["low"])

    merged: list[dict] = [parsed[0]]
    for current in parsed[1:]:
        last = merged[-1]
        # None high means open-ended (extends to infinity) — absorbs everything
        if last["high"] is None:
            continue
        if current["low"] is None:
            if current["high"] is None or current["high"] >= last["high"]:
                last["high"] = current["high"]
                last["high_closed"] = current.get("high_closed", True)
            continue
        last_high, cur_low = _normalize_for_compare(last["high"], current["low"])
        if last_high >= cur_low:
            if current["high"] is None:
                last["high"] = None
                last["high_closed"] = current.get("high_closed", True)
            else:
                _, cur_high = _normalize_for_compare(last["high"], current["high"])
                last_h_norm, _ = _normalize_for_compare(last["high"], current["high"])
                if cur_high > last_h_norm:
                    last["high"] = current["high"]
                    last["high_closed"] = current["high_closed"]
                elif cur_high == last_h_norm:
                    last["high_closed"] = last["high_closed"] or current["high_closed"]
        else:
            merged.append(current)

    result = []
    for iv in merged:
        result.append({
            "low": str(iv["low"]) if iv["low"] is not None else None,
            "high": str(iv["high"]) if iv["high"] is not None else None,
            "lowClosed": iv["low_closed"],
            "highClosed": iv["high_closed"],
        })
    return _json.dumps(result)


# ========================================
# Registration
# ========================================

def registerIntervalUdfs(con: "duckdb.DuckDBPyConnection") -> None:
    """Register all interval UDFs."""
    # Many interval UDFs legitimately return None (e.g. intervalStart on
    # malformed input), so use null_handling="special" for all of them.
    con.create_function("intervalStart", intervalStart, null_handling="special")
    con.create_function("intervalEnd", intervalEnd, null_handling="special")
    con.create_function("intervalWidth", intervalWidth, null_handling="special")
    con.create_function("intervalContains", intervalContains, null_handling="special")
    con.create_function("intervalProperlyContains", intervalProperlyContains, null_handling="special")
    con.create_function("intervalOverlaps", intervalOverlaps, null_handling="special")
    con.create_function("intervalBefore", intervalBefore, null_handling="special")
    con.create_function("intervalAfter", intervalAfter, null_handling="special")
    con.create_function("intervalMeets", intervalMeets, null_handling="special")
    con.create_function("intervalIncludes", intervalIncludes, null_handling="special")
    con.create_function("intervalIncludedIn", intervalIncludedIn, null_handling="special")
    con.create_function("intervalProperlyIncludes", intervalProperlyIncludes, null_handling="special")
    con.create_function("intervalProperlyIncludedIn", intervalProperlyIncludedIn, null_handling="special")
    con.create_function("intervalOverlapsBefore", intervalOverlapsBefore, null_handling="special")
    con.create_function("intervalOverlapsAfter", intervalOverlapsAfter, null_handling="special")
    con.create_function("intervalMeetsBefore", intervalMeetsBefore, null_handling="special")
    con.create_function("intervalMeetsAfter", intervalMeetsAfter, null_handling="special")
    con.create_function("intervalStartsSame", intervalStartsSame, null_handling="special")
    con.create_function("intervalEndsSame", intervalEndsSame, null_handling="special")
    con.create_function("intervalFromBounds", intervalFromBounds, null_handling="special")
    con.create_function("collapse_intervals", collapse_intervals, null_handling="special")


__all__ = [
    "registerIntervalUdfs",
    "intervalStart",
    "intervalEnd",
    "intervalWidth",
    "intervalContains",
    "intervalProperlyContains",
    "intervalOverlaps",
    "intervalBefore",
    "intervalAfter",
    "intervalMeets",
    "intervalIncludes",
    "intervalIncludedIn",
    "intervalProperlyIncludes",
    "intervalProperlyIncludedIn",
    "intervalOverlapsBefore",
    "intervalOverlapsAfter",
    "intervalMeetsBefore",
    "intervalMeetsAfter",
    "intervalStartsSame",
    "intervalEndsSame",
    "intervalFromBounds",
    "collapse_intervals",
]
