"""
CQL Math Function UDFs

DEPRECATED: These UDFs are superseded by Tier 1 SQL macros in macros/math.py
which provide zero Python overhead. These are retained for backward compatibility
with code that references the mathAbs/mathRound/etc. function names directly.
New code should use the SQL macro versions (Abs, Round, Floor, etc.) instead.
"""
from __future__ import annotations
from typing import TYPE_CHECKING
import math

if TYPE_CHECKING:
    import duckdb



import logging

_logger = logging.getLogger(__name__)
def mathAbs(x: float | int | None) -> float | int | None:
    """CQL Abs(x)."""
    if x is None:
        return None
    return abs(x)


def mathRound(x: float | None, precision: int = 0) -> float | None:
    """CQL Round(x, precision)."""
    if x is None:
        return None
    return round(x, precision)


def mathFloor(x: float | None) -> int | None:
    """CQL Floor(x)."""
    if x is None:
        return None
    return math.floor(x)


def mathCeiling(x: float | None) -> int | None:
    """CQL Ceiling(x)."""
    if x is None:
        return None
    return math.ceil(x)


def mathSqrt(x: float | None) -> float | None:
    """CQL Sqrt(x)."""
    if x is None or x < 0:
        return None
    return math.sqrt(x)


def mathExp(x: float | None) -> float | None:
    """CQL Exp(x) (§16.6).

    If the result overflows (positive infinity), raise an error.
    """
    if x is None:
        return None
    result = math.exp(x)
    if math.isinf(result):
        raise ValueError(f"Exp({x}) results in overflow (positive infinity)")
    return result


def mathLn(x: float | None) -> float | None:
    """CQL Ln(x) - natural logarithm (§16.12).

    Ln(0) results in negative infinity → runtime error.
    Ln(negative) is undefined → returns null.
    """
    if x is None:
        return None
    if x == 0 or x == -0.0:
        raise ValueError("Ln(0) results in negative infinity")
    if x < 0:
        return None
    return math.log(x)


def mathLog(x: float | None, base: float = 10) -> float | None:
    """CQL Log(x, base) (§16.11).

    Undefined for x <= 0, base <= 0, or base == 1.
    """
    if x is None or base is None:
        return None
    if x <= 0 or base <= 0 or base == 1:
        raise ValueError(f"Log is undefined for x={x}, base={base}")
    return math.log(x, base)


def mathPower(x: float | None, exponent: float) -> float | None:
    """CQL Power(x, y)."""
    if x is None or exponent is None:
        return None
    try:
        return math.pow(x, exponent)
    except ValueError as e:
        _logger.warning("UDF mathPower failed: %s", e)
        return None


def mathTruncate(x: float | None) -> int | None:
    """CQL Truncate(x) - integer part."""
    if x is None:
        return None
    return math.trunc(x)


def predecessorOf(x) -> str | float | int | None:
    """CQL Predecessor (§22.25): returns the value one step less than x.

    Integer/Long: x - 1, Decimal: x - 10^-8, Date: x - 1 day,
    DateTime: x - 1 ms, Time: x - 1 ms, Quantity: value - step.
    """
    if x is None:
        return None
    from decimal import Decimal
    from datetime import date, datetime, timedelta
    # Handle date/datetime objects
    if isinstance(x, datetime):
        return (x - timedelta(milliseconds=1)).isoformat()
    if isinstance(x, date):
        return (x - timedelta(days=1)).isoformat()
    # Handle strings: time strings, date/datetime strings, quantity JSON
    if isinstance(x, str):
        x_stripped = x.strip()
        # Time string (T-prefixed or HH:MM:SS pattern)
        if x_stripped.startswith('T') or (len(x_stripped) >= 5 and x_stripped[2:3] == ':'):
            t_str = x_stripped.lstrip('T')
            parts = t_str.split(':')
            h = int(parts[0])
            m = int(parts[1]) if len(parts) > 1 else 0
            s_parts = parts[2].split('.') if len(parts) > 2 else ['0']
            s = int(s_parts[0])
            ms = int(s_parts[1].ljust(3, '0')[:3]) if len(s_parts) > 1 else 0
            total_ms = ((h * 60 + m) * 60 + s) * 1000 + ms - 1
            if total_ms < 0:
                raise ValueError(
                    "The result of the predecessor operation precedes "
                    "the minimum value allowed for type Time"
                )
            rh, rem = divmod(total_ms, 3600000)
            rm, rem = divmod(rem, 60000)
            rs, rms = divmod(rem, 1000)
            return f"T{rh:02d}:{rm:02d}:{rs:02d}.{rms:03d}"
        # Quantity JSON
        if x_stripped.startswith('{') and '"value"' in x_stripped:
            import json as _json
            try:
                q = _json.loads(x_stripped)
                v = q.get('value', 0)
                q['value'] = float(Decimal(str(v)) - Decimal("0.00000001"))
                return _json.dumps(q)
            except Exception:
                return None
        # Date/datetime string
        try:
            from datetime import date as _d, datetime as _dt
            if 'T' in x_stripped or ' ' in x_stripped:
                dt = _dt.fromisoformat(x_stripped.replace('Z', '+00:00').replace(' ', 'T'))
                return (dt - timedelta(milliseconds=1)).isoformat()
            parsed = _d.fromisoformat(x_stripped)
            return (parsed - timedelta(days=1)).isoformat()
        except ValueError:
            pass
        # Try numeric string
        try:
            v = Decimal(x_stripped)
            return float(v - Decimal("0.00000001"))
        except Exception:
            return None
    if isinstance(x, Decimal) or isinstance(x, float):
        return x - Decimal("0.00000001") if isinstance(x, Decimal) else float(x) - 1e-8
    return int(x) - 1


def successorOf(x) -> str | float | int | None:
    """CQL Successor (§22.26): returns the value one step greater than x.

    Integer/Long: x + 1, Decimal: x + 10^-8, Date: x + 1 day,
    DateTime: x + 1 ms, Time: x + 1 ms, Quantity: value + step.
    """
    if x is None:
        return None
    from decimal import Decimal
    from datetime import date, datetime, timedelta
    # Handle date/datetime objects
    if isinstance(x, datetime):
        return (x + timedelta(milliseconds=1)).isoformat()
    if isinstance(x, date):
        return (x + timedelta(days=1)).isoformat()
    # Handle strings
    if isinstance(x, str):
        x_stripped = x.strip()
        # Time string
        if x_stripped.startswith('T') or (len(x_stripped) >= 5 and x_stripped[2:3] == ':'):
            t_str = x_stripped.lstrip('T')
            parts = t_str.split(':')
            h = int(parts[0])
            m = int(parts[1]) if len(parts) > 1 else 0
            s_parts = parts[2].split('.') if len(parts) > 2 else ['0']
            s = int(s_parts[0])
            ms = int(s_parts[1].ljust(3, '0')[:3]) if len(s_parts) > 1 else 0
            total_ms = ((h * 60 + m) * 60 + s) * 1000 + ms + 1
            # Maximum time is T23:59:59.999 = 86399999 ms
            if total_ms > 86399999:
                raise ValueError(
                    "The result of the successor operation exceeds "
                    "the maximum value allowed for type Time"
                )
            rh, rem = divmod(total_ms, 3600000)
            rm, rem = divmod(rem, 60000)
            rs, rms = divmod(rem, 1000)
            return f"T{rh:02d}:{rm:02d}:{rs:02d}.{rms:03d}"
        # Quantity JSON
        if x_stripped.startswith('{') and '"value"' in x_stripped:
            import json as _json
            try:
                q = _json.loads(x_stripped)
                v = q.get('value', 0)
                q['value'] = float(Decimal(str(v)) + Decimal("0.00000001"))
                return _json.dumps(q)
            except Exception:
                return None
        # Date/datetime string
        try:
            from datetime import date as _d, datetime as _dt
            if 'T' in x_stripped or ' ' in x_stripped:
                dt = _dt.fromisoformat(x_stripped.replace('Z', '+00:00').replace(' ', 'T'))
                return (dt + timedelta(milliseconds=1)).isoformat()
            parsed = _d.fromisoformat(x_stripped)
            return (parsed + timedelta(days=1)).isoformat()
        except ValueError:
            pass
        # Try numeric string
        try:
            v = Decimal(x_stripped)
            return float(v + Decimal("0.00000001"))
        except Exception:
            return None
    if isinstance(x, Decimal) or isinstance(x, float):
        return x + Decimal("0.00000001") if isinstance(x, Decimal) else float(x) + 1e-8
    return int(x) + 1


def highBoundary(value, precision: int | None = None) -> str | float | None:
    """CQL HighBoundary(value, precision) — §22.10.

    Returns the highest value within the given precision of the input.
    For Decimal: fills remaining digits with 9s.
    For Date/DateTime: fills to end of the precision period.
    For Time: fills to end of the precision period.
    """
    if value is None or precision is None:
        return None
    precision = int(precision)

    # Handle Decimal (DuckDB passes DECIMAL type as Python Decimal object)
    from decimal import Decimal as _Decimal
    if isinstance(value, (int, float, _Decimal)):
        d_str = str(value)
        # Count current decimal places
        if '.' in d_str:
            current_dec_places = len(d_str.split('.')[1])
        else:
            current_dec_places = 0
        # precision = target number of decimal places
        digits_to_fill = precision - current_dec_places
        if digits_to_fill <= 0:
            return float(value)
        if '.' not in d_str:
            d_str += '.'
        d_str += '9' * digits_to_fill
        return float(d_str)

    # Handle datetime/date/time as strings
    if isinstance(value, str):
        return _high_boundary_temporal(value, precision)

    # Handle DuckDB timestamp/date objects
    from datetime import date, datetime
    if isinstance(value, datetime):
        return _high_boundary_temporal(value.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3], precision)
    if isinstance(value, date):
        return _high_boundary_temporal(value.strftime("%Y-%m-%d"), precision)

    return None


def _high_boundary_temporal(value_str: str, precision: int) -> str | None:
    """Fill a temporal value to its high boundary at the given precision.

    CQL precision → component mapping:
    4=year, 6=month, 8=day, 10=hour, 12=minute, 14=second, 17=millisecond
    Time: 2=hour, 4=minute, 6=second, 9=millisecond
    """
    s = value_str.strip().replace(' ', 'T')
    # Detect time-only
    is_time = ':' in s and '-' not in s
    if is_time:
        s = s.lstrip('T')
        parts = s.split(':')
        h = parts[0] if len(parts) > 0 else '00'
        m = parts[1] if len(parts) > 1 else '59'
        sec_parts = parts[2].split('.') if len(parts) > 2 else ['59', '999']
        sec = sec_parts[0] if len(sec_parts) > 0 else '59'
        ms = sec_parts[1] if len(sec_parts) > 1 else '999'

        if precision <= 2:  # hour only
            return f"T{h}:59:59.999"
        elif precision <= 4:  # hour:minute
            return f"T{h}:{m}:59.999"
        elif precision <= 6:  # second
            return f"T{h}:{m}:{sec}.999"
        return f"T{h}:{m}:{sec}.{ms}"

    # DateTime/Date precision levels (digit count):
    # 4=Y, 6=YM, 8=YMD, 10=YMDH, 12=YMDHm, 14=YMDHms, 17=YMDHmsf
    # Fill missing components to their high values, but STOP at the
    # requested precision level (CQL §22.10).
    year = s[:4]
    month = s[5:7] if len(s) > 5 else '12'
    import calendar
    day_max = calendar.monthrange(int(year), int(month))[1]
    day = s[8:10] if len(s) > 8 else f'{day_max:02d}'
    # Recalculate day_max now that month is finalized
    if month == '12' and not (len(s) > 5):
        day = '31'
    hour = s[11:13] if len(s) > 11 else '23'
    minute = s[14:16] if len(s) > 14 else '59'
    second = s[17:19] if len(s) > 17 else '59'
    ms = s[20:23] if len(s) > 20 else '999'

    if precision <= 4:
        return year
    elif precision <= 6:
        return f"{year}-{month}"
    elif precision <= 8:
        return f"{year}-{month}-{day}"
    elif precision <= 10:
        return f"{year}-{month}-{day}T{hour}"
    elif precision <= 12:
        return f"{year}-{month}-{day}T{hour}:{minute}"
    elif precision <= 14:
        return f"{year}-{month}-{day}T{hour}:{minute}:{second}"
    else:
        return f"{year}-{month}-{day}T{hour}:{minute}:{second}.{ms}"


def lowBoundary(value, precision: int | None = None) -> str | float | None:
    """CQL LowBoundary(value, precision) — §22.14.

    Returns the lowest value within the given precision of the input.
    For Decimal: fills remaining digits with 0s.
    For Date/DateTime: fills to start of the precision period.
    For Time: fills to start of the precision period.
    """
    if value is None or precision is None:
        return None
    precision = int(precision)

    from decimal import Decimal as _Decimal
    if isinstance(value, (int, float, _Decimal)):
        d_str = str(value)
        if '.' in d_str:
            current_dec_places = len(d_str.split('.')[1])
        else:
            current_dec_places = 0
        digits_to_fill = precision - current_dec_places
        if digits_to_fill <= 0:
            return float(value)
        if '.' not in d_str:
            d_str += '.'
        d_str += '0' * digits_to_fill
        return float(d_str)

    if isinstance(value, str):
        return _low_boundary_temporal(value, precision)

    from datetime import date, datetime
    if isinstance(value, datetime):
        return _low_boundary_temporal(value.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3], precision)
    if isinstance(value, date):
        return _low_boundary_temporal(value.strftime("%Y-%m-%d"), precision)

    return None


def _low_boundary_temporal(value_str: str, precision: int) -> str | None:
    """Fill a temporal value to its low boundary at the given precision.

    CQL precision → component mapping:
    4=year, 6=month, 8=day, 10=hour, 12=minute, 14=second, 17=millisecond
    Time: 2=hour, 4=minute, 6=second, 9=millisecond
    """
    s = value_str.strip().replace(' ', 'T')
    is_time = ':' in s and '-' not in s
    if is_time:
        s = s.lstrip('T')
        parts = s.split(':')
        h = parts[0] if len(parts) > 0 else '00'
        m = parts[1] if len(parts) > 1 else '00'
        sec_parts = parts[2].split('.') if len(parts) > 2 else ['00', '000']
        sec = sec_parts[0] if len(sec_parts) > 0 else '00'
        ms = sec_parts[1] if len(sec_parts) > 1 else '000'

        if precision <= 2:
            return f"T{h}:00:00.000"
        elif precision <= 4:
            return f"T{h}:{m}:00.000"
        elif precision <= 6:
            return f"T{h}:{m}:{sec}.000"
        return f"T{h}:{m}:{sec}.{ms}"

    # DateTime/Date: fill missing components to their low values, truncated
    # to the requested precision level.
    year = s[:4]
    month = s[5:7] if len(s) > 5 else '01'
    day = s[8:10] if len(s) > 8 else '01'
    hour = s[11:13] if len(s) > 11 else '00'
    minute = s[14:16] if len(s) > 14 else '00'
    second = s[17:19] if len(s) > 17 else '00'
    ms = s[20:23] if len(s) > 20 else '000'

    if precision <= 4:
        return year
    elif precision <= 6:
        return f"{year}-{month}"
    elif precision <= 8:
        return f"{year}-{month}-{day}"
    elif precision <= 10:
        return f"{year}-{month}-{day}T{hour}"
    elif precision <= 12:
        return f"{year}-{month}-{day}T{hour}:{minute}"
    elif precision <= 14:
        return f"{year}-{month}-{day}T{hour}:{minute}:{second}"
    else:
        return f"{year}-{month}-{day}T{hour}:{minute}:{second}.{ms}"


def cqlPrecision(value) -> int | None:
    """CQL §22.24: Return the number of digits of precision in a value.

    - Decimal: number of digits after the decimal point
    - Date/DateTime/Time: count of digit characters (excluding separators)
    """
    if value is None:
        return None
    s = str(value)

    # Date/DateTime: count digit chars only (strip separators: - T : .)
    if 'T' in s or (len(s) >= 4 and s[:4].isdigit() and (len(s) == 4 or s[4:5] == '-')):
        # Strip timezone info for precision counting
        for tz in ('+', 'Z'):
            idx = s.find(tz, 10)
            if idx > 0:
                s = s[:idx]
        return sum(1 for c in s if c.isdigit())

    # Time-only: HH:MM:SS.mmm
    if s.startswith('T') or (len(s) >= 2 and ':' in s and '-' not in s):
        s = s.lstrip('T')
        return sum(1 for c in s if c.isdigit())

    # Decimal/Integer: count digits after decimal point
    try:
        from decimal import Decimal as D
        d = D(s)
        _, digits, exp = d.as_tuple()
        if exp >= 0:
            return 0
        return -exp  # number of decimal places
    except Exception:
        return len(s)


def cqlMessage(source, condition, code, severity, message) -> str:
    """CQL Message (§22.15) — raise runtime error when severity is 'Error'."""
    if severity == 'Error':
        raise ValueError(f"{code}: {message}")
    return source


def registerMathUdfs(con: "duckdb.DuckDBPyConnection") -> None:
    """Register all math UDFs."""
    con.create_function("mathAbs", mathAbs, null_handling="special")
    con.create_function("mathRound", mathRound, null_handling="special")
    con.create_function("mathFloor", mathFloor, null_handling="special")
    con.create_function("mathCeiling", mathCeiling, null_handling="special")
    con.create_function("mathSqrt", mathSqrt, null_handling="special")
    con.create_function("mathExp", mathExp, null_handling="special")
    con.create_function("mathLn", mathLn, null_handling="special")
    con.create_function("mathLog", mathLog, null_handling="special")
    con.create_function("mathPower", mathPower, null_handling="special")
    con.create_function("mathTruncate", mathTruncate, null_handling="special")
    con.create_function("predecessorOf", predecessorOf, null_handling="special")
    con.create_function("successorOf", successorOf, null_handling="special")
    con.create_function("HighBoundary", highBoundary, null_handling="special")
    con.create_function("LowBoundary", lowBoundary, null_handling="special")
    con.create_function("CQLPrecision", cqlPrecision, null_handling="special")
    con.create_function("CQLMessage", cqlMessage, null_handling="special")


__all__ = [
    "mathAbs", "mathRound", "mathFloor", "mathCeiling",
    "mathSqrt", "mathExp", "mathLn", "mathLog",
    "mathPower", "mathTruncate", "registerMathUdfs",
]
