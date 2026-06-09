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
import math
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any

import orjson
from orjson import JSONDecodeError

if TYPE_CHECKING:
    import duckdb


import logging

_logger = logging.getLogger(__name__)
_DECIMAL_STEP = Decimal("0.00000001")


def _decimal_step(value: float, direction: int) -> float:
    return float(Decimal(str(value)) + (_DECIMAL_STEP * direction))


def _format_decimal(value: float) -> str:
    if abs(value) < 5e-13:
        value = 0.0
    text = f"{value:.8f}".rstrip("0")
    if text.endswith("."):
        text += "0"
    return text


def _quantity_bound(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict) or "value" not in value:
        return None
    try:
        numeric = float(value["value"])
    except (TypeError, ValueError):
        return None
    try:
        quantity_json = orjson.dumps(value).decode("utf-8")
    except (TypeError, ValueError):
        return None
    return {
        "__cql_quantity_json__": quantity_json,
        "__cql_quantity_value__": numeric,
    }


def _is_quantity_bound(value: Any) -> bool:
    return isinstance(value, dict) and "__cql_quantity_json__" in value


def _quantity_json(value: Any) -> str | None:
    if _is_quantity_bound(value):
        return value["__cql_quantity_json__"]
    if isinstance(value, dict) and "value" in value:
        bound = _quantity_bound(value)
        return bound["__cql_quantity_json__"] if bound else None
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.startswith("{") and '"value"' in stripped:
            try:
                parsed = orjson.loads(stripped)
            except (JSONDecodeError, TypeError, ValueError):
                return None
            bound = _quantity_bound(parsed) if isinstance(parsed, dict) else None
            return bound["__cql_quantity_json__"] if bound else None
    return None


def _quantity_numeric(value: Any) -> float | None:
    if _is_quantity_bound(value):
        return float(value["__cql_quantity_value__"])
    quantity_json = _quantity_json(value)
    if quantity_json is None:
        return None
    try:
        parsed = orjson.loads(quantity_json)
        return float(parsed["value"])
    except (JSONDecodeError, KeyError, TypeError, ValueError):
        return None


def _quantity_bound_with_numeric(value: Any, numeric: float) -> Any:
    quantity_json = _quantity_json(value)
    if quantity_json is None:
        return numeric
    try:
        parsed = orjson.loads(quantity_json)
    except (JSONDecodeError, TypeError, ValueError):
        return numeric
    if not isinstance(parsed, dict):
        return numeric
    parsed["value"] = numeric
    return _quantity_bound(parsed) or numeric


def _format_bound_output(value: Any) -> Any:
    if _is_quantity_bound(value):
        return value["__cql_quantity_json__"]
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def _successor(value: Any) -> Any:
    """CQL successor: smallest value greater than the given value.

    Step sizes per CQL §22.26:
    - Integer/Long: +1
    - Decimal (Python float): +10^-8 (CQL minimum Decimal step)
    - Date: +1 day
    - DateTime: +1 ms
    """
    if isinstance(value, int):
        return value + 1
    if isinstance(value, float):
        # CQL Decimal minimum step is 10^-8
        return _decimal_step(value, 1)
    if _is_quantity_bound(value):
        numeric = _quantity_numeric(value)
        return _quantity_bound_with_numeric(value, numeric + 1e-8) if numeric is not None else None
    if isinstance(value, datetime):
        return value + timedelta(milliseconds=1)
    if isinstance(value, date) and not isinstance(value, datetime):
        return value + timedelta(days=1)
    return None


def _predecessor(value: Any) -> Any:
    """CQL predecessor: largest value less than the given value.

    Step sizes per CQL §22.25:
    - Integer/Long: -1
    - Decimal (Python float): -10^-8 (CQL minimum Decimal step)
    - Date: -1 day
    - DateTime: -1 ms
    """
    if isinstance(value, int):
        return value - 1
    if isinstance(value, float):
        # CQL Decimal minimum step is 10^-8
        return _decimal_step(value, -1)
    if _is_quantity_bound(value):
        numeric = _quantity_numeric(value)
        return _quantity_bound_with_numeric(value, numeric - 1e-8) if numeric is not None else None
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
    return _predecessor_for_bound(iv["high"], iv.get("high_raw"))


def _effective_start(iv: dict) -> Any:
    """Get the first value contained in the interval (handles open/closed)."""
    if iv["low"] is None:
        return None
    if iv.get("low_closed", True):
        return iv["low"]
    return _successor_for_bound(iv["low"], iv.get("low_raw"))
# Pattern matching valid point values: dates, datetimes, numbers
_POINT_VALUE_RE = re.compile(
    r'^\d{4}(-\d{2}(-\d{2}(T\d{2}:\d{2}(:\d{2})?)?)?)?([+-]\d{2}:\d{2}|Z)?$'
    r'|^-?\d+(\.\d+)?$'
)


def _is_day_precision_datetime_string(value: Any) -> bool:
    """Return True for CQL day-precision DateTime strings like YYYY-MM-DDT."""
    if not isinstance(value, str):
        return False
    stripped = value.strip()
    return (
        len(stripped) == 11
        and stripped.endswith("T")
        and stripped[4] == "-"
        and stripped[7] == "-"
        and stripped[:4].isdigit()
        and stripped[5:7].isdigit()
        and stripped[8:10].isdigit()
    )


def _is_time_like_string(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    stripped = value.strip()
    bare = stripped[1:] if stripped.startswith("T") else stripped
    return (
        len(bare) >= 2
        and bare[:2].isdigit()
        and (
            stripped.startswith("T")
            or (":" in bare and "-" not in bare)
        )
    )


def _temporal_precision_from_raw(raw_value: Any) -> str | None:
    if not isinstance(raw_value, str):
        return None
    stripped = raw_value.strip()
    if not stripped:
        return None
    looks_temporal = _is_time_like_string(stripped) or (
        len(stripped) >= 4
        and stripped[:4].isdigit()
        and (len(stripped) == 4 or stripped[4] in ("-", "T", " "))
    )
    if not looks_temporal:
        return None
    try:
        from .datetime import _infer_precision
        return _infer_precision(stripped)
    except (KeyError, TypeError, ValueError):
        return None


def _add_temporal_precision_step(value: Any, raw_value: Any, direction: int) -> Any | None:
    """Step Date/DateTime/Time values by their authored CQL precision."""
    precision = _temporal_precision_from_raw(raw_value)
    if precision is None:
        return None
    if isinstance(value, int) and not isinstance(value, bool) and _is_time_like_string(raw_value):
        steps = {
            "hour": 60 * 60 * 1000,
            "minute": 60 * 1000,
            "second": 1000,
            "millisecond": 1,
        }
        step = steps.get(precision)
        return value + (direction * step) if step is not None else None
    if isinstance(value, (date, datetime)):
        try:
            if precision == "year":
                from dateutil.relativedelta import relativedelta
                return value + relativedelta(years=direction)
            if precision == "month":
                from dateutil.relativedelta import relativedelta
                return value + relativedelta(months=direction)
            if precision == "day":
                return value + timedelta(days=direction)
            if precision == "hour":
                return value + timedelta(hours=direction)
            if precision == "minute":
                return value + timedelta(minutes=direction)
            if precision == "second":
                return value + timedelta(seconds=direction)
            if precision == "millisecond":
                return value + timedelta(milliseconds=direction)
        except (OverflowError, ValueError):
            return None
    return None


def _format_day_precision_datetime(value: date | datetime) -> str:
    return f"{value.year:04d}-{value.month:02d}-{value.day:02d}T"


def _format_adjusted_bound_for_raw(value: Any, raw_value: Any = None) -> Any:
    if _is_quantity_bound(value):
        return value["__cql_quantity_json__"]
    if isinstance(value, datetime):
        if _is_day_precision_datetime_string(raw_value):
            return _format_day_precision_datetime(value)
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return value


def _successor_for_bound(value: Any, raw_value: Any = None) -> Any:
    """Return successor using raw precision markers when available."""
    temporal_step = _add_temporal_precision_step(value, raw_value, 1)
    if temporal_step is not None:
        return temporal_step
    return _successor(value)


def _predecessor_for_bound(value: Any, raw_value: Any = None) -> Any:
    """Return predecessor using raw precision markers when available."""
    temporal_step = _add_temporal_precision_step(value, raw_value, -1)
    if temporal_step is not None:
        return temporal_step
    return _predecessor(value)


def _parse_interval_bound(value: Any) -> Any:
    """Parse string/date-like interval bounds, preserving non-string scalars.

    Handles numeric strings (integers/decimals) in addition to dates/datetimes.
    Date parsing is tried first so that year-only strings like "2024" are not
    misinterpreted as integers.
    The sentinel ``__null__`` means "unbounded" (typed null bound).
    """
    if value is None:
        return None
    if isinstance(value, str) and value == "__null__":
        return None
    if isinstance(value, dict):
        # Quantity or other structured JSON passed directly by DuckDB
        bound = _quantity_bound(value)
        if bound is not None:
            return bound
        return None
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        # Quantity JSON: extract numeric value for comparison
        stripped = value.strip()
        if stripped.startswith('{') and '"value"' in stripped:
            try:
                q = orjson.loads(stripped)
                bound = _quantity_bound(q) if isinstance(q, dict) else None
                if bound is not None:
                    return bound
            except (JSONDecodeError, TypeError, ValueError):
                pass
        # Time-only values: full (HH:MM:SS) or partial (THH, THH:MM)
        # Partial time strings arise from precision truncation (e.g., "hour of @T10:30")
        if ((':' in stripped and '-' not in stripped and not stripped.startswith('{'))
                or (stripped.startswith('T') and len(stripped) >= 3 and stripped[1:3].isdigit())):
            from datetime import time as _time_type
            t_str = stripped.lstrip('T').strip()
            try:
                # Pad partial time strings: 'HH' → 'HH:00:00', 'HH:MM' → 'HH:MM:00'
                if len(t_str) == 2 and t_str.isdigit():
                    t_str = f"{t_str}:00:00"
                elif len(t_str) == 5 and t_str[2] == ':':
                    t_str = f"{t_str}:00"
                t = _time_type.fromisoformat(t_str)
                return t.hour * 3600000 + t.minute * 60000 + t.second * 1000 + t.microsecond // 1000
            except (ValueError, TypeError):
                pass
        # Try date/datetime first so year-only dates like "2024" aren't
        # mistaken for integers.
        parsed = _parse_date_or_datetime(value)
        if parsed is not None:
            return parsed
        # Then try numeric parsing (integers/decimals)
        try:
            if '.' in value and 'T' not in value and '-' not in value[1:]:
                return float(value)
            if stripped.lstrip('-').isdigit():
                return int(stripped)
        except (ValueError, OverflowError):
            pass
    return value


def _parse_point(value: str | None) -> Any:
    """Parse a point value which may be a date, datetime, time, integer, decimal, or quantity."""
    if value is None:
        return None
    if not isinstance(value, str):
        return value
    stripped = value.strip()
    if not stripped:
        return None
    # Quantity JSON: extract numeric value for comparison
    if stripped.startswith('{') and '"value"' in stripped:
        try:
            q = orjson.loads(stripped)
            bound = _quantity_bound(q) if isinstance(q, dict) else None
            if bound is not None:
                return bound
        except (JSONDecodeError, TypeError, ValueError):
            pass
    # Time-only values: full (HH:MM:SS) or partial (THH, THH:MM)
    if ((':' in stripped and '-' not in stripped and not stripped.startswith('{'))
            or (stripped.startswith('T') and len(stripped) >= 3 and stripped[1:3].isdigit())):
        from datetime import time as _time_type
        t_str = stripped.lstrip('T').strip()
        try:
            # Pad partial time strings
            if len(t_str) == 2 and t_str.isdigit():
                t_str = f"{t_str}:00:00"
            elif len(t_str) == 5 and t_str[2] == ':':
                t_str = f"{t_str}:00"
            # Normalize fractional seconds
            if '.' in t_str:
                base, frac = t_str.split('.', 1)
                frac = frac.ljust(6, '0')[:6]
                t_str = f"{base}.{frac}"
            t = _time_type.fromisoformat(t_str)
            return t.hour * 3600000 + t.minute * 60000 + t.second * 1000 + t.microsecond // 1000
        except (ValueError, TypeError):
            pass
    # Try numeric
    try:
        if '.' in stripped and 'T' not in stripped and '-' not in stripped[1:] and ':' not in stripped:
            return float(stripped)
        if stripped.lstrip('-').isdigit():
            return int(stripped)
    except (ValueError, OverflowError):
        pass
    # Then try date/datetime
    return _parse_date_or_datetime(stripped)


def _parse_interval(value: str) -> dict | None:
    """Parse interval JSON to dict with date objects.

    For discrete types (int, date, datetime), open bounds are normalized
    to equivalent closed bounds (CQL §2.17).  E.g. Interval(3, 10] for
    integers becomes effectively [4, 10] so that all comparison functions
    use a single closed-bound code path.
    """
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

    # Warn on common snake_case key mistakes and accept them
    _SNAKE_TO_CAMEL = {"low_closed": "lowClosed", "high_closed": "highClosed"}
    for snake, camel in _SNAKE_TO_CAMEL.items():
        if snake in data and camel not in data:
            _logger.warning(
                "_parse_interval: found '%s' (snake_case); use '%s' (camelCase) instead. "
                "Accepting the value.", snake, camel,
            )
            data[camel] = data[snake]

    # Support both CQL interval format (low/high) and FHIR Period (start/end)
    low_val = data.get("low") if "low" in data else data.get("start")
    high_val = data.get("high") if "high" in data else data.get("end")
    low = _parse_interval_bound(low_val)
    high = _parse_interval_bound(high_val)
    low_closed = data.get("lowClosed", True)
    high_closed = data.get("highClosed", True)

    # Normalize open bounds to closed for discrete (point) types.
    # Integer: successor/predecessor is ±1
    # Date: successor/predecessor is ±1 day
    # DateTime: successor/predecessor is ±1 millisecond
    low_raw = low_val
    high_raw = high_val
    low_was_open = low is not None and not low_closed
    high_was_open = high is not None and not high_closed
    if low is not None and not low_closed:
        if isinstance(low, int):
            low = low + 1
            low_closed = True
            low_raw = str(low)
        elif isinstance(low, float):
            low = _decimal_step(low, 1)
            low_closed = True
            low_raw = _format_decimal(low)
        elif _is_quantity_bound(low):
            adjusted = _successor_for_bound(low, low_val)
            if adjusted is not None:
                low = adjusted
                low_closed = True
                low_raw = _quantity_json(adjusted) or adjusted
        elif isinstance(low, date) and not isinstance(low, datetime):
            low = low + timedelta(days=1)
            low_closed = True
            low_raw = low.isoformat()
        elif isinstance(low, datetime):
            low = _successor_for_bound(low, low_val)
            low_closed = True
            low_raw = _format_adjusted_bound_for_raw(low, low_val)
    if high is not None and not high_closed:
        if isinstance(high, int):
            high = high - 1
            high_closed = True
            high_raw = str(high)
        elif isinstance(high, float):
            high = _decimal_step(high, -1)
            high_closed = True
            high_raw = _format_decimal(high)
        elif _is_quantity_bound(high):
            adjusted = _predecessor_for_bound(high, high_val)
            if adjusted is not None:
                high = adjusted
                high_closed = True
                high_raw = _quantity_json(adjusted) or adjusted
        elif isinstance(high, date) and not isinstance(high, datetime):
            high = high - timedelta(days=1)
            high_closed = True
            high_raw = high.isoformat()
        elif isinstance(high, datetime):
            high = _predecessor_for_bound(high, high_val)
            high_closed = True
            high_raw = _format_adjusted_bound_for_raw(high, high_val)

    return {
        "low": low,
        "high": high,
        "low_closed": low_closed,
        "high_closed": high_closed,
        "low_raw": low_raw,
        "high_raw": high_raw,
        "low_was_open": low_was_open,
        "high_was_open": high_was_open,
    }


def _raw_closed_bound(interval: str, primary_key: str, fhir_key: str, closed_key: str) -> str | None:
    """Return an explicit closed/default-closed raw interval bound.

    This avoids the full interval parser for common FHIR Period JSON such as
    {"start": "...", "end": "..."} while preserving fallback behavior for
    open bounds, null bounds, malformed JSON, and non-object values.
    """
    try:
        raw = orjson.loads(interval)
    except JSONDecodeError:
        return None
    if not isinstance(raw, dict):
        return None
    if raw.get(closed_key, True) is not True:
        return None
    raw_bound = raw.get(primary_key)
    if raw_bound is None:
        raw_bound = raw.get(fhir_key)
    if raw_bound is None:
        return None
    if raw_bound == "__null__":
        return None
    return raw_bound if isinstance(raw_bound, str) else str(raw_bound)


def _authored_closed_temporal_raw(iv: dict, raw_key: str, closed_key: str, open_key: str) -> str | None:
    """Return an authored closed temporal bound for uncertainty-aware comparison.

    Bounds normalized from an authored open boundary are effective endpoints,
    so compare their parsed values instead of reclassifying the computed value
    as an authored partial-precision literal.
    """
    raw_value = iv.get(raw_key)
    if not iv.get(closed_key, True) or iv.get(open_key, False):
        return None
    return raw_value if _is_temporal_string(raw_value) else None


def _parse_date_or_datetime(value: str | date | datetime | None) -> date | datetime | None:
    """Parse date or datetime from ISO string.

    Handles partial-precision ISO 8601 strings (year-only, year-month)
    by padding to full date.  Precision information is lost — callers
    that need precision should use the dedicated cql* UDFs instead.
    """
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
        # Normalize partial fractional seconds (.4 → .400000) for Python 3.10 compat
        val = value.strip()

        # Handle partial-precision ISO 8601 strings
        # Year-only: '2014' → date(2014, 1, 1)
        if len(val) == 4 and val.isdigit():
            return date(int(val), 1, 1)
        # Year-month: '2014-01' → date(2014, 1, 1)
        if len(val) == 7 and val[4] == '-' and val[:4].isdigit() and val[5:7].isdigit():
            return date(int(val[:4]), int(val[5:7]), 1)
        # Day-precision DateTime: '2014-01-15T' → datetime(2014, 1, 15)
        if _is_day_precision_datetime_string(val):
            parsed_date = date.fromisoformat(val[:10])
            return datetime(parsed_date.year, parsed_date.month, parsed_date.day)

        if '.' in val:
            # Find the fractional part and pad to 6 digits
            dot_idx = val.rindex('.')
            # Find end of fractional digits
            end = dot_idx + 1
            while end < len(val) and val[end].isdigit():
                end += 1
            frac = val[dot_idx+1:end]
            frac = frac.ljust(6, '0')[:6]
            val = val[:dot_idx+1] + frac + val[end:]
        if "T" in val:
            return datetime.fromisoformat(val.replace("Z", "+00:00"))
        # Handle space-separated datetime from DuckDB CAST(TIMESTAMP AS VARCHAR)
        # e.g. "2024-10-01 00:00:00"
        if " " in val and ":" in val:
            return datetime.fromisoformat(val.replace(" ", "T").replace("Z", "+00:00"))
        return date.fromisoformat(val)
    except ValueError as e:
        _logger.debug("_parse_date_or_datetime failed: %s", e)
        return None


def _cql_minimum_for_peer_bound(peer: Any, raw_peer: Any) -> str | None:
    """Return CQL point-type minimum for a closed null low boundary."""
    if _is_time_like_string(raw_peer):
        return "T00:00:00.000"
    if isinstance(peer, bool):
        return None
    if isinstance(peer, int):
        return "-2147483648"
    if isinstance(peer, float):
        return "-99999999999999999999.99999999"
    if _is_quantity_bound(peer):
        return None
    if isinstance(peer, datetime):
        if isinstance(raw_peer, str) and ("T" in raw_peer or " " in raw_peer):
            return "0001-01-01T00:00:00.000+00:00"
        return "0001-01-01"
    if isinstance(peer, date):
        return "0001-01-01"
    return None


def _cql_maximum_for_peer_bound(peer: Any, raw_peer: Any) -> str | None:
    """Return CQL point-type maximum for a closed null high boundary."""
    if _is_time_like_string(raw_peer):
        return "T23:59:59.999"
    if isinstance(peer, bool):
        return None
    if isinstance(peer, int):
        return "2147483647"
    if isinstance(peer, float):
        return "99999999999999999999.99999999"
    if _is_quantity_bound(peer):
        return None
    if isinstance(peer, datetime):
        if isinstance(raw_peer, str) and ("T" in raw_peer or " " in raw_peer):
            return "9999-12-31T23:59:59.999+00:00"
        return "9999-12-31"
    if isinstance(peer, date):
        return "9999-12-31"
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
    raw_low = _raw_closed_bound(interval, "low", "start", "lowClosed")
    if raw_low is not None:
        return raw_low
    iv = _parse_interval(interval)
    if not iv:
        return None
    if iv["low"] is None:
        try:
            raw = orjson.loads(interval)
            raw_low = raw.get("low") or raw.get("start")
            if raw_low is not None and raw_low != "__null__":
                return str(raw_low)
        except JSONDecodeError:
            pass
        if iv.get("low_closed", True) and iv["high"] is not None:
            return _cql_minimum_for_peer_bound(iv["high"], iv.get("high_raw"))
        return None
    # Return raw bound values only when the authored boundary was closed.
    # _parse_interval normalizes open discrete bounds to closed effective
    # bounds, so iv["low_closed"] no longer tells us whether the source bound
    # was open.
    try:
        raw = orjson.loads(interval)
        raw_low = raw.get("low") or raw.get("start")
        if raw.get("lowClosed", True) is True and raw_low is not None:
            return str(raw_low) if not isinstance(raw_low, str) else raw_low
    except JSONDecodeError:
        pass
    v = _effective_start(iv)
    if v is None:
        return None
    if isinstance(v, float):
        return _format_decimal(v)
    formatted = _format_adjusted_bound_for_raw(v, iv.get("low_raw"))
    return formatted if isinstance(formatted, str) else str(formatted)


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
    raw_high = _raw_closed_bound(interval, "high", "end", "highClosed")
    if raw_high is not None:
        return raw_high
    iv = _parse_interval(interval)
    if not iv:
        return None
    if iv["high"] is None:
        try:
            raw = orjson.loads(interval)
            raw_high = raw.get("high") or raw.get("end")
            if raw_high is not None and raw_high != "__null__":
                return str(raw_high)
        except JSONDecodeError:
            pass
        if iv.get("high_closed", True) and iv["low"] is not None:
            return _cql_maximum_for_peer_bound(iv["low"], iv.get("low_raw"))
        return None
    try:
        raw = orjson.loads(interval)
        raw_high = raw.get("high") or raw.get("end")
        if raw.get("highClosed", True) is True and raw_high is not None:
            return str(raw_high) if not isinstance(raw_high, str) else raw_high
    except JSONDecodeError:
        pass
    v = _effective_end(iv)
    if v is None:
        return None
    if isinstance(v, float):
        return _format_decimal(v)
    formatted = _format_adjusted_bound_for_raw(v, iv.get("high_raw"))
    return formatted if isinstance(formatted, str) else str(formatted)


def pointFrom(interval: str | None) -> str | None:
    """CQL §19.22: Extract the single point from a unit interval.

    If the interval is a unit interval after applying CQL Start/End effective
    boundary semantics, returns the point value. Otherwise returns null.
    """
    iv = _parse_interval(interval)
    if not iv or iv["low"] is None or iv["high"] is None:
        return None

    low = _effective_start(iv)
    high = _effective_end(iv)
    if low is None or high is None:
        return None

    cmp_low, cmp_high = _normalize_for_compare(low, high)
    if isinstance(cmp_low, float) or isinstance(cmp_high, float):
        if abs(float(cmp_low) - float(cmp_high)) > 5e-13:
            return None
    elif cmp_low != cmp_high:
        return None

    formatted = _format_adjusted_bound_for_raw(low, iv.get("low_raw"))
    if isinstance(formatted, (date, datetime)):
        return formatted.isoformat()
    if isinstance(formatted, float):
        return _format_decimal(formatted)
    return str(formatted)


def intervalWidth(interval: str | None) -> str | None:
    """Get the width of an interval (numeric difference for integer/decimal/quantity).

    CQL §19.25: For date/time intervals, the width operator is not defined.
    Returns a JSON quantity string for quantity intervals, numeric string otherwise.
    """
    iv = _parse_interval(interval)
    if not iv or iv["low"] is None or iv["high"] is None:
        return None

    low = iv["low"]
    high = iv["high"]

    low_q = _quantity_json(low)
    high_q = _quantity_json(high)
    if low_q is not None and high_q is not None:
        try:
            from .quantity import _parse_quantity, _quantity_to_pint
            low_parsed = _parse_quantity(low_q)
            high_parsed = _parse_quantity(high_q)
            low_pint = _quantity_to_pint(low_parsed) if low_parsed else None
            high_pint = _quantity_to_pint(high_parsed) if high_parsed else None
            if low_pint is None or high_pint is None:
                return None
            high_converted = high_pint.to(low_pint.units)
            unit = (low_parsed or {}).get("code") or (low_parsed or {}).get("unit") or "1"
            import json as _json
            return _json.dumps({
                "value": float(high_converted.magnitude - low_pint.magnitude),
                "unit": unit,
                "code": unit,
            })
        except Exception as e:
            _logger.debug("Unexpected error in UDF intervalWidth quantity comparison: %s", e)
            return None

    # CQL §19.25: "For date/time intervals, this operator is not defined."
    if isinstance(low, (datetime, date)) or isinstance(high, (datetime, date)):
        raise ValueError(
            "The Width operator is not defined for date/time intervals. "
            "Use 'duration in' instead (CQL §19.25)."
        )
    # Check the raw JSON bounds for time strings (parsed to ms integers)
    try:
        raw = orjson.loads(interval)
        raw_low = raw.get("low") or raw.get("start")
        if isinstance(raw_low, str):
            rl = raw_low.strip()
            # Time string: T-prefixed or HH:MM:SS pattern
            if rl.startswith('T') or rl.startswith('t') or (
                len(rl) >= 5 and rl[2:3] == ':' and rl[:2].isdigit()
            ):
                raise ValueError(
                    "The Width operator is not defined for time intervals. "
                    "Use 'duration in' instead (CQL §19.25)."
                )
            # Quantity JSON — return quantity width
            if rl.startswith('{') and '"value"' in rl:
                import json as _json
                q = _json.loads(rl)
                unit = q.get("unit") or q.get("code") or "1"
                width_val = float(high) - float(low)
                return _json.dumps({"value": width_val, "unit": unit, "code": unit})
    except ValueError:
        raise
    except Exception as e:
        _logger.debug("Unexpected error in UDF intervalWidth quantity parse: %s", e)

    # Numeric intervals
    if isinstance(low, (int, float)) and isinstance(high, (int, float)):
        result = high - low
        if isinstance(low, float) or isinstance(high, float):
            return _format_decimal(float(result))
        return str(result)

    return str(high - low)


def interval_size(interval: str | None) -> str | None:
    """Get the size of an interval (number of discrete values).

    CQL §19.18: Size(I) = Width(I) + point-size, where point-size is the
    smallest meaningful difference for the point type.
    For integer intervals: Size = high - low + 1.
    For decimal intervals: Size = high - low + minimum precision.
    For date/time intervals: same limitation as Width (not defined).
    """
    if interval is None:
        return None
    iv = _parse_interval(interval)
    if not iv or iv["low"] is None or iv["high"] is None:
        return None

    low = iv["low"]
    high = iv["high"]

    if isinstance(low, (datetime, date)) or isinstance(high, (datetime, date)):
        raise ValueError(
            "The Size operator is not defined for date/time intervals. "
            "Use 'duration in' instead (CQL §19.18)."
        )

    low_q = _quantity_json(low)
    high_q = _quantity_json(high)
    if low_q is not None and high_q is not None:
        try:
            from .quantity import _parse_quantity, _quantity_to_pint
            low_parsed = _parse_quantity(low_q)
            high_parsed = _parse_quantity(high_q)
            low_pint = _quantity_to_pint(low_parsed) if low_parsed else None
            high_pint = _quantity_to_pint(high_parsed) if high_parsed else None
            if low_pint is None or high_pint is None:
                return None
            high_converted = high_pint.to(low_pint.units)
            unit = (low_parsed or {}).get("code") or (low_parsed or {}).get("unit") or "1"
            import json as _json
            return _json.dumps({
                "value": float(high_converted.magnitude - low_pint.magnitude + 1e-8),
                "unit": unit,
                "code": unit,
            })
        except Exception as e:
            _logger.debug("Unexpected error in UDF interval_size quantity comparison: %s", e)
            return None

    if isinstance(low, int) and isinstance(high, int):
        return str(high - low + 1)

    if isinstance(low, (int, float)) and isinstance(high, (int, float)):
        return _format_decimal(float(Decimal(str(high)) - Decimal(str(low)) + _DECIMAL_STEP))

    return str(high - low)


def intervalContains(interval: str | None, point: str | None) -> bool | None:
    """Check if interval contains a point or another interval.

    Per CQL spec:
    - ``Interval<T> contains T`` → point containment
    - ``Interval<T> contains Interval<T>`` → equivalent to ``includes``

    The translator emits ``intervalContains(B, A)`` for both ``A during B``
    (interval in interval) and point-in-interval checks.  When *point* is
    actually an interval JSON string, delegate to ``intervalIncludes``.

    Null inputs return null per CQL three-valued logic.
    """
    if interval is None:
        return None
    if point is None:
        return None

    # Detect whether the second argument is an interval (JSON object) or a
    # scalar point value. Interval JSON has "low"/"high" keys; quantity JSON
    # has "value"/"unit" keys and should be treated as a point.
    stripped = point.strip() if point else ""
    if stripped.startswith("{"):
        try:
            obj = orjson.loads(stripped)
            if isinstance(obj, dict) and (
                "low" in obj or "high" in obj or "lowClosed" in obj
                or "start" in obj or "end" in obj
            ):
                # Interval JSON (low/high or FHIR Period start/end) → use "includes" semantics
                return intervalIncludes(interval, point)
        except (JSONDecodeError, TypeError):
            pass

    iv = _parse_interval(interval)
    pt = _parse_point(point)

    if not iv or pt is None:
        return None

    low, high = iv["low"], iv["high"]

    # Check bounds — None means unbounded (always satisfies that side)
    low_ok = True
    if low is not None:
        cmp = _compare_interval_values(low, pt)
        if cmp is None:
            return None
        low_ok = cmp <= 0 if iv["low_closed"] else cmp < 0
    high_ok = True
    if high is not None:
        cmp = _compare_interval_values(pt, high)
        if cmp is None:
            return None
        high_ok = cmp <= 0 if iv["high_closed"] else cmp < 0

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
        try:
            obj = orjson.loads(stripped)
            if isinstance(obj, dict) and (
                "low" in obj or "high" in obj or "lowClosed" in obj
                or "start" in obj or "end" in obj
            ):
                return intervalProperlyIncludes(interval, point)
        except (JSONDecodeError, TypeError):
            pass

    iv = _parse_interval(interval)
    pt = _parse_point(point)

    if not iv or pt is None:
        return None

    low, high = iv["low"], iv["high"]
    point_for_compare = point if _is_temporal_string(point) else pt

    # Official CQL conformance treats interval-point "properly includes" as
    # strict containment: boundary points are not properly contained.
    low_ok = True
    if low is not None:
        low_for_compare = _interval_bound(iv, "low", "low_raw")
        cmp = (
            _precision_aware_compare(low_for_compare, point_for_compare)
            if _is_temporal_string(low_for_compare) and _is_temporal_string(point_for_compare)
            else _compare_interval_values(low, pt)
        )
        if cmp is None:
            return None
        low_ok = cmp < 0
    high_ok = True
    if high is not None:
        high_for_compare = _interval_bound(iv, "high", "high_raw")
        cmp = (
            _precision_aware_compare(point_for_compare, high_for_compare)
            if _is_temporal_string(point_for_compare) and _is_temporal_string(high_for_compare)
            else _compare_interval_values(pt, high)
        )
        if cmp is None:
            return None
        high_ok = cmp < 0
    return low_ok and high_ok


def _normalize_datetime_str(s: str) -> str:
    """Normalize datetime string format for consistent comparison.

    TIMESTAMP→VARCHAR produces space-separated format ('2026-01-01 00:00:00')
    while FHIR dates use T-separator ('2026-01-01T00:00:00.000Z').
    Normalize both to the same format: T-separator, no trailing Z.
    """
    s = s.replace(' ', 'T')  # space → T separator
    if s.endswith('Z'):
        s = s[:-1]  # strip UTC 'Z' marker
    return s


def _normalize_timestamp_bound(s: str) -> str:
    """Normalize a TIMESTAMP-formatted bound string to ISO 8601.

    DuckDB ``CAST(... AS TIMESTAMP)`` → VARCHAR produces space-separated
    format without trailing ``.000`` milliseconds (e.g.
    ``'2026-01-01 00:00:00'``).  CQL literals use T-separator and preserve
    precision (``'2017-09-01T00:00:00'``).  The space separator is a
    reliable indicator of TIMESTAMP formatting — normalize these to full
    ISO 8601 with ``.000`` milliseconds so precision-aware comparison
    treats them as millisecond-precision (not second).
    """
    if ' ' in s and 'T' not in s:
        s = s.replace(' ', 'T')
        if '.' not in s:
            s += '.000'
    return s


def _precision_aware_compare(a, b) -> int | None:
    """Precision-aware comparison of two interval bounds.

    Returns -1 (a < b), 0 (a == b), 1 (a > b), or None (uncertain).
    Handles partial-precision ISO 8601 strings per CQL §18.4.
    """
    from .datetime import _compare_at_min_precision, _infer_precision
    # If both are strings and they're date/datetime values, use precision-aware comparison
    if isinstance(a, str) and isinstance(b, str):
        a_s = _normalize_datetime_str(a.strip())
        b_s = _normalize_datetime_str(b.strip())
        # Skip non-date strings (e.g., time strings, numeric strings)
        a_looks_date = (a_s and a_s[0].isdigit() and len(a_s) >= 4) or a_s.startswith('T')
        b_looks_date = (b_s and b_s[0].isdigit() and len(b_s) >= 4) or b_s.startswith('T')
        if a_looks_date and b_looks_date:
            try:
                a_prec = _infer_precision(a_s)
                b_prec = _infer_precision(b_s)
                if a_prec != b_prec:
                    cmp, certain = _compare_at_min_precision(
                        a_s,
                        b_s,
                        promote_date_to_datetime=True,
                    )
                    if not certain:
                        return None  # Uncertain due to precision mismatch
                    return cmp
            except (ValueError, KeyError):
                pass
    # Fall back to _normalize_for_compare for same-precision or non-string values
    na, nb = _normalize_for_compare(a, b)
    if isinstance(na, (dict, list)) or isinstance(nb, (dict, list)):
        return None
    try:
        if na < nb:
            return -1
        elif na > nb:
            return 1
    except TypeError:
        return None
    return 0


def _compare_interval_values(a: Any, b: Any) -> int | None:
    """Tri-valued comparison for interval bounds and points."""
    q_a = _quantity_json(a)
    q_b = _quantity_json(b)
    if q_a is not None and q_b is not None:
        from .quantity import quantityCompare

        less = quantityCompare(q_a, q_b, "<")
        if less is None:
            return None
        if less:
            return -1
        greater = quantityCompare(q_a, q_b, ">")
        if greater is None:
            return None
        if greater:
            return 1
        equal = quantityCompare(q_a, q_b, "==")
        if equal is None:
            return None
        return 0 if equal else None

    left, right = _normalize_for_compare(a, b)
    if isinstance(left, (dict, list)) or isinstance(right, (dict, list)):
        return None
    try:
        if left < right:
            return -1
        if left > right:
            return 1
    except TypeError:
        return None
    return 0


def _normalize_for_compare(a, b):
    """Normalize date/datetime pair for comparison.

    Per CQL spec, when comparing values of different precisions (date vs datetime),
    comparison is done at the precision of the less precise operand. So when one is
    a date and the other is a datetime, we truncate the datetime to date precision.
    """
    # Helper: convert a CQL Time string to millis-since-midnight
    def _time_str_to_millis(s: str) -> int | None:
        from datetime import time as _time_type
        stripped = s.strip().lstrip('T')
        try:
            # Pad partial time strings
            if len(stripped) == 2 and stripped.isdigit():
                stripped = f"{stripped}:00:00"
            elif len(stripped) == 5 and stripped[2] == ':':
                stripped = f"{stripped}:00"
            if '.' in stripped:
                base, frac = stripped.split('.', 1)
                frac = frac.ljust(6, '0')[:6]
                stripped = f"{base}.{frac}"
            t = _time_type.fromisoformat(stripped)
            return t.hour * 3600000 + t.minute * 60000 + t.second * 1000 + t.microsecond // 1000
        except (ValueError, TypeError):
            return None

    # Handle Time strings (start with 'T' or look like HH:MM:SS)
    def _is_time_str(v) -> bool:
        if not isinstance(v, str):
            return False
        s = v.strip()
        # Full: T10:00:00, 10:00:00; Partial: T10, T10:00
        return (s.startswith('T') and len(s) >= 3 and s[1:3].isdigit()) or (
            len(s) >= 5 and s[2] == ':' and s[:2].isdigit()
        )

    q_a = _quantity_json(a)
    q_b = _quantity_json(b)
    if q_a is not None and q_b is not None:
        try:
            from .quantity import _parse_quantity, _quantity_to_pint
            parsed_a = _parse_quantity(q_a)
            parsed_b = _parse_quantity(q_b)
            pint_a = _quantity_to_pint(parsed_a) if parsed_a else None
            pint_b = _quantity_to_pint(parsed_b) if parsed_b else None
            if pint_a is not None and pint_b is not None:
                return float(pint_a.magnitude), float(pint_b.to(pint_a.units).magnitude)
        except Exception as e:
            _logger.debug("Quantity interval comparison normalization failed: %s", e)
            return a, b
    if (q_a is not None) != (q_b is not None):
        return a, b

    # Coerce Time strings to millis for comparison with int time-millis
    if _is_time_str(a):
        m = _time_str_to_millis(a)
        if m is not None:
            a = m
    if _is_time_str(b):
        m = _time_str_to_millis(b)
        if m is not None:
            b = m

    # Normalize datetime string format (space→T, strip Z) before comparison
    if isinstance(a, str):
        a = _normalize_datetime_str(a)
    if isinstance(b, str):
        b = _normalize_datetime_str(b)

    # Coerce unparsed strings to date/datetime objects first
    if isinstance(a, str) and not isinstance(b, str):
        parsed = _parse_date_or_datetime(a)
        if parsed is not None:
            a = parsed
    if isinstance(b, str) and not isinstance(a, str):
        parsed = _parse_date_or_datetime(b)
        if parsed is not None:
            b = parsed
    # If both are still strings, try to parse both
    if isinstance(a, str) and isinstance(b, str):
        pa = _parse_date_or_datetime(a)
        pb = _parse_date_or_datetime(b)
        if pa is not None and pb is not None:
            a, b = pa, pb
        else:
            # Fall back to string comparison for ISO 8601
            return a, b

    # Guard: incompatible types (e.g. datetime vs int) cannot be compared.
    # Coerce the int to a date (treating it as a year) when the other is a date/datetime,
    # but only for valid year values (1-9999). Large ints are time-millis or other non-year values.
    if isinstance(a, (date, datetime)) and isinstance(b, int) and 1 <= b <= 9999:
        b = date(b, 1, 1)
    elif isinstance(b, (date, datetime)) and isinstance(a, int) and 1 <= a <= 9999:
        a = date(a, 1, 1)
    # For pure integer pairs (e.g., time millis), compare directly
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return a, b
    # Handle datetime vs large-int (time millis) comparison:
    # Convert datetime to millis-since-midnight for comparison with time millis
    def _dt_to_millis(dt):
        return dt.hour * 3600000 + dt.minute * 60000 + dt.second * 1000 + dt.microsecond // 1000
    if isinstance(a, (date, datetime)) and isinstance(b, int) and b > 9999:
        a = _dt_to_millis(a) if isinstance(a, datetime) else 0
        return a, b
    elif isinstance(b, (date, datetime)) and isinstance(a, int) and a > 9999:
        b = _dt_to_millis(b) if isinstance(b, datetime) else 0
        return a, b

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


def _normalize_bound(raw_val, is_closed: bool, is_high: bool, parsed) -> tuple:
    """Normalize an interval bound to closed form for discrete types.

    For discrete types (int, date, datetime), open bounds are converted
    to equivalent closed bounds by adjusting ±1 predecessor step.
    Returns (new_raw_val, new_is_closed).
    """
    if is_closed:
        return raw_val, True

    from decimal import Decimal as _Decimal

    if isinstance(parsed, int) and not isinstance(parsed, bool):
        if is_high:
            return parsed - 1, True
        else:
            return parsed + 1, True
    elif isinstance(parsed, float):
        if is_high:
            return float(_Decimal(str(parsed)) - _Decimal("0.00000001")), True
        else:
            return float(_Decimal(str(parsed)) + _Decimal("0.00000001")), True
    elif _is_quantity_bound(parsed):
        numeric = _quantity_numeric(parsed)
        if numeric is None:
            return raw_val, is_closed
        if is_high:
            adjusted = float(_Decimal(str(numeric)) - _Decimal("0.00000001"))
        else:
            adjusted = float(_Decimal(str(numeric)) + _Decimal("0.00000001"))
        return _quantity_bound_with_numeric(parsed, adjusted), True
    elif isinstance(parsed, date) and not isinstance(parsed, datetime):
        from datetime import timedelta
        if is_high:
            new_d = parsed - timedelta(days=1)
        else:
            new_d = parsed + timedelta(days=1)
        return new_d.isoformat(), True
    elif isinstance(parsed, datetime):
        if is_high:
            new_dt = _predecessor_for_bound(parsed, raw_val)
        else:
            new_dt = _successor_for_bound(parsed, raw_val)
        if new_dt is None:
            return raw_val, is_closed
        if _is_day_precision_datetime_string(raw_val):
            return _format_day_precision_datetime(new_dt), True
        return new_dt.isoformat(), True

    # Non-discrete type — keep as-is
    return raw_val, is_closed


def _millis_to_time_str(ms: int) -> str:
    """Convert milliseconds since midnight to a time string HH:MM:SS.mmm."""
    h, rem = divmod(ms, 3600000)
    m, rem = divmod(rem, 60000)
    s, millis = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d}.{millis:03d}"


def _is_time_raw(raw_val) -> bool:
    """Check if a raw interval bound value is a time string."""
    return _is_time_like_string(raw_val)


def _normalize_bound_for_output(raw_val, is_closed: bool, is_high: bool, parsed) -> tuple:
    """Like _normalize_bound but preserves time/quantity format in output.

    When parsed is an integer from a time string, the result integer is
    converted back to a time string for JSON serialization.
    When the raw_val is a quantity JSON string, the result is wrapped back
    into quantity JSON.
    """
    new_val, new_closed = _normalize_bound(raw_val, is_closed, is_high, parsed)
    if _is_quantity_bound(new_val):
        new_val = new_val["__cql_quantity_json__"]
    # If original was a time string and result is an integer, convert back
    if isinstance(new_val, int) and _is_time_raw(raw_val):
        new_val = _millis_to_time_str(new_val)
    # If original was quantity JSON, wrap the numeric result back into quantity
    if isinstance(raw_val, str) and isinstance(new_val, (int, float)):
        stripped = raw_val.strip()
        if stripped.startswith('{') and '"value"' in stripped:
            try:
                q = orjson.loads(stripped)
                if isinstance(q, dict) and "value" in q:
                    q["value"] = new_val
                    import json as _json
                    new_val = _json.dumps(q)
            except (JSONDecodeError, TypeError, ValueError):
                pass
    return new_val, new_closed


def _unwrap_bound_for_json(val):
    """Unwrap a JSON-encoded bound value for proper nesting in output.

    If val is a string containing JSON (e.g., quantity), parse it to a dict
    so json.dumps produces properly nested output instead of double-encoding.
    """
    if isinstance(val, str):
        stripped = val.strip()
        if stripped.startswith('{'):
            try:
                parsed = orjson.loads(stripped)
                if isinstance(parsed, dict) and "value" in parsed:
                    quantity = {"value": parsed["value"]}
                    unit = parsed.get("unit") or parsed.get("code")
                    if unit is not None:
                        quantity["unit"] = unit
                    return quantity
                return parsed
            except (JSONDecodeError, TypeError, ValueError):
                pass
    return val


def intervalOverlaps(interval1: str | None, interval2: str | None) -> bool | None:
    """Check if two intervals overlap.

    CQL §19.22: Returns null when interval endpoints have insufficient
    precision for certain comparison (e.g., '2012-02-26' vs '2012-02').
    Returns None (NULL) for null/unparseable inputs per CQL three-valued logic.
    """
    iv1 = _parse_interval(interval1)
    iv2 = _parse_interval(interval2)

    if not iv1 or not iv2:
        return None

    # Use raw string values for precision-aware comparison only for temporal bounds
    h1_raw = _authored_closed_temporal_raw(iv1, "high_raw", "high_closed", "high_was_open")
    l2_raw = _authored_closed_temporal_raw(iv2, "low_raw", "low_closed", "low_was_open")
    h2_raw = _authored_closed_temporal_raw(iv2, "high_raw", "high_closed", "high_was_open")
    l1_raw = _authored_closed_temporal_raw(iv1, "low_raw", "low_closed", "low_was_open")

    # Intervals overlap if neither ends before the other starts
    # (end1 >= start2) AND (end2 >= start1)
    if iv1["high"] is None or iv2["low"] is None:
        end1_after_start2 = True
    else:
        cmp1 = _precision_aware_compare(
            h1_raw if h1_raw else iv1["high"],
            l2_raw if l2_raw else iv2["low"],
        )
        if cmp1 is None:
            return None
        if iv1["high_closed"] and iv2["low_closed"]:
            end1_after_start2 = cmp1 >= 0
        else:
            end1_after_start2 = cmp1 > 0
    if iv2["high"] is None or iv1["low"] is None:
        end2_after_start1 = True
    else:
        cmp2 = _precision_aware_compare(
            h2_raw if h2_raw else iv2["high"],
            l1_raw if l1_raw else iv1["low"],
        )
        if cmp2 is None:
            return None
        if iv2["high_closed"] and iv1["low_closed"]:
            end2_after_start1 = cmp2 >= 0
        else:
            end2_after_start1 = cmp2 > 0

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


def intervalOnOrAfter(interval1: str | None, interval2: str | None) -> bool | None:
    """CQL §19.17 — on or after for intervals.

    - Interval on or after Interval: start(X) >= end(Y)
    - Point on or after Interval: point >= end(Y)  (point wrapped as degenerate interval)
    - Interval on or after Point: start(X) >= point

    Returns None for null inputs.
    """
    iv1 = _parse_interval(interval1)
    iv2 = _parse_interval(interval2)
    if not iv1 or not iv2:
        return None
    # start of first >= end of second
    start1 = _effective_start(iv1)
    end2 = _effective_end(iv2)
    if start1 is None or end2 is None:
        return None
    start1_raw = _authored_closed_temporal_raw(iv1, "low_raw", "low_closed", "low_was_open")
    end2_raw = _authored_closed_temporal_raw(iv2, "high_raw", "high_closed", "high_was_open")
    cmp = _precision_aware_compare(
        start1_raw if start1_raw else start1,
        end2_raw if end2_raw else end2,
    )
    if cmp is None:
        return None
    return cmp >= 0


def intervalOnOrBefore(interval1: str | None, interval2: str | None) -> bool | None:
    """CQL §19.18 — on or before for intervals.

    - Interval on or before Interval: end(X) <= start(Y)
    - Point on or before Interval: point <= start(Y)  (point wrapped as degenerate interval)
    - Interval on or before Point: end(X) <= point

    Returns None for null inputs.
    """
    iv1 = _parse_interval(interval1)
    iv2 = _parse_interval(interval2)
    if not iv1 or not iv2:
        return None
    # end of first <= start of second
    end1 = _effective_end(iv1)
    start2 = _effective_start(iv2)
    if end1 is None or start2 is None:
        return None
    end1_raw = _authored_closed_temporal_raw(iv1, "high_raw", "high_closed", "high_was_open")
    start2_raw = _authored_closed_temporal_raw(iv2, "low_raw", "low_closed", "low_was_open")
    cmp = _precision_aware_compare(
        end1_raw if end1_raw else end1,
        start2_raw if start2_raw else start2,
    )
    if cmp is None:
        return None
    return cmp <= 0


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
        succ = _successor_for_bound(end1, iv1.get("high_raw"))
        if succ is not None:
            s, t = _normalize_for_compare(succ, start2)
            if s == t:
                return True

    # Check iv2 meets iv1: successor(effective end of iv2) == effective start of iv1
    end2 = _effective_end(iv2)
    start1 = _effective_start(iv1)
    if end2 is not None and start1 is not None:
        succ = _successor_for_bound(end2, iv2.get("high_raw"))
        if succ is not None:
            s, t = _normalize_for_compare(succ, start1)
            if s == t:
                return True

    if end1 is None or start2 is None or end2 is None or start1 is None:
        return None

    return False


def _is_temporal_string(s) -> bool:
    """Check if a string looks like a date/datetime ISO 8601 value."""
    if not isinstance(s, str):
        return False
    s = s.strip()
    if _is_time_like_string(s):
        return True
    # ISO 8601 date/datetime patterns: YYYY or YYYY-MM etc.
    return len(s) >= 4 and s[0:4].isdigit() and (len(s) == 4 or s[4] == '-' or s[4] == 'T')


_PRECISION_VALUES = frozenset((
    "year", "month", "day", "hour", "minute", "second", "millisecond",
))


def _compare_bound_at_precision(a: Any, b: Any, precision: str | None) -> int | None:
    """Compare interval bounds at an explicit CQL temporal precision."""
    if precision not in _PRECISION_VALUES:
        return None
    if _is_temporal_string(a) and _is_temporal_string(b):
        from .datetime import _compare_at_specified_precision
        cmp, certain = _compare_at_specified_precision(str(a), str(b), precision)
        return cmp if certain else None
    na, nb = _normalize_for_compare(a, b)
    if na < nb:
        return -1
    if na > nb:
        return 1
    return 0


def _interval_bound(iv: dict, parsed_key: str, raw_key: str) -> Any:
    raw = iv.get(raw_key)
    return raw if _is_temporal_string(raw) else iv.get(parsed_key)


def intervalBeforePrecise(interval1: str | None, interval2: str | None, precision: str | None) -> bool | None:
    """Precision-aware CQL interval before."""
    if interval1 is None or interval2 is None or precision is None:
        return None
    iv1 = _parse_interval(interval1)
    iv2 = _parse_interval(interval2)
    if not iv1 or not iv2 or iv1["high"] is None or iv2["low"] is None:
        return False
    cmp = _compare_bound_at_precision(
        _interval_bound(iv1, "high", "high_raw"),
        _interval_bound(iv2, "low", "low_raw"),
        str(precision),
    )
    if cmp is None:
        return None
    if iv1["high_closed"] and iv2["low_closed"]:
        return cmp < 0
    return cmp <= 0


def intervalAfterPrecise(interval1: str | None, interval2: str | None, precision: str | None) -> bool | None:
    """Precision-aware CQL interval after."""
    if interval1 is None or interval2 is None or precision is None:
        return None
    return intervalBeforePrecise(interval2, interval1, precision)


def intervalContainsPrecise(interval: str | None, point: str | None, precision: str | None) -> bool | None:
    """Precision-aware CQL interval contains point/interval."""
    if interval is None:
        return False
    if point is None or precision is None:
        return None
    iv = _parse_interval(interval)
    if not iv:
        return False
    stripped = point.strip()
    if stripped.startswith("{"):
        try:
            obj = orjson.loads(stripped)
            if isinstance(obj, dict) and (
                "low" in obj or "high" in obj or "lowClosed" in obj
                or "start" in obj or "end" in obj
            ):
                return intervalIncludesPrecise(interval, point, precision)
        except (JSONDecodeError, TypeError):
            pass
    pt = point if _is_temporal_string(point) else _parse_point(point)
    if pt is None:
        return False
    if iv["low"] is not None:
        cmp = _compare_bound_at_precision(_interval_bound(iv, "low", "low_raw"), pt, str(precision))
        if cmp is None or cmp > 0 or (cmp == 0 and not iv["low_closed"]):
            return None if cmp is None else False
    if iv["high"] is not None:
        cmp = _compare_bound_at_precision(_interval_bound(iv, "high", "high_raw"), pt, str(precision))
        if cmp is None or cmp < 0 or (cmp == 0 and not iv["high_closed"]):
            return None if cmp is None else False
    return True


def intervalOverlapsPrecise(interval1: str | None, interval2: str | None, precision: str | None) -> bool | None:
    """Precision-aware CQL interval overlaps."""
    if interval1 is None or interval2 is None or precision is None:
        return None
    iv1 = _parse_interval(interval1)
    iv2 = _parse_interval(interval2)
    if not iv1 or not iv2:
        return False
    if iv1["low"] is not None and iv2["high"] is not None:
        cmp = _compare_bound_at_precision(
            _interval_bound(iv2, "high", "high_raw"),
            _interval_bound(iv1, "low", "low_raw"),
            str(precision),
        )
        if cmp is None:
            return None
        if cmp < 0 or (cmp == 0 and (not iv2["high_closed"] or not iv1["low_closed"])):
            return False
    if iv1["high"] is not None and iv2["low"] is not None:
        cmp = _compare_bound_at_precision(
            _interval_bound(iv1, "high", "high_raw"),
            _interval_bound(iv2, "low", "low_raw"),
            str(precision),
        )
        if cmp is None:
            return None
        if cmp < 0 or (cmp == 0 and (not iv1["high_closed"] or not iv2["low_closed"])):
            return False
    return True


def intervalOverlapsBeforePrecise(interval1: str | None, interval2: str | None, precision: str | None) -> bool | None:
    """Precision-aware CQL interval overlaps before."""
    if interval1 is None or interval2 is None or precision is None:
        return None
    iv1 = _parse_interval(interval1)
    iv2 = _parse_interval(interval2)
    if not iv1 or not iv2 or iv1["low"] is None or iv2["low"] is None:
        return False
    low_cmp = _compare_bound_at_precision(
        _interval_bound(iv1, "low", "low_raw"),
        _interval_bound(iv2, "low", "low_raw"),
        str(precision),
    )
    if low_cmp is None:
        return None
    if low_cmp >= 0:
        return False
    if iv1["high"] is None:
        return True
    high_cmp = _compare_bound_at_precision(
        _interval_bound(iv1, "high", "high_raw"),
        _interval_bound(iv2, "low", "low_raw"),
        str(precision),
    )
    if high_cmp is None:
        return None
    if high_cmp == 0:
        return iv1["high_closed"] and iv2["low_closed"]
    return high_cmp > 0


def intervalOverlapsAfterPrecise(interval1: str | None, interval2: str | None, precision: str | None) -> bool | None:
    """Precision-aware CQL interval overlaps after."""
    if interval1 is None or interval2 is None or precision is None:
        return None
    return intervalOverlapsBeforePrecise(interval2, interval1, precision)


def intervalIncludes(interval1: str | None, interval2: str | None) -> bool | None:
    """Check if interval1 fully includes interval2.

    CQL §19.10: Returns null when interval endpoints have insufficient
    precision for certain comparison.
    Respects open/closed boundaries per CQL spec.
    Null bounds are treated as unbounded (CQL §19.1).
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
    # Use raw string values for precision-aware comparison only for temporal bounds
    start1_raw = _authored_closed_temporal_raw(iv1, "low_raw", "low_closed", "low_was_open")
    end1_raw = _authored_closed_temporal_raw(iv1, "high_raw", "high_closed", "high_was_open")
    start2_raw = _authored_closed_temporal_raw(iv2, "low_raw", "low_closed", "low_was_open")
    end2_raw = _authored_closed_temporal_raw(iv2, "high_raw", "high_closed", "high_was_open")
    # Null bound = unbounded
    if start1 is None:
        start_ok = True
    elif start2 is None:
        start_ok = False
    else:
        cmp = _precision_aware_compare(
            start1_raw if start1_raw else start1,
            start2_raw if start2_raw else start2,
        )
        if cmp is None:
            return None
        start_ok = cmp <= 0
    if end1 is None:
        end_ok = True
    elif end2 is None:
        end_ok = False
    else:
        cmp = _precision_aware_compare(
            end1_raw if end1_raw else end1,
            end2_raw if end2_raw else end2,
        )
        if cmp is None:
            return None
        end_ok = cmp >= 0
    return start_ok and end_ok


def intervalIncludedIn(interval1: str | None, interval2: str | None) -> bool:
    """Check if interval1 is included in interval2."""
    return intervalIncludes(interval2, interval1)


def intervalIncludesPrecise(interval1: str | None, interval2: str | None, precision: str | None) -> bool | None:
    """Precision-aware CQL interval includes."""
    if interval1 is None or interval2 is None or precision is None:
        return None
    iv1 = _parse_interval(interval1)
    iv2 = _parse_interval(interval2)
    if not iv1 or not iv2:
        return False
    if iv2["low"] is None and iv1["low"] is not None:
        return False
    if iv2["high"] is None and iv1["high"] is not None:
        return False
    if iv2["low"] is not None:
        low_contains = intervalContainsPrecise(
            interval1,
            str(_interval_bound(iv2, "low", "low_raw")),
            precision,
        )
        if low_contains is None:
            return None
        if not low_contains:
            return False
    if iv2["high"] is not None:
        high_contains = intervalContainsPrecise(
        interval1,
            str(_interval_bound(iv2, "high", "high_raw")),
            precision,
        )
        if high_contains is None:
            return None
        if not high_contains:
            return False
    return True


def _interval_effective_bounds(interval: str | None) -> tuple[Any, Any] | None:
    iv = _parse_interval(interval)
    if not iv:
        return None
    return _effective_start(iv), _effective_end(iv)


def _bounds_equal(left: Any, right: Any, *, nulls_equivalent: bool) -> bool | None:
    if left is None or right is None:
        return left is None and right is None
    left_norm, right_norm = _normalize_for_compare(left, right)
    return left_norm == right_norm


def intervalEquals(interval1: str | None, interval2: str | None) -> bool | None:
    """CQL interval equality using semantic Start/End boundaries."""
    if interval1 is None or interval2 is None:
        return None
    left = _interval_effective_bounds(interval1)
    right = _interval_effective_bounds(interval2)
    if left is None or right is None:
        return None
    starts_equal = _bounds_equal(left[0], right[0], nulls_equivalent=False)
    ends_equal = _bounds_equal(left[1], right[1], nulls_equivalent=False)
    if starts_equal is None or ends_equal is None:
        return None
    return starts_equal and ends_equal


def intervalEquivalent(interval1: str | None, interval2: str | None) -> bool:
    """CQL interval equivalence using semantic Start/End boundaries."""
    if interval1 is None or interval2 is None:
        return interval1 is None and interval2 is None
    left = _interval_effective_bounds(interval1)
    right = _interval_effective_bounds(interval2)
    if left is None or right is None:
        return False
    starts_equal = _bounds_equal(left[0], right[0], nulls_equivalent=True)
    ends_equal = _bounds_equal(left[1], right[1], nulls_equivalent=True)
    return bool(starts_equal and ends_equal)


def intervalIncludedInPrecise(interval1: str | None, interval2: str | None, precision: str | None) -> bool | None:
    """Precision-aware CQL interval included in."""
    if interval1 is None or interval2 is None or precision is None:
        return None
    return intervalIncludesPrecise(interval2, interval1, precision)


def intervalProperlyIncludes(interval1: str | None, interval2: str | None) -> bool | None:
    """Check if interval1 properly includes interval2 (includes AND not equal).

    Respects open/closed boundaries per CQL spec.
    Null bounds are treated as unbounded (CQL §19.1).
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
    # Null bound = unbounded: null start is before everything, null end is after everything
    # start1 <= start2: True if start1 is null (unbounded below)
    if start1 is None:
        start_ok = True
    elif start2 is None:
        start_ok = False  # start2 unbounded, start1 is not → can't include
    else:
        s1, s2 = _normalize_for_compare(start1, start2)
        start_ok = s1 <= s2
    # end1 >= end2: True if end1 is null (unbounded above)
    if end1 is None:
        end_ok = True
    elif end2 is None:
        end_ok = False
    else:
        e1, e2 = _normalize_for_compare(end1, end2)
        end_ok = e1 >= e2
    includes = start_ok and end_ok
    # Check equality — both must have same effective bounds
    if start1 is None and start2 is None:
        starts_equal = True
    elif start1 is None or start2 is None:
        starts_equal = False
    else:
        s1, s2 = _normalize_for_compare(start1, start2)
        starts_equal = s1 == s2
    if end1 is None and end2 is None:
        ends_equal = True
    elif end1 is None or end2 is None:
        ends_equal = False
    else:
        e1, e2 = _normalize_for_compare(end1, end2)
        ends_equal = e1 == e2
    is_equal = starts_equal and ends_equal
    return includes and not is_equal


def intervalProperlyIncludedIn(interval1: str | None, interval2: str | None) -> bool | None:
    """Check if interval1 is properly included in interval2 (CQL §19.14).

    Per CQL null propagation, a null interval value is not the same as an
    interval with typed-null bounds.  ``Interval[null, null]`` is unbounded;
    ``null as Interval<T>`` yields SQL NULL for this operator.
    """
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
    if overlaps is None:
        return None
    if not overlaps:
        return False
    # Compare effective starts (accounts for open bounds via successor)
    s1 = _effective_start(iv1)
    s2 = _effective_start(iv2)
    if s1 is None:
        return True  # -infinity is before any start
    if s2 is None:
        return False  # can't start before -infinity
    cmp = _compare_interval_values(s1, s2)
    if cmp is None:
        return None
    return cmp < 0


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
    if overlaps is None:
        return None
    if not overlaps:
        return False
    # Compare effective ends (accounts for open bounds via predecessor)
    e1 = _effective_end(iv1)
    e2 = _effective_end(iv2)
    if e1 is None:
        return True  # +infinity is after any end
    if e2 is None:
        return False  # can't end after +infinity
    cmp = _compare_interval_values(e1, e2)
    if cmp is None:
        return None
    return cmp > 0


def _interval_definitely_after(iv1: dict, iv2: dict) -> bool:
    """Return True when iv1 starts after iv2 ends with known bounds."""
    start1 = _effective_start(iv1)
    end2 = _effective_end(iv2)
    if start1 is None or end2 is None:
        return False
    start1_raw = _authored_closed_temporal_raw(iv1, "low_raw", "low_closed", "low_was_open")
    end2_raw = _authored_closed_temporal_raw(iv2, "high_raw", "high_closed", "high_was_open")
    cmp = _precision_aware_compare(
        start1_raw if start1_raw else start1,
        end2_raw if end2_raw else end2,
    )
    return cmp is not None and cmp > 0


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
        if _interval_definitely_after(iv1, iv2):
            return False
        return None
    succ = _successor_for_bound(end1, iv1.get("high_raw"))
    if succ is None:
        return None
    s, t = _normalize_for_compare(succ, start2)
    return s == t


def intervalMeetsAfter(interval1: str | None, interval2: str | None) -> bool:
    """Check if interval2 ends exactly when interval1 starts (iv2 meets iv1 from before)."""
    return intervalMeetsBefore(interval2, interval1)


def intervalStartsSame(interval1: str | None, interval2: str | None) -> bool | None:
    """CQL §19.30 Starts: iv1 starts iv2 iff iv1.start == iv2.start AND iv1.end <= iv2.end.

    Returns None (NULL) for null/unparseable inputs per CQL three-valued logic.
    """
    iv1 = _parse_interval(interval1)
    iv2 = _parse_interval(interval2)
    if not iv1 or not iv2:
        return None
    if iv1["low"] is None or iv2["low"] is None:
        return None
    l1, l2 = _normalize_for_compare(iv1["low"], iv2["low"])
    if l1 != l2:
        return False
    # CQL Starts also requires iv1.end <= iv2.end (containment at end)
    end1 = _effective_end(iv1)
    end2 = _effective_end(iv2)
    if end1 is None or end2 is None:
        return None
    e1, e2 = _normalize_for_compare(end1, end2)
    return e1 <= e2


def intervalEndsSame(interval1: str | None, interval2: str | None) -> bool | None:
    """CQL §19.13 Ends: iv1 ends iv2 iff iv1.start >= iv2.start AND iv1.end == iv2.end.

    Returns None (NULL) for null/unparseable inputs per CQL three-valued logic.
    """
    iv1 = _parse_interval(interval1)
    iv2 = _parse_interval(interval2)
    if not iv1 or not iv2:
        return None
    if iv1["high"] is None or iv2["high"] is None:
        return None
    h1, h2 = _normalize_for_compare(iv1["high"], iv2["high"])
    if h1 != h2:
        return False
    # CQL Ends also requires iv1.start >= iv2.start (containment at start)
    start1 = _effective_start(iv1)
    start2 = _effective_start(iv2)
    if start1 is None or start2 is None:
        return None
    s1, s2 = _normalize_for_compare(start1, start2)
    return s1 >= s2


def intervalFromBounds(low: str | None, high: str | None, lowClosed: bool = True, highClosed: bool = False) -> str | None:
    """Create an interval from bounds.

    If both bounds are null and no type annotation exists, result is null.
    (Typed null bounds like ``null as Integer`` are passed as ``'__null__'``
    string by the translator to indicate unbounded intervals.)

    Raises ValueError if the interval is invalid (low > high after bound
    normalization), per CQL §2.17.
    """
    if low is None and high is None:
        return None
    # Normalize TIMESTAMP-formatted bounds (space separator → ISO 8601 T + .000)
    # so interval JSON preserves millisecond precision for downstream comparison.
    if isinstance(low, str):
        low = _normalize_timestamp_bound(low)
    if isinstance(high, str):
        high = _normalize_timestamp_bound(high)
    # Validate that low <= high for non-null bounds (CQL §2.17)
    if low is not None and high is not None:
        parsed_low = _parse_interval_bound(low)
        parsed_high = _parse_interval_bound(high)
        if parsed_low is not None and parsed_high is not None:
            try:
                pl, ph = _normalize_for_compare(parsed_low, parsed_high)
                if pl > ph:
                    raise ValueError(
                        f"Invalid Interval - the ending boundary must be greater "
                        f"than or equal to the starting boundary: [{low}, {high}]"
                    )
                if pl == ph and not (lowClosed and highClosed):
                    raise ValueError(
                        f"Invalid Interval - the ending boundary must be greater "
                        f"than or equal to the starting boundary: [{low}, {high}]"
                    )
            except TypeError:
                pass  # incomparable types — let downstream handle
    import json
    return json.dumps({
        "low": _unwrap_bound_for_json(low),
        "high": _unwrap_bound_for_json(high),
        "lowClosed": lowClosed,
        "highClosed": highClosed
    })


def intervalIntersect(interval1: str | None, interval2: str | None) -> str | None:
    """Compute the intersection of two intervals (CQL §19.15).

    Returns the interval where both intervals overlap, or NULL if they
    don't overlap.  Uses _normalize_for_compare for type-safe comparison.
    """
    iv1 = _parse_interval(interval1)
    iv2 = _parse_interval(interval2)
    if not iv1 or not iv2:
        return None

    # Also parse raw JSON to preserve original string representations
    import json as _json
    try:
        raw1 = orjson.loads(interval1) if interval1 else {}
        raw2 = orjson.loads(interval2) if interval2 else {}
    except Exception as e:
        _logger.debug("Unexpected error in UDF intervalIntersect JSON parse: %s", e)
        return None
    # Use parser-normalized raw bounds so discrete open endpoints compare and
    # serialize through their effective CQL Start/End values.
    raw1_low = iv1.get("low_raw")
    raw1_high = iv1.get("high_raw")
    raw2_low = iv2.get("low_raw")
    raw2_high = iv2.get("high_raw")
    raw1_low = None if raw1_low == "__null__" else raw1_low
    raw1_high = None if raw1_high == "__null__" else raw1_high
    raw2_low = None if raw2_low == "__null__" else raw2_low
    raw2_high = None if raw2_high == "__null__" else raw2_high

    # Find the greater of the two lows
    if iv1["low"] is None and iv2["low"] is None:
        new_low_raw = None
        new_low_closed = iv1["low_closed"] and iv2["low_closed"]
    elif iv1["low"] is None:
        if iv1["low_closed"]:
            # Closed null low is unbounded below; the finite low wins.
            new_low_raw = raw2_low
            new_low_closed = iv2["low_closed"]
        else:
            # Open null low is an unknown effective start; preserve it.
            new_low_raw = raw1_low
            new_low_closed = iv1["low_closed"]
    elif iv2["low"] is None:
        if iv2["low_closed"]:
            new_low_raw = raw1_low
            new_low_closed = iv1["low_closed"]
        else:
            new_low_raw = raw2_low
            new_low_closed = iv2["low_closed"]
    else:
        l1, l2 = _normalize_for_compare(iv1["low"], iv2["low"])
        if l1 > l2:
            new_low_raw = raw1_low
            new_low_closed = iv1["low_closed"]
        elif l2 > l1:
            new_low_raw = raw2_low
            new_low_closed = iv2["low_closed"]
        else:
            new_low_raw = raw1_low
            new_low_closed = iv1["low_closed"] and iv2["low_closed"]

    # Find the lesser of the two highs
    if iv1["high"] is None and iv2["high"] is None:
        new_high_raw = None
        new_high_closed = iv1["high_closed"] and iv2["high_closed"]
    elif iv1["high"] is None:
        if iv1["high_closed"]:
            # Closed null high is unbounded above; the finite high wins.
            new_high_raw = raw2_high
            new_high_closed = iv2["high_closed"]
        else:
            # Open null high has no effective end; preserve the unknown bound.
            new_high_raw = raw1_high
            new_high_closed = iv1["high_closed"]
    elif iv2["high"] is None:
        if iv2["high_closed"]:
            new_high_raw = raw1_high
            new_high_closed = iv1["high_closed"]
        else:
            new_high_raw = raw2_high
            new_high_closed = iv2["high_closed"]
    else:
        h1, h2 = _normalize_for_compare(iv1["high"], iv2["high"])
        if h1 < h2:
            new_high_raw = raw1_high
            new_high_closed = iv1["high_closed"]
        elif h2 < h1:
            new_high_raw = raw2_high
            new_high_closed = iv2["high_closed"]
        else:
            new_high_raw = raw1_high
            new_high_closed = iv1["high_closed"] and iv2["high_closed"]

    # Check if result is valid (non-empty) using parsed values for comparison
    new_low_parsed = _parse_interval_bound(new_low_raw)
    new_high_parsed = _parse_interval_bound(new_high_raw)
    if new_low_parsed is not None and new_high_parsed is not None:
        nl, nh = _normalize_for_compare(new_low_parsed, new_high_parsed)
        if nl > nh:
            return None
        if nl == nh and not (new_low_closed and new_high_closed):
            return None

    return _json.dumps({
        "low": _unwrap_bound_for_json(new_low_raw),
        "high": _unwrap_bound_for_json(new_high_raw),
        "lowClosed": new_low_closed,
        "highClosed": new_high_closed,
    })


def intervalUnion(interval1: str | None, interval2: str | None) -> str | None:
    """Compute the union of two intervals (CQL §19.31).

    If the intervals overlap or meet, returns their union.
    If they do not overlap or meet, returns NULL.
    """
    iv1 = _parse_interval(interval1)
    iv2 = _parse_interval(interval2)
    if not iv1 or not iv2:
        return None

    import json as _json

    # Determine whether intervals overlap or meet.
    # Two intervals overlap/meet if max(low) <= min(high) (considering closedness).
    # Also handle null bounds (unbounded).
    def _effective_low(iv):
        return iv["low"]

    def _effective_high(iv):
        return iv["high"]

    # Check overlap or adjacency using successor/predecessor for meets.
    overlap = False

    low1 = _effective_low(iv1)
    high1 = _effective_high(iv1)
    low2 = _effective_low(iv2)
    high2 = _effective_high(iv2)

    # If either interval has unbounded side towards the other, they overlap.
    # iv1.high is None (unbounded above) → overlaps with iv2 regardless of iv2's low
    # iv2.low is None (unbounded below) → overlaps with iv1 regardless of iv1's high
    if high1 is None or low2 is None or low1 is None or high2 is None:
        overlap = True
    else:
        # Both intervals have finite bounds.
        # They overlap if iv1.high >= iv2.low and iv2.high >= iv1.low.
        try:
            h1, l2 = _normalize_for_compare(high1, low2)
            h2, l1 = _normalize_for_compare(high2, low1)

            # Check if iv1 is entirely before iv2
            if h1 < l2:
                # Before concluding no overlap, check for adjacency (meets)
                # via successor: if successor(iv1.high) == iv2.low, they meet
                try:
                    succ = _successor_for_bound(high1, iv1.get("high_raw"))
                    if succ is not None:
                        s, l2n = _normalize_for_compare(succ, low2)
                        if s == l2n:
                            overlap = True
                except Exception as e:
                    _logger.debug("Unexpected error in UDF union successor check: %s", e)
                if not overlap:
                    # Also check reverse direction
                    pass
            elif h1 > l2:
                # iv1.high > iv2.low → must also check iv2.high >= iv1.low
                if h2 < l1:
                    # Check successor for reverse adjacency
                    try:
                        succ = _successor_for_bound(high2, iv2.get("high_raw"))
                        if succ is not None:
                            s, l1n = _normalize_for_compare(succ, low1)
                            if s == l1n:
                                overlap = True
                    except Exception as e:
                        _logger.debug("Unexpected error in UDF union reverse successor check: %s", e)
                else:
                    overlap = True
            else:
                # h1 == l2: overlap only if at least one side is closed
                if iv1["high_closed"] or iv2["low_closed"]:
                    overlap = True
                else:
                    # Check for adjacency (meets): successor(iv1.high) == iv2.low
                    # For integer types, successor is +1
                    try:
                        succ = _successor_for_bound(high1, iv1.get("high_raw"))
                        s, l2n = _normalize_for_compare(succ, low2)
                        if s == l2n:
                            overlap = True
                    except Exception as e:
                        _logger.debug("Unexpected error in UDF union adjacency check: %s", e)

            # Also check the reverse direction if not yet overlapping
            if not overlap and h2 == l1:
                if iv2["high_closed"] or iv1["low_closed"]:
                    overlap = True
                else:
                    try:
                        succ = _successor_for_bound(high2, iv2.get("high_raw"))
                        s, l1n = _normalize_for_compare(succ, low1)
                        if s == l1n:
                            overlap = True
                    except Exception as e:
                        _logger.debug("Unexpected error in UDF union reverse adjacency check: %s", e)
        except Exception as e:
            _logger.debug("Unexpected error in UDF intervalUnion overlap detection: %s", e)
            return None

    if not overlap:
        return None

    # Compute the union from effective Start/End boundaries. _parse_interval()
    # normalizes finite open bounds to equivalent closed effective bounds.
    raw1_low = iv1.get("low_raw")
    raw1_high = iv1.get("high_raw")
    raw2_low = iv2.get("low_raw")
    raw2_high = iv2.get("high_raw")

    # Min of lows
    if low1 is None:
        new_low_raw = raw1_low
        new_low_closed = iv1["low_closed"]
    elif low2 is None:
        new_low_raw = raw2_low
        new_low_closed = iv2["low_closed"]
    else:
        l1n, l2n = _normalize_for_compare(low1, low2)
        if l1n < l2n:
            new_low_raw = raw1_low
            new_low_closed = iv1["low_closed"]
        elif l2n < l1n:
            new_low_raw = raw2_low
            new_low_closed = iv2["low_closed"]
        else:
            new_low_raw = raw1_low
            new_low_closed = iv1["low_closed"] or iv2["low_closed"]

    # Max of highs
    if high1 is None:
        new_high_raw = raw1_high
        new_high_closed = iv1["high_closed"]
    elif high2 is None:
        new_high_raw = raw2_high
        new_high_closed = iv2["high_closed"]
    else:
        h1n, h2n = _normalize_for_compare(high1, high2)
        if h1n > h2n:
            new_high_raw = raw1_high
            new_high_closed = iv1["high_closed"]
        elif h2n > h1n:
            new_high_raw = raw2_high
            new_high_closed = iv2["high_closed"]
        else:
            new_high_raw = raw1_high
            new_high_closed = iv1["high_closed"] or iv2["high_closed"]

    return _json.dumps({
        "low": _unwrap_bound_for_json(new_low_raw),
        "high": _unwrap_bound_for_json(new_high_raw),
        "lowClosed": new_low_closed,
        "highClosed": new_high_closed,
    })


def intervalExcept(interval1: str | None, interval2: str | None) -> str | None:
    """CQL §19.12: Compute the set difference of two intervals.

    Returns the portion of interval1 not in interval2.
    If they don't overlap, returns interval1.
    If interval2 completely contains interval1, returns null.
    """
    import json as _json
    iv1 = _parse_interval(interval1)
    iv2 = _parse_interval(interval2)
    if not iv1:
        return None
    if not iv2:
        return interval1

    low1 = iv1["low"]
    high1 = iv1["high"]
    low2 = iv2["low"]
    high2 = iv2["high"]

    # Check if intervals overlap
    overlap = False
    if (low1 is None or high2 is None) and (high1 is None or low2 is None):
        overlap = True
    elif low1 is None or high2 is None:
        # iv1 starts at -∞ or iv2 ends at +∞
        if low2 is not None and high1 is not None:
            l2, h1 = _normalize_for_compare(low2, high1)
            overlap = l2 <= h1
        else:
            overlap = True
    elif high1 is None or low2 is None:
        if low1 is not None and high2 is not None:
            l1, h2 = _normalize_for_compare(low1, high2)
            overlap = l1 <= h2
        else:
            overlap = True
    else:
        h1, l2 = _normalize_for_compare(high1, low2)
        l1, h2 = _normalize_for_compare(low1, high2)
        if h1 < l2 or h2 < l1:
            overlap = False
        elif h1 == l2 and not (iv1["high_closed"] and iv2["low_closed"]):
            overlap = False
        elif h2 == l1 and not (iv2["high_closed"] and iv1["low_closed"]):
            overlap = False
        else:
            overlap = True

    if not overlap:
        return interval1

    # Parse raw JSON for output
    try:
        raw1 = orjson.loads(interval1) if interval1 else {}
        raw2 = orjson.loads(interval2) if interval2 else {}
    except Exception as e:
        _logger.debug("Unexpected error in UDF intervalExcept JSON parse: %s", e)
        return None
    raw1_low = raw1.get("low") or raw1.get("start")
    raw1_high = raw1.get("high") or raw1.get("end")
    raw2_low = raw2.get("low") or raw2.get("start")
    raw2_high = raw2.get("high") or raw2.get("end")

    # Check if iv2 completely contains iv1 → result is null
    # iv2 contains iv1 if iv2.low <= iv1.low and iv2.high >= iv1.high
    iv2_contains_iv1 = True
    if low1 is not None and low2 is not None:
        l1n, l2n = _normalize_for_compare(low1, low2)
        if l2n > l1n:
            iv2_contains_iv1 = False
        elif l2n == l1n and not iv2["low_closed"] and iv1["low_closed"]:
            iv2_contains_iv1 = False
    elif low2 is not None and low1 is None:
        iv2_contains_iv1 = False
    if high1 is not None and high2 is not None:
        h1n, h2n = _normalize_for_compare(high1, high2)
        if h2n < h1n:
            iv2_contains_iv1 = False
        elif h2n == h1n and not iv2["high_closed"] and iv1["high_closed"]:
            iv2_contains_iv1 = False
    elif high2 is not None and high1 is None:
        iv2_contains_iv1 = False

    if iv2_contains_iv1:
        return None

    # iv2 partially overlaps iv1 — determine which portion of iv1 remains.
    # If iv2.low > iv1.low AND iv2.high < iv1.high → iv2 splits iv1 → null
    # If iv2.low > iv1.low (only) → left portion: [iv1.low, predecessor(iv2.low)]
    # If iv2.high < iv1.high (only) → right portion: [successor(iv2.high), iv1.high]
    has_left = False
    has_right = False
    if low2 is not None and low1 is not None:
        l1n, l2n = _normalize_for_compare(low1, low2)
        if l2n > l1n:
            has_left = True
    elif low2 is not None and low1 is None:
        has_left = True  # iv1 starts at -∞, so iv2.low is always > iv1.low
    if high2 is not None and high1 is not None:
        h1n, h2n = _normalize_for_compare(high1, high2)
        if h2n < h1n:
            has_right = True
    elif high2 is not None and high1 is None:
        has_right = True  # iv1 ends at +∞, so iv2.high is always < iv1.high

    # CQL except returns only one contiguous interval; if iv2 splits iv1, return null.
    if has_left and has_right:
        return None

    if has_left:
        new_high_raw = raw2_low
        new_high_closed = not iv2["low_closed"]
        new_high_raw, new_high_closed = _normalize_bound_for_output(
            new_high_raw, new_high_closed, is_high=True, parsed=low2)
        return _json.dumps({
            "low": _unwrap_bound_for_json(raw1_low),
            "high": _unwrap_bound_for_json(new_high_raw),
            "lowClosed": iv1["low_closed"],
            "highClosed": new_high_closed,
        })

    if has_right:
        new_low_raw = raw2_high
        new_low_closed = not iv2["high_closed"]
        new_low_raw, new_low_closed = _normalize_bound_for_output(
            new_low_raw, new_low_closed, is_high=False, parsed=high2)
        return _json.dumps({
            "low": _unwrap_bound_for_json(new_low_raw),
            "high": _unwrap_bound_for_json(raw1_high),
            "lowClosed": new_low_closed,
            "highClosed": iv1["high_closed"],
        })

    return None


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
    if not isinstance(raw_list, list):
        return None
    if len(raw_list) == 0:
        return "[]"

    # Detect input type for output formatting
    input_type = "numeric"  # default
    quantity_unit = None
    for item in raw_list:
        # Parse string items (JSON-encoded intervals) into dicts for detection
        check_item = item
        if isinstance(item, str):
            try:
                check_item = orjson.loads(item)
            except (JSONDecodeError, TypeError, ValueError):
                continue
        if isinstance(check_item, dict):
            low_val = check_item.get("low") if "low" in check_item else check_item.get("start")
            high_val = check_item.get("high") if "high" in check_item else check_item.get("end")
            for bv in (low_val, high_val):
                if isinstance(bv, str):
                    bv_s = bv.strip()
                    if bv_s.startswith('{') and '"value"' in bv_s:
                        try:
                            q = orjson.loads(bv_s)
                            if isinstance(q, dict) and "value" in q:
                                input_type = "quantity"
                                quantity_unit = q.get("unit") or q.get("code")
                        except (JSONDecodeError, TypeError, ValueError):
                            pass
                    elif ':' in bv_s and '-' not in bv_s and not bv_s.startswith('{'):
                        input_type = "time"
                    elif _is_day_precision_datetime_string(bv_s):
                        input_type = "datetime_day"
            if input_type != "numeric":
                break

    parsed = []
    for item in raw_list:
        if isinstance(item, str):
            iv = _parse_interval(item)
        elif isinstance(item, dict):
            low_val = item.get("low") if "low" in item else item.get("start")
            high_val = item.get("high") if "high" in item else item.get("end")
            iv = {
                "low": _parse_interval_bound(low_val),
                "high": _parse_interval_bound(high_val),
                "low_closed": item.get("lowClosed", True),
                "high_closed": item.get("highClosed", True),
                "low_raw": low_val,
                "high_raw": high_val,
            }
        else:
            iv = None
        if iv and iv["low"] is not None:
            parsed.append(iv)

    if not parsed:
        return "[]"

    from functools import cmp_to_key

    def _compare_lows(left_iv, right_iv) -> int:
        left_low = left_iv.get("low")
        right_low = right_iv.get("low")
        if left_low is None and right_low is None:
            return 0
        if left_low is None:
            return -1
        if right_low is None:
            return 1
        cmp = _precision_aware_compare(left_low, right_low)
        return cmp if cmp is not None else 0

    parsed.sort(key=cmp_to_key(_compare_lows))

    merged: list[dict] = [parsed[0]]
    for current in parsed[1:]:
        last = merged[-1]
        if last["high"] is None:
            continue
        if current["low"] is None:
            current_extends = current["high"] is None
            if not current_extends and last["high"] is not None:
                current_high, last_high = _normalize_for_compare(current["high"], last["high"])
                current_extends = current_high >= last_high
            if current_extends:
                last["high"] = current["high"]
                last["high_closed"] = current.get("high_closed", True)
            continue
        last_high, cur_low = _normalize_for_compare(last["high"], current["low"])
        succ_high = _successor_for_bound(last["high"], last.get("high_raw"))
        if succ_high is not None:
            succ_norm, cur_low_norm = _normalize_for_compare(succ_high, current["low"])
            adjacent_or_overlap = succ_norm >= cur_low_norm
        else:
            adjacent_or_overlap = last_high >= cur_low
        if adjacent_or_overlap:
            if current["high"] is None:
                last["high"] = None
                last["high_closed"] = current.get("high_closed", True)
                last["high_raw"] = current.get("high_raw")
            else:
                _, cur_high = _normalize_for_compare(last["high"], current["high"])
                last_h_norm, _ = _normalize_for_compare(last["high"], current["high"])
                if cur_high > last_h_norm:
                    last["high"] = current["high"]
                    last["high_closed"] = current["high_closed"]
                    last["high_raw"] = current.get("high_raw")
                elif cur_high == last_h_norm:
                    last["high_closed"] = last["high_closed"] or current["high_closed"]
        else:
            merged.append(current)

    def _format_bound(val):
        """Format a bound value back to its original type representation."""
        if val is None:
            return None
        if input_type == "time" and isinstance(val, (int, float)):
            ms = int(val)
            h = ms // 3600000
            m = (ms % 3600000) // 60000
            s = (ms % 60000) // 1000
            frac = ms % 1000
            return f"T{h:02d}:{m:02d}:{s:02d}.{frac:03d}"
        if _is_quantity_bound(val):
            try:
                return orjson.loads(val["__cql_quantity_json__"])
            except (JSONDecodeError, TypeError, ValueError):
                return val["__cql_quantity_json__"]
        if input_type == "quantity" and isinstance(val, (int, float)):
            return {"value": val, "unit": quantity_unit}
        if input_type == "datetime_day" and isinstance(val, datetime):
            return _format_day_precision_datetime(val)
        return str(val)

    result = []
    for iv in merged:
        result.append({
            "low": _format_bound(iv["low"]),
            "high": _format_bound(iv["high"]),
            "lowClosed": iv["low_closed"],
            "highClosed": iv["high_closed"],
        })
    return _json.dumps(result)


# ========================================
# expand (CQL §19.25)
# ========================================


def expand(interval_or_list, per: str | None = None) -> str | None:
    """Expand an interval or list of intervals into unit intervals.

    CQL §19.25: The expand operator returns the set of intervals of size per
    for all the ranges in the input. If per is null, a default step is used
    based on the point type of the interval.

    Args:
        interval_or_list: JSON interval string, JSON list of interval strings,
            or Python list of strings (from DuckDB VARCHAR[])
        per: Optional Quantity JSON with the step size, e.g. '{"value":1,"unit":"day"}'

    Returns:
        JSON list of unit interval strings
    """
    return _expand_impl(interval_or_list, per)


def expand1(interval_or_list) -> str | None:
    """1-arg overload of expand for DuckDB UDF registration."""
    return _expand_impl(interval_or_list, None)


def expand_points(interval_or_list, per: str | None = None) -> str | None:
    """Expand a single interval into a list of point values (CQL §19.25 single-interval overload)."""
    return _expand_points_impl(interval_or_list, per)


def expand_points1(interval_or_list) -> str | None:
    """1-arg overload of expand_points."""
    return _expand_points_impl(interval_or_list, None)


def _expand_points_impl(interval_or_list, per) -> str | None:
    """Expand and return only the starting points (not unit intervals).

    CQL §19.25: When given a single interval (not a list), expand returns
    the list of points starting at the lower bound, stepping by *per*.
    """
    raw = _expand_impl(interval_or_list, per)
    if raw is None or raw == "[]":
        return raw
    try:
        intervals = orjson.loads(raw)
    except Exception as e:
        _logger.debug("Unexpected error in UDF expand JSON parse: %s", e)
        return raw
    if not isinstance(intervals, list):
        return raw
    # Extract 'low' from each unit interval
    points = []
    for iv in intervals:
        if isinstance(iv, dict):
            val = iv.get("low") or iv.get("start")
            if val is not None:
                # Try to preserve original type
                try:
                    ival = int(val)
                    if str(ival) == str(val):
                        points.append(ival)
                        continue
                except (ValueError, TypeError):
                    pass
                try:
                    fval = float(val)
                    points.append(fval)
                    continue
                except (ValueError, TypeError):
                    pass
                points.append(val)
        else:
            points.append(iv)
    return orjson.dumps(points).decode("utf-8")


def _parse_expand_per(per):
    """Parse the per (step size) argument for expand."""
    if per is None:
        return None, None, True
    if not isinstance(per, str):
        return None, None, False
    per_stripped = per.strip()
    if not per_stripped.startswith('{'):
        return None, None, False
    try:
        q = orjson.loads(per_stripped)
    except (JSONDecodeError, TypeError, ValueError):
        return None, None, False
    if not isinstance(q, dict):
        return None, None, False
    raw_value = q.get("value")
    if isinstance(raw_value, bool) or not isinstance(raw_value, (int, float)):
        return None, None, False
    step_value = float(raw_value)
    if not math.isfinite(step_value):
        return None, None, False
    step_unit = q.get("unit", "") or q.get("code", "") or ""
    return step_value, step_unit, True


_TEMPORAL_EXPAND_UNITS = {
    "year", "years", "a",
    "month", "months", "mo",
    "week", "weeks", "wk",
    "day", "days", "d",
    "hour", "hours", "h",
    "minute", "minutes", "min",
    "second", "seconds", "s",
    "millisecond", "milliseconds", "ms",
}


def _is_default_expand_unit(unit: str | None) -> bool:
    return unit is None or str(unit).strip().lower() in {"", "1"}


def _is_temporal_expand_unit(unit: str | None) -> bool:
    return str(unit or "").strip().lower() in _TEMPORAL_EXPAND_UNITS


def _expand_quantity(
    low,
    high,
    low_closed: bool,
    high_closed: bool,
    step_value,
    step_unit: str | None,
) -> list:
    low_json = _quantity_json(low)
    high_json = _quantity_json(high)
    if low_json is None or high_json is None:
        return []

    try:
        from .quantity import _parse_quantity, quantityConvert
        low_q = _parse_quantity(low_json)
        if not low_q or low_q.get("value") is None:
            return []
        target_unit = low_q.get("code") or low_q.get("unit") or "1"
        high_converted = quantityConvert(high_json, target_unit)
        high_q = _parse_quantity(high_converted) if high_converted else None
        if not high_q or high_q.get("value") is None:
            return []
        step = Decimal(str(step_value if step_value is not None else 0.00000001))
        if step_unit:
            step_json = orjson.dumps({
                "value": float(step),
                "unit": step_unit,
                "code": step_unit,
                "system": "http://unitsofmeasure.org",
            }).decode("utf-8")
            step_converted = quantityConvert(step_json, target_unit)
            step_q = _parse_quantity(step_converted) if step_converted else None
            if not step_q or step_q.get("value") is None:
                return []
            step = Decimal(str(step_q["value"]))
        if step <= 0:
            return []

        start = Decimal(str(low_q["value"]))
        end = Decimal(str(high_q["value"]))
        if not low_closed:
            start += Decimal("0.00000001")
        if not high_closed:
            end -= Decimal("0.00000001")
        if end < start:
            return []

        result = []
        current = start
        max_points = 10000
        while current <= end and len(result) < max_points:
            value = float(current)
            quantity = {
                "value": value,
                "unit": target_unit,
                "code": target_unit,
                "system": "http://unitsofmeasure.org",
            }
            result.append({
                "low": quantity,
                "high": dict(quantity),
                "lowClosed": True,
                "highClosed": True,
            })
            current += step
        return result
    except (ArithmeticError, JSONDecodeError, TypeError, ValueError):
        return []


def _expand_impl(interval_or_list, per) -> str | None:
    """Core expand implementation."""
    if interval_or_list is None:
        return None

    # Handle Python list from DuckDB VARCHAR[]
    if isinstance(interval_or_list, list):
        if len(interval_or_list) == 0:
            return "[]"
        # Filter out None entries
        items = [item for item in interval_or_list if item is not None]
        if not items:
            return "[]"
        # Parse step
        step_value, step_unit, valid_per = _parse_expand_per(per)
        if not valid_per:
            return None
        # Expand each interval
        result = []
        for item in items:
            if isinstance(item, str) and item.strip().startswith('{'):
                try:
                    parsed = orjson.loads(item.strip())
                    low_raw = parsed.get("low") or parsed.get("start")
                    high_raw = parsed.get("high") or parsed.get("end")
                    low_closed = parsed.get("lowClosed", True)
                    high_closed = parsed.get("highClosed", True)
                    if low_raw is None or high_raw is None:
                        continue
                    low_parsed = _parse_interval_bound(low_raw)
                    high_parsed = _parse_interval_bound(high_raw)
                    if low_parsed is None or high_parsed is None:
                        continue
                    expanded = _expand_single_interval(
                        low_raw, high_raw, low_parsed, high_parsed,
                        low_closed, high_closed, step_value, step_unit
                    )
                    if expanded:
                        result.extend(expanded)
                except (JSONDecodeError, TypeError, ValueError):
                    pass
        return orjson.dumps(result).decode("utf-8") if result else "[]"

    if isinstance(interval_or_list, str):
        stripped = interval_or_list.strip()
    else:
        return None

    if not stripped:
        return None

    # Parse per (step size)
    step_value, step_unit, valid_per = _parse_expand_per(per)
    if not valid_per:
        return None

    # Parse input: could be a list of intervals or a single interval
    intervals = []
    try:
        parsed = orjson.loads(stripped)
    except (JSONDecodeError, TypeError, ValueError):
        return "[]"

    if isinstance(parsed, list):
        if len(parsed) == 0:
            return "[]"
        for item in parsed:
            if item is None:
                continue
            if isinstance(item, dict):
                intervals.append(item)
            elif isinstance(item, str):
                iv = _parse_interval(item)
                if iv:
                    intervals.append(iv)
    elif isinstance(parsed, dict):
        intervals.append(parsed)
    else:
        return "[]"

    if not intervals:
        return "[]"

    result = []
    for iv in intervals:
        low_raw = iv.get("low") or iv.get("start")
        high_raw = iv.get("high") or iv.get("end")
        low_closed = iv.get("lowClosed", True)
        high_closed = iv.get("highClosed", True)

        if low_raw is None or high_raw is None:
            continue

        low_parsed = _parse_interval_bound(low_raw)
        high_parsed = _parse_interval_bound(high_raw)

        if low_parsed is None or high_parsed is None:
            continue

        expanded = _expand_single_interval(
            low_raw, high_raw, low_parsed, high_parsed,
            low_closed, high_closed, step_value, step_unit
        )
        result.extend(expanded)

    return orjson.dumps(result).decode("utf-8")


def _expand_single_interval(
    low_raw, high_raw, low_parsed, high_parsed,
    low_closed: bool, high_closed: bool,
    step_value, step_unit: str | None
) -> list:
    """Expand a single interval into unit intervals."""
    from decimal import Decimal

    # Determine type category
    if _is_quantity_bound(low_parsed) or _is_quantity_bound(high_parsed):
        if step_unit is not None and _is_temporal_expand_unit(step_unit):
            return []
        return _expand_quantity(
            low_parsed, high_parsed, low_closed, high_closed, step_value, step_unit
        )
    # Check for time values first: they are parsed as millis (integers) but raw values are time strings.
    if isinstance(low_parsed, (int, float)) and not isinstance(low_parsed, bool):
        raw_str = str(low_raw) if low_raw is not None else ""
        if ':' in raw_str and '-' not in raw_str:
            return _expand_time(low_raw, high_raw, low_parsed, high_parsed,
                                low_closed, high_closed, step_value, step_unit)
    if isinstance(low_parsed, (date, datetime)):
        if step_unit is not None and not _is_temporal_expand_unit(step_unit):
            return []
        return _expand_temporal(low_raw, high_raw, low_parsed, high_parsed,
                                low_closed, high_closed, step_value, step_unit)
    elif isinstance(low_parsed, int) and not isinstance(low_parsed, bool):
        if not _is_default_expand_unit(step_unit):
            return []
        # If step_value is fractional, promote integer to decimal.
        # Integer Interval[10, 10] spans [10.0, 10.99999999] in decimal space.
        if step_value is not None and float(step_value) != int(float(step_value)):
            promoted_low = float(low_parsed) if low_closed else float(low_parsed + 1)
            promoted_high = float(high_parsed + 1) - 1e-8 if high_closed else float(high_parsed) - 1e-8
            return _expand_numeric(promoted_low, promoted_high,
                                   True, True, step_value, is_int=False)
        return _expand_numeric(low_parsed, high_parsed, low_closed, high_closed,
                               step_value, is_int=True)
    elif isinstance(low_parsed, float):
        if not _is_default_expand_unit(step_unit):
            return []
        return _expand_numeric(low_parsed, high_parsed, low_closed, high_closed,
                               step_value, is_int=False)
    else:
        # Could be time (stored as millis) — check if raw values look like times
        raw_str = str(low_raw)
        if ':' in raw_str and '-' not in raw_str:
            if step_unit is not None and not _is_temporal_expand_unit(step_unit):
                return []
            return _expand_time(low_raw, high_raw, low_parsed, high_parsed,
                                low_closed, high_closed, step_value, step_unit)
        return []


def _expand_numeric(low, high, low_closed, high_closed, step_value, is_int=True):
    """Expand a numeric interval into unit intervals.

    CQL §19.25: Each sub-interval has size = per.
    For integers per N: [start, start+N-1] (N integer points).
    For decimals per X: [start, start] (unit interval at per-precision).
    """
    from decimal import Decimal, ROUND_HALF_UP

    if step_value is None:
        step = 1 if is_int else Decimal("0.00000001")
    else:
        step = int(step_value) if is_int and float(step_value) == int(float(step_value)) else float(step_value)

    # Adjust for open boundaries using predecessor step (not per step)
    start = low
    end = high
    if not low_closed:
        start = start + 1 if is_int else start + 1e-8
    if not high_closed:
        end = end - 1 if is_int else end - 1e-8

    if is_int:
        start = int(start)
        end = int(end)
        step = int(step) if step == int(step) else step
    else:
        start = Decimal(str(start))
        end = Decimal(str(end))
        step = Decimal(str(step))

    result = []
    current = start
    max_items = 10000
    while current <= end and len(result) < max_items:
        if is_int:
            iv_end = int(current + step - 1)
            if iv_end > int(end):
                break  # Drop partial interval at end per CQL §19.25
            result.append({
                "low": int(current),
                "high": int(iv_end),
                "lowClosed": True,
                "highClosed": True,
            })
        else:
            # Decimal: unit (point) intervals
            result.append({
                "low": float(current),
                "high": float(current),
                "lowClosed": True,
                "highClosed": True,
            })
        current = current + step

    return result


def _expand_temporal(low_raw, high_raw, low_parsed, high_parsed,
                     low_closed, high_closed, step_value, step_unit):
    """Expand a date/datetime interval into unit intervals."""
    # Determine default step
    if step_unit is None:
        # Default based on type
        if isinstance(low_parsed, datetime):
            step_unit = "millisecond"
            step_value = 1.0
        else:
            step_unit = "day"
            step_value = 1.0
    elif not _is_temporal_expand_unit(step_unit):
        return []
    if step_value is None:
        step_value = 1.0

    unit_map = {
        "year": "years", "years": "years",
        "month": "months", "months": "months",
        "week": "weeks", "weeks": "weeks",
        "day": "days", "days": "days",
        "hour": "hours", "hours": "hours",
        "minute": "minutes", "minutes": "minutes",
        "second": "seconds", "seconds": "seconds",
        "millisecond": "milliseconds", "milliseconds": "milliseconds",
    }
    td_unit = unit_map.get(step_unit.lower(), "days")

    from dateutil.relativedelta import relativedelta

    def _add_step(dt, n=1):
        count = int(step_value * n)
        if td_unit in ("years",):
            return dt + relativedelta(years=count)
        elif td_unit in ("months",):
            return dt + relativedelta(months=count)
        elif td_unit in ("weeks",):
            return dt + timedelta(weeks=count)
        elif td_unit in ("days",):
            return dt + timedelta(days=count)
        elif td_unit in ("hours",):
            return dt + timedelta(hours=count)
        elif td_unit in ("minutes",):
            return dt + timedelta(minutes=count)
        elif td_unit in ("seconds",):
            return dt + timedelta(seconds=count)
        elif td_unit in ("milliseconds",):
            return dt + timedelta(milliseconds=count)
        return dt + timedelta(days=count)

    def _sub_step(dt, n=1):
        count = int(step_value * n)
        if td_unit in ("years",):
            return dt - relativedelta(years=count)
        elif td_unit in ("months",):
            return dt - relativedelta(months=count)
        elif td_unit in ("weeks",):
            return dt - timedelta(weeks=count)
        elif td_unit in ("days",):
            return dt - timedelta(days=count)
        elif td_unit in ("hours",):
            return dt - timedelta(hours=count)
        elif td_unit in ("minutes",):
            return dt - timedelta(minutes=count)
        elif td_unit in ("seconds",):
            return dt - timedelta(seconds=count)
        elif td_unit in ("milliseconds",):
            return dt - timedelta(milliseconds=count)
        return dt - timedelta(days=count)

    # Ensure both are same type
    if isinstance(low_parsed, date) and not isinstance(low_parsed, datetime):
        if isinstance(high_parsed, datetime):
            low_parsed = datetime(low_parsed.year, low_parsed.month, low_parsed.day)
    if isinstance(high_parsed, date) and not isinstance(high_parsed, datetime):
        if isinstance(low_parsed, datetime):
            high_parsed = datetime(high_parsed.year, high_parsed.month, high_parsed.day)

    start = low_parsed
    end = high_parsed
    if not low_closed:
        start = _add_step(start)
    if not high_closed:
        end = _sub_step(end)

    def _format_dt(dt):
        if isinstance(dt, datetime):
            return dt.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3]
        elif isinstance(dt, date):
            return dt.strftime("%Y-%m-%d")
        return str(dt)

    result = []
    current = start
    max_items = 10000
    while current <= end and len(result) < max_items:
        iv_end = _add_step(current)
        # The unit interval ends just before the next step
        # For dates: predecessor is -1 day, for datetime: -1 ms
        if isinstance(current, datetime):
            iv_end_actual = iv_end - timedelta(milliseconds=1)
        elif isinstance(current, date):
            iv_end_actual = iv_end - timedelta(days=1)
        else:
            iv_end_actual = iv_end

        if iv_end_actual > end:
            iv_end_actual = end

        result.append({
            "low": _format_dt(current),
            "high": _format_dt(iv_end_actual),
            "lowClosed": True,
            "highClosed": True,
        })
        current = iv_end

    return result


def _expand_time(low_raw, high_raw, low_parsed_millis, high_parsed_millis,
                 low_closed, high_closed, step_value, step_unit):
    """Expand a time interval into unit intervals.

    CQL §19.25: If per is more precise than the boundary precision, return empty.
    Output times are formatted at the per unit's precision.
    """
    if step_unit is None:
        step_unit = "hour"
        step_value = 1.0
    elif not _is_temporal_expand_unit(step_unit):
        return []
    if step_value is None:
        step_value = 1.0

    millis_per = {
        "hour": 3600000, "hours": 3600000,
        "minute": 60000, "minutes": 60000,
        "second": 1000, "seconds": 1000,
        "millisecond": 1, "milliseconds": 1,
    }
    # Precision levels: higher = more precise
    precision_rank = {"hour": 0, "hours": 0, "minute": 1, "minutes": 1,
                      "second": 2, "seconds": 2, "millisecond": 3, "milliseconds": 3}

    # Determine input precision from raw time string
    raw_str = str(low_raw).strip().lstrip('T')
    parts = raw_str.split(':')
    if len(parts) == 1:
        input_rank = 0  # hour only
    elif len(parts) == 2:
        input_rank = 1  # HH:MM
    elif '.' in parts[-1]:
        input_rank = 3  # HH:MM:SS.mmm
    else:
        input_rank = 2  # HH:MM:SS

    per_rank = precision_rank.get(step_unit.lower(), 0)

    # If per is more precise than boundary, return empty
    if per_rank > input_rank:
        return []

    step_ms = int(step_value * millis_per.get(step_unit.lower(), 3600000))

    start_ms = int(low_parsed_millis)
    end_ms = int(high_parsed_millis)
    # Open bounds: exclude the exact boundary, not the step.
    # Per CQL expand semantics, we include unit intervals that fit within the bounds.
    if not low_closed:
        start_ms += 1  # exclude exact low boundary
    if not high_closed:
        end_ms -= 1  # exclude exact high boundary

    def _ms_to_time(ms, rank):
        h = ms // 3600000
        m = (ms % 3600000) // 60000
        s = (ms % 60000) // 1000
        ml = ms % 1000
        if rank == 0:
            return f"T{h:02d}"
        elif rank == 1:
            return f"T{h:02d}:{m:02d}"
        elif rank == 2:
            return f"T{h:02d}:{m:02d}:{s:02d}"
        else:
            return f"T{h:02d}:{m:02d}:{s:02d}.{ml:03d}"

    result = []
    current = start_ms
    max_items = 10000
    while current <= end_ms and len(result) < max_items:
        iv_end = current + step_ms - 1
        if iv_end > end_ms:
            iv_end = end_ms
        result.append({
            "low": _ms_to_time(current, per_rank),
            "high": _ms_to_time(current, per_rank),
            "lowClosed": True,
            "highClosed": True,
        })
        current = current + step_ms

    return result


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
    con.create_function("interval_size", interval_size, null_handling="special")
    con.create_function("intervalContains", intervalContains, null_handling="special")
    con.create_function("intervalProperlyContains", intervalProperlyContains, null_handling="special")
    con.create_function("intervalOverlaps", intervalOverlaps, null_handling="special")
    con.create_function("intervalBefore", intervalBefore, null_handling="special")
    con.create_function("intervalAfter", intervalAfter, null_handling="special")
    con.create_function("intervalOnOrAfter", intervalOnOrAfter, null_handling="special")
    con.create_function("intervalOnOrBefore", intervalOnOrBefore, null_handling="special")
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
    con.create_function("intervalEquals", intervalEquals, null_handling="special")
    con.create_function("intervalEquivalent", intervalEquivalent, null_handling="special")
    con.create_function("intervalContainsPrecise", intervalContainsPrecise, null_handling="special")
    con.create_function("intervalOverlapsPrecise", intervalOverlapsPrecise, null_handling="special")
    con.create_function("intervalIncludesPrecise", intervalIncludesPrecise, null_handling="special")
    con.create_function("intervalIncludedInPrecise", intervalIncludedInPrecise, null_handling="special")
    con.create_function("intervalBeforePrecise", intervalBeforePrecise, null_handling="special")
    con.create_function("intervalAfterPrecise", intervalAfterPrecise, null_handling="special")
    con.create_function("intervalOverlapsBeforePrecise", intervalOverlapsBeforePrecise, null_handling="special")
    con.create_function("intervalOverlapsAfterPrecise", intervalOverlapsAfterPrecise, null_handling="special")
    con.create_function("intervalFromBounds", intervalFromBounds, null_handling="special")
    con.create_function("intervalIntersect", intervalIntersect, null_handling="special")
    con.create_function("intervalUnion", intervalUnion, null_handling="special")
    con.create_function("intervalExcept", intervalExcept, null_handling="special")
    con.create_function("pointFrom", pointFrom, null_handling="special")
    con.create_function("collapse_intervals", collapse_intervals, null_handling="special")
    con.create_function("expand", expand, parameters=["VARCHAR[]", "VARCHAR"], return_type="VARCHAR", null_handling="special")
    con.create_function("expand1", expand1, parameters=["VARCHAR[]"], return_type="VARCHAR", null_handling="special")
    con.create_function("expand_points", expand_points, parameters=["VARCHAR", "VARCHAR"], return_type="VARCHAR", null_handling="special")
    con.create_function("expand_points1", expand_points1, parameters=["VARCHAR"], return_type="VARCHAR", null_handling="special")


__all__ = [
    "registerIntervalUdfs",
    "intervalStart",
    "intervalEnd",
    "intervalWidth",
    "interval_size",
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
    "intervalEquals",
    "intervalEquivalent",
    "intervalContainsPrecise",
    "intervalOverlapsPrecise",
    "intervalIncludesPrecise",
    "intervalIncludedInPrecise",
    "intervalBeforePrecise",
    "intervalAfterPrecise",
    "intervalOverlapsBeforePrecise",
    "intervalOverlapsAfterPrecise",
    "intervalFromBounds",
    "intervalIntersect",
    "collapse_intervals",
]
