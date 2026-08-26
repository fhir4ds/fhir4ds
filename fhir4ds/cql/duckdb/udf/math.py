"""
CQL Math Function UDFs

DEPRECATED: These UDFs are superseded by Tier 1 SQL macros in macros/math.py
which provide zero Python overhead. These are retained for backward compatibility
with code that references the mathAbs/mathRound/etc. function names directly.
New code should use the SQL macro versions (Abs, Round, Floor, etc.) instead.
"""
from __future__ import annotations
from typing import TYPE_CHECKING
from decimal import Decimal
import math
import re

if TYPE_CHECKING:
    import duckdb



import logging

_logger = logging.getLogger(__name__)


_NUMBER_RE = re.compile(r"^[+-]?(?:(?:\d+(?:\.\d*)?)|(?:\.\d+))(?:[eE][+-]?\d+)?$")
_QUANTITY_VALUE_NUMBER_RE = re.compile(
    r'"value"\s*:\s*([+-]?(?:(?:\d+(?:\.\d*)?)|(?:\.\d+))(?:[eE][+-]?\d+)?)'
)
_TIME_ZONE_SUFFIX_RE = re.compile(r"(Z|[+-]\d{2}:\d{2})$")
_MAX_DECIMAL_BOUNDARY_EXPONENT = 1000
_CQL_LONG_MIN = -9223372036854775808
_CQL_LONG_MAX = 9223372036854775807
_CQL_INTEGER_MIN = -2147483648
_CQL_INTEGER_MAX = 2147483647
_CQL_DECIMAL_MIN = Decimal("-99999999999999999999.99999999")
_CQL_DECIMAL_MAX = Decimal("99999999999999999999.99999999")


def _parse_math_number(value) -> float | None:
    if value is None:
        return None
    text = str(value)
    if not _NUMBER_RE.fullmatch(text):
        return None
    result = float(text)
    if math.isinf(result) or math.isnan(result):
        return None
    return result


def _format_math_result(value: float) -> str | None:
    if math.isinf(value) or math.isnan(value):
        return None
    if value == math.floor(value) and abs(value) < 1e15:
        return str(int(value))
    return f"{value:.15g}"


def _split_time_suffix(value_str: str) -> tuple[str, str]:
    text = value_str.strip()
    if text.startswith(("T", "t")):
        text = text[1:]
    match = _TIME_ZONE_SUFFIX_RE.search(text)
    if match:
        return text[:match.start()], match.group(1)
    return text, ""


def _split_datetime_suffix(value_str: str) -> tuple[str, str]:
    text = value_str.strip()
    time_pos = max(text.find("T"), text.find(" "))
    if time_pos < 0:
        return text, ""
    match = _TIME_ZONE_SUFFIX_RE.search(text)
    if match and match.start() > time_pos:
        return text[: match.start()], match.group(1)
    return text, ""


def _strip_datetime_timezone_for_precision(value_str: str) -> str:
    """Remove timezone suffix from DateTime text before precision counting."""
    text = value_str.strip()
    time_pos = max(text.find("T"), text.find(" "))
    if time_pos < 0:
        return text
    match = _TIME_ZONE_SUFFIX_RE.search(text)
    if match and match.start() > time_pos:
        return text[: match.start()]
    return text


def _valid_timezone_suffix(suffix: str) -> bool:
    if not suffix or suffix == "Z":
        return True
    if len(suffix) != 6 or suffix[3] != ":":
        return False
    offset = suffix[1:3] + suffix[4:6]
    if not offset.isdigit():
        return False
    hours = int(offset[:2])
    minutes = int(offset[2:])
    return minutes <= 59 and (hours < 14 or (hours == 14 and minutes == 0))


def _is_time_only_string(value_str: str) -> bool:
    text = value_str.strip()
    if text.startswith(("T", "t")):
        return True
    return len(text) >= 5 and text[0:2].isdigit() and text[2] == ":"


def _is_year_precision_date_string(value_str: str) -> bool:
    text = value_str.strip()
    return len(text) == 4 and text.isdigit()


def _decimal_boundary_text(value_str: str, precision: int, fill: str) -> str | None:
    """CQL §6.7 HighBoundary / §6.9 LowBoundary for Decimal inputs.

    Mirrors the HL7 reference implementation
    (``HighBoundaryEvaluator``/``LowBoundaryEvaluator`` in
    cqframework/clinical_quality_language): HighBoundary appends
    ``99999999`` to the input's plain string and truncates DOWN at the
    requested precision; LowBoundary is ``setScale(precision, DOWN)``.
    Consequences: ``HighBoundary(1.587, 8)`` -> ``1.58799999``,
    ``HighBoundary(1.587, 2)`` -> ``1.58`` (truncated at precision, NOT
    the unchanged input), ``LowBoundary(1.587, 2)`` -> ``1.58``.
    """
    if precision > 8:
        return None
    d_str = value_str.strip()
    if "e" in d_str.lower():
        from decimal import Decimal, InvalidOperation

        try:
            decimal_value = Decimal(d_str)
        except (InvalidOperation, ValueError):
            return None
        if not decimal_value.is_finite():
            return None
        if abs(decimal_value.adjusted()) > _MAX_DECIMAL_BOUNDARY_EXPONENT:
            return None
        d_str = format(decimal_value, "f")
    if "." in d_str:
        int_part, frac = d_str.split(".", 1)
    else:
        int_part, frac = d_str, ""
    # Pad with the fill digit (9 for high, 0 for low) then truncate the
    # fractional part to exactly `precision` digits (ROUND_DOWN / toward
    # zero, matching BigDecimal.setScale(precision, RoundingMode.DOWN)).
    new_frac = (frac + fill * 8)[:precision] if precision > 0 else ""
    if precision > 0:
        return f"{int_part}.{new_frac}"
    return int_part


def _validate_time_parts(time_part: str, suffix: str) -> bool:
    if not _valid_timezone_suffix(suffix):
        return False
    if not time_part:
        return False
    parts = time_part.split(":")
    if len(parts) > 3:
        return False
    if not parts[0].isdigit():
        return False
    hour = int(parts[0])
    if hour > 23:
        return False
    if len(parts) > 1:
        if not parts[1].isdigit():
            return False
        minute = int(parts[1])
        if minute > 59:
            return False
    if len(parts) > 2:
        sec_parts = parts[2].split(".")
        if len(sec_parts) > 2 or not sec_parts[0].isdigit():
            return False
        second = int(sec_parts[0])
        if second > 59:
            return False
        if len(sec_parts) == 2 and (
            not sec_parts[1].isdigit() or len(sec_parts[1]) > 3
        ):
            return False
    return True


def _validate_temporal_body(value_str: str, suffix: str) -> bool:
    if not _valid_timezone_suffix(suffix):
        return False
    if "T" in value_str or " " in value_str:
        sep = "T" if "T" in value_str else " "
        date_part, time_part = value_str.split(sep, 1)
    else:
        date_part, time_part = value_str, ""

    if len(date_part) < 4 or not date_part[:4].isdigit():
        return False
    year = int(date_part[:4])
    if year < 1 or year > 9999:
        return False
    month = 1
    if len(date_part) >= 7:
        if date_part[4] != "-" or not date_part[5:7].isdigit():
            return False
        month = int(date_part[5:7])
        if month < 1 or month > 12:
            return False
    if len(date_part) >= 10:
        if date_part[7] != "-" or not date_part[8:10].isdigit():
            return False
        import calendar

        day = int(date_part[8:10])
        if day < 1 or day > calendar.monthrange(year, month)[1]:
            return False
    if len(date_part) not in (4, 7, 10):
        return False
    if time_part:
        return _validate_time_parts(time_part, suffix)
    return True


def mathAbs(x: str | None) -> str | None:
    """CQL Abs(x)."""
    value = _parse_math_number(x)
    if value is None:
        return None
    return _format_math_result(abs(value))


def mathRound(x: str | None, precision: str | None = "0") -> str | None:
    """CQL Round(x, precision)."""
    value = _parse_math_number(x)
    if value is None:
        return None
    try:
        prec = int(str(precision)) if precision is not None else 0
    except ValueError:
        prec = 0
    multiplier = 10.0 ** prec
    shifted = value * multiplier
    if shifted >= 0:
        shifted = math.floor(shifted + 0.5)
    else:
        shifted = math.ceil(shifted - 0.5)
    result = shifted / multiplier
    if prec <= 0:
        return _format_math_result(result)
    return f"{result:.{prec}f}"


def mathFloor(x: str | None) -> str | None:
    """CQL Floor(x).

    CQL 1.5 Appendix B: Floor(Decimal) returns Integer; "If the result of
    the operation cannot be represented as an Integer, the result is
    null" (e.g. Floor(2147483648.2) -> null).
    """
    value = _parse_math_number(x)
    if value is None:
        return None
    result = math.floor(value)
    if result < _CQL_INTEGER_MIN or result > _CQL_INTEGER_MAX:
        return None
    return _format_math_result(result)


def mathCeiling(x: str | None) -> str | None:
    """CQL Ceiling(x).

    CQL 1.5 Appendix B: Ceiling(Decimal) returns Integer; "If the result
    of the operation cannot be represented as an Integer, the result is
    null" (e.g. Ceiling(3147483647.05) -> null).
    """
    value = _parse_math_number(x)
    if value is None:
        return None
    result = math.ceil(value)
    if result < _CQL_INTEGER_MIN or result > _CQL_INTEGER_MAX:
        return None
    return _format_math_result(result)


def mathSqrt(x: str | None) -> str | None:
    """CQL Sqrt(x)."""
    value = _parse_math_number(x)
    if value is None or value < 0:
        return None
    return _format_math_result(math.sqrt(value))


def mathExp(x: str | None) -> str | None:
    """CQL Exp(x) (§16.6).

    Per CQL v1.5.3 §16.6: "If the result of the operation cannot be
    represented, the result is null." Reinforced by the section header:
    "operations that cause arithmetic overflow or underflow ... will
    result in null, rather than a run-time error." So we return None when
    the result overflows to infinity (e.g. Exp(710), Exp(1000), Exp(1e5)),
    instead of raising a runtime error.
    """
    value = _parse_math_number(x)
    if value is None:
        return None
    try:
        result = math.exp(value)
    except OverflowError:
        # math.exp raises OverflowError only for results that overflow to
        # infinity; spec §16.6 mandates NULL on unrepresentable results.
        return None
    return _format_math_result(result)


def mathLn(x: str | None) -> str | None:
    """CQL Ln(x) - natural logarithm (§16.12).

    Per CQL v1.5.3 §16.12: "If the result of the operation cannot be
    represented, the result is null." Ln(0) is -infinity and cannot be
    represented, so return None rather than raising a runtime error.
    Negative inputs are also undefined and return None.
    """
    value = _parse_math_number(x)
    if value is None:
        return None
    if value == 0:
        # Ln(0) is -infinity; spec §16.12 mandates NULL.
        return None
    if value < 0:
        return None
    return _format_math_result(math.log(value))


def mathLog(x: str | None, base: str | None = "10") -> str | None:
    """CQL Log(x, base) (§16.11).

    Undefined for x <= 0, base <= 0, or base == 1.
    """
    value = _parse_math_number(x)
    base_value = _parse_math_number(base)
    if value is None or base_value is None or value <= 0 or base_value <= 0 or base_value == 1:
        return None
    return _format_math_result(math.log(value, base_value))


def mathPower(x: str | None, exponent: str | None) -> str | None:
    """CQL Power(x, y)."""
    value = _parse_math_number(x)
    exponent_value = _parse_math_number(exponent)
    if value is None or exponent_value is None:
        return None
    try:
        result = math.pow(value, exponent_value)
    except (OverflowError, ValueError) as e:
        _logger.warning("UDF mathPower failed: %s", e)
        return None
    if result != 0 and abs(result) < 1e-4:
        # Sub-scale magnitudes must be emitted in fixed notation at the
        # implementation scale (8): '%.15g' scientific text (e.g.
        # '9.09494701772928e-10') is rounded UP to 1E-8 by DuckDB's
        # VARCHAR->DECIMAL(38,8) cast, so Power(2, -30) returned
        # 0.00000001 instead of the correctly quantized 0.00000000.
        return f"{result:.8f}"
    return _format_math_result(result)


def mathTruncate(x: str | None) -> str | None:
    """CQL Truncate(x) - integer part."""
    value = _parse_math_number(x)
    if value is None:
        return None
    return _format_math_result(math.trunc(value))


def _step_time_string(value: str, direction: int) -> str | None:
    import re

    match = re.fullmatch(
        r"T?(?P<h>\d{2})(?::(?P<m>\d{2})(?::(?P<s>\d{2})(?:\.(?P<ms>\d{1,3}))?)?)?(?P<suffix>Z|[+-]\d{2}:\d{2})?",
        value,
    )
    if not match:
        return None
    h = int(match.group("h"))
    m = int(match.group("m") or 0)
    s = int(match.group("s") or 0)
    ms_text = match.group("ms")
    ms = int(ms_text.ljust(3, "0")) if ms_text is not None else 0
    if h > 23 or m > 59 or s > 59:
        return None

    if match.group("m") is None:
        precision = "hour"
        step = 3600000
    elif match.group("s") is None:
        precision = "minute"
        step = 60000
    elif ms_text is None:
        precision = "second"
        step = 1000
    else:
        precision = "millisecond"
        step = 1

    total_ms = ((h * 60 + m) * 60 + s) * 1000 + ms + direction * step
    if total_ms < 0 or total_ms > 86399999:
        return None

    rh, rem = divmod(total_ms, 3600000)
    rm, rem = divmod(rem, 60000)
    rs, rms = divmod(rem, 1000)
    suffix = match.group("suffix") or ""
    if precision == "hour":
        return f"T{rh:02d}{suffix}"
    if precision == "minute":
        return f"T{rh:02d}:{rm:02d}{suffix}"
    if precision == "second":
        return f"T{rh:02d}:{rm:02d}:{rs:02d}{suffix}"
    return f"T{rh:02d}:{rm:02d}:{rs:02d}.{rms:03d}{suffix}"


def _step_temporal_string(value: str, direction: int) -> str | None:
    import re
    from datetime import date, datetime, timedelta
    import calendar

    match = re.fullmatch(
        r"(?P<y>\d{4})(?:-(?P<mo>\d{2})(?:-(?P<d>\d{2}))?)?(?P<dt>[T ])?(?P<h>\d{2})?(?::(?P<mi>\d{2})(?::(?P<s>\d{2})(?:\.(?P<ms>\d{1,3}))?)?)?(?P<suffix>Z|[+-]\d{2}:\d{2})?",
        value,
    )
    if not match:
        return None

    has_datetime_marker = match.group("dt") is not None
    y = int(match.group("y"))
    mo = int(match.group("mo") or 1)
    d = int(match.group("d") or 1)
    h = int(match.group("h") or 0)
    mi = int(match.group("mi") or 0)
    s = int(match.group("s") or 0)
    ms_text = match.group("ms")
    ms = int(ms_text.ljust(3, "0")) if ms_text is not None else 0
    if not (1 <= y <= 9999 and 1 <= mo <= 12 and 1 <= d <= calendar.monthrange(y, mo)[1]):
        return None
    if h > 23 or mi > 59 or s > 59:
        return None

    if match.group("mo") is None:
        precision = "year"
    elif match.group("d") is None:
        precision = "month"
    elif not has_datetime_marker:
        precision = "day"
    elif match.group("h") is None:
        precision = "day"
    elif match.group("mi") is None:
        precision = "hour"
    elif match.group("s") is None:
        precision = "minute"
    elif ms_text is None:
        precision = "second"
    else:
        precision = "millisecond"

    def step_month(year: int, month: int) -> tuple[int, int] | None:
        month += direction
        if month < 1:
            month = 12
            year -= 1
        elif month > 12:
            month = 1
            year += 1
        if year < 1 or year > 9999:
            return None
        return year, month

    try:
        if precision == "year":
            y += direction
            if y < 1 or y > 9999:
                return None
        elif precision == "month":
            stepped = step_month(y, mo)
            if stepped is None:
                return None
            y, mo = stepped
        elif precision == "day":
            stepped_date = date(y, mo, d) + timedelta(days=direction)
            y, mo, d = stepped_date.year, stepped_date.month, stepped_date.day
        else:
            delta_args = {
                "hour": {"hours": direction},
                "minute": {"minutes": direction},
                "second": {"seconds": direction},
                "millisecond": {"milliseconds": direction},
            }[precision]
            stepped_dt = datetime(y, mo, d, h, mi, s, ms * 1000) + timedelta(**delta_args)
            y, mo, d = stepped_dt.year, stepped_dt.month, stepped_dt.day
            h, mi, s, ms = stepped_dt.hour, stepped_dt.minute, stepped_dt.second, stepped_dt.microsecond // 1000
    except (OverflowError, ValueError):
        return None

    suffix = match.group("suffix") or ""
    if not has_datetime_marker:
        if precision == "year":
            return f"{y:04d}"
        if precision == "month":
            return f"{y:04d}-{mo:02d}"
        return f"{y:04d}-{mo:02d}-{d:02d}"

    if precision == "year":
        return f"{y:04d}T"
    if precision == "month":
        return f"{y:04d}-{mo:02d}T"
    if precision == "day":
        return f"{y:04d}-{mo:02d}-{d:02d}T"
    if precision == "hour":
        return f"{y:04d}-{mo:02d}-{d:02d}T{h:02d}{suffix}"
    if precision == "minute":
        return f"{y:04d}-{mo:02d}-{d:02d}T{h:02d}:{mi:02d}{suffix}"
    if precision == "second":
        return f"{y:04d}-{mo:02d}-{d:02d}T{h:02d}:{mi:02d}:{s:02d}{suffix}"
    return f"{y:04d}-{mo:02d}-{d:02d}T{h:02d}:{mi:02d}:{s:02d}.{ms:03d}{suffix}"


def _step_quantity_json(value: str, direction: int) -> str | None:
    match = _QUANTITY_VALUE_NUMBER_RE.search(value)
    if not match:
        return None

    raw_number = match.group(1)
    from decimal import Decimal, InvalidOperation

    try:
        current = Decimal(raw_number)
    except InvalidOperation:
        return None

    from .quantity import _format_cql_quantity, _parse_quantity

    parsed = _parse_quantity(value)
    if not parsed or parsed.get("value") is None:
        return None

    unit = parsed.get("unit") or parsed.get("code") or "1"
    step = Decimal("0.00000001") if ("." in raw_number or "e" in raw_number.lower()) else Decimal(1)
    return _format_cql_quantity(current + direction * step, unit)


def _step_value(x, direction: int) -> str | float | int | None:
    """Shared implementation for predecessorOf/successorOf.

    Args:
        x: Input value (int, float, Decimal, str, date, datetime, or None).
        direction: +1 for successor, -1 for predecessor.
    """
    if x is None:
        return None
    from decimal import Decimal
    from datetime import date, datetime, timedelta
    if isinstance(x, datetime):
        return (x + timedelta(milliseconds=direction)).isoformat()
    if isinstance(x, date):
        return (x + timedelta(days=direction)).isoformat()
    if isinstance(x, str):
        x_stripped = x.strip()
        # Time string (T-prefixed or HH:MM:SS pattern)
        if x_stripped.startswith('T') or (len(x_stripped) >= 5 and x_stripped[2:3] == ':'):
            return _step_time_string(x_stripped, direction)
        # Quantity JSON
        if x_stripped.startswith('{'):
            return _step_quantity_json(x_stripped, direction)
        # Date/datetime string
        stepped_temporal = _step_temporal_string(x_stripped, direction)
        if stepped_temporal is not None:
            return stepped_temporal
        # Try numeric string
        try:
            v = Decimal(x_stripped)
            if (direction < 0 and v <= _CQL_DECIMAL_MIN) or (direction > 0 and v >= _CQL_DECIMAL_MAX):
                return None
            return float(v + direction * Decimal("0.00000001"))
        except Exception as e:
            _logger.debug("Unexpected error in UDF _step_value numeric parse: %s", e)
            return None
    if isinstance(x, Decimal) or isinstance(x, float):
        step = Decimal("0.00000001")
        decimal_value = x if isinstance(x, Decimal) else Decimal(str(x))
        if (direction < 0 and decimal_value <= _CQL_DECIMAL_MIN) or (
            direction > 0 and decimal_value >= _CQL_DECIMAL_MAX
        ):
            return None
        return x + direction * step if isinstance(x, Decimal) else float(x) + direction * 1e-8
    if isinstance(x, bool):
        return None
    if isinstance(x, int):
        if direction < 0 and x <= _CQL_LONG_MIN:
            return None
        if direction > 0 and x >= _CQL_LONG_MAX:
            return None
    return int(x) + direction


def predecessorOf(x) -> str | float | int | None:
    """CQL Predecessor (§22.25): returns the value one step less than x.

    Integer/Long: x - 1, Decimal: x - 10^-8, Date: x - 1 day,
    DateTime: x - 1 ms, Time: x - 1 ms, Quantity: value - step.
    """
    try:
        return _step_value(x, -1)
    except (OverflowError, ValueError, TypeError) as e:
        _logger.debug("UDF predecessorOf returned null for boundary/invalid input: %s", e)
        return None


def successorOf(x) -> str | float | int | None:
    """CQL Successor (§22.26): returns the value one step greater than x.

    Integer/Long: x + 1, Decimal: x + 10^-8, Date: x + 1 day,
    DateTime: x + 1 ms, Time: x + 1 ms, Quantity: value + step.
    """
    try:
        return _step_value(x, +1)
    except (OverflowError, ValueError, TypeError) as e:
        _logger.debug("UDF successorOf returned null for boundary/invalid input: %s", e)
        return None


def highBoundary(value, precision: int | None = None) -> str | float | None:
    """CQL HighBoundary(value, precision) — §22.10.

    Returns the highest value within the given precision of the input.
    For Decimal: fills remaining digits with 9s.
    For Date/DateTime: fills to end of the precision period.
    For Time: fills to end of the precision period.
    """
    if value is None:
        return None
    if precision is None:
        precision = _default_boundary_precision(value)
        if precision is None:
            return None
    precision = int(precision)

    # Handle Decimal (DuckDB passes DECIMAL type as Python Decimal object)
    from decimal import Decimal as _Decimal
    if isinstance(value, (int, float, _Decimal)):
        if precision > 8:
            return None
        bounded = _decimal_boundary_text(str(value), precision, "9")
        # Return the exact text (like the native extension's string result),
        # never float(): a DOUBLE round-trip corrupts >15-significant-digit
        # Decimals (CQL-10 HISTORIAN QA-001) and loses the fixture-mandated
        # scale-8 rendering. Callers transport via VARCHAR/DECIMAL(38,8).
        return bounded

    if isinstance(value, str):
        stripped = value.strip()
        if _NUMBER_RE.fullmatch(stripped) and not _is_year_precision_date_string(stripped):
            return _decimal_boundary_text(stripped, precision, "9")
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
    # Detect time-only. Time values may include Z or +/-HH:MM suffixes.
    is_time = _is_time_only_string(s)
    if is_time:
        if precision > 9:
            return None
        time_part, suffix = _split_time_suffix(s)
        if not _validate_time_parts(time_part, suffix):
            return None
        parts = time_part.split(':')
        h = parts[0] if len(parts) > 0 else '00'
        m = parts[1] if len(parts) > 1 else '59'
        sec_parts = parts[2].split('.') if len(parts) > 2 else ['59', '999']
        sec = sec_parts[0] if len(sec_parts) > 0 else '59'
        ms = sec_parts[1] if len(sec_parts) > 1 else '999'

        if precision <= 2:  # hour only
            return f"T{h}:59:59.999{suffix}"
        elif precision <= 4:  # hour:minute
            return f"T{h}:{m}:59.999{suffix}"
        elif precision <= 6:  # second
            return f"T{h}:{m}:{sec}.999{suffix}"
        return f"T{h}:{m}:{sec}.{ms}{suffix}"

    # DateTime/Date precision levels (digit count):
    # 4=Y, 6=YM, 8=YMD, 10=YMDH, 12=YMDHm, 14=YMDHms, 17=YMDHmsf
    # Fill missing components to their high values, but STOP at the
    # requested precision level (CQL §22.10).
    is_datetime = 'T' in s
    suffix = ""
    if is_datetime:
        s, suffix = _split_datetime_suffix(s)
    if not _validate_temporal_body(s, suffix):
        return None
    if (is_datetime and precision > 17) or (not is_datetime and precision > 8):
        return None
    year = s[:4]
    month = s[5:7] if len(s) > 5 else '12'
    import calendar
    try:
        day_max = calendar.monthrange(int(year), int(month))[1]
    except (ValueError, TypeError):
        return None
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
        return f"{year}-{month}-{day}T{hour}{suffix}"
    elif precision <= 12:
        return f"{year}-{month}-{day}T{hour}:{minute}{suffix}"
    elif precision <= 14:
        return f"{year}-{month}-{day}T{hour}:{minute}:{second}{suffix}"
    else:
        return f"{year}-{month}-{day}T{hour}:{minute}:{second}.{ms}{suffix}"


def lowBoundary(value, precision: int | None = None) -> str | float | None:
    """CQL LowBoundary(value, precision) — §22.14.

    Returns the lowest value within the given precision of the input.
    For Decimal: fills remaining digits with 0s.
    For Date/DateTime: fills to start of the precision period.
    For Time: fills to start of the precision period.
    """
    if value is None:
        return None
    if precision is None:
        precision = _default_boundary_precision(value)
        if precision is None:
            return None
    precision = int(precision)

    from decimal import Decimal as _Decimal
    if isinstance(value, (int, float, _Decimal)):
        if precision > 8:
            return None
        bounded = _decimal_boundary_text(str(value), precision, "0")
        # Exact text, matching the native extension string result — see
        # highBoundary() for the QA-001 DOUBLE-corruption rationale.
        return bounded

    if isinstance(value, str):
        stripped = value.strip()
        if _NUMBER_RE.fullmatch(stripped) and not _is_year_precision_date_string(stripped):
            return _decimal_boundary_text(stripped, precision, "0")
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
    is_time = _is_time_only_string(s)
    if is_time:
        if precision > 9:
            return None
        time_part, suffix = _split_time_suffix(s)
        if not _validate_time_parts(time_part, suffix):
            return None
        parts = time_part.split(':')
        h = parts[0] if len(parts) > 0 else '00'
        m = parts[1] if len(parts) > 1 else '00'
        sec_parts = parts[2].split('.') if len(parts) > 2 else ['00', '000']
        sec = sec_parts[0] if len(sec_parts) > 0 else '00'
        ms = sec_parts[1] if len(sec_parts) > 1 else '000'

        if precision <= 2:
            return f"T{h}:00:00.000{suffix}"
        elif precision <= 4:
            return f"T{h}:{m}:00.000{suffix}"
        elif precision <= 6:
            return f"T{h}:{m}:{sec}.000{suffix}"
        return f"T{h}:{m}:{sec}.{ms}{suffix}"

    # DateTime/Date: fill missing components to their low values, truncated
    # to the requested precision level.
    is_datetime = 'T' in s
    suffix = ""
    if is_datetime:
        s, suffix = _split_datetime_suffix(s)
    if not _validate_temporal_body(s, suffix):
        return None
    if (is_datetime and precision > 17) or (not is_datetime and precision > 8):
        return None
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
        return f"{year}-{month}-{day}T{hour}{suffix}"
    elif precision <= 12:
        return f"{year}-{month}-{day}T{hour}:{minute}{suffix}"
    elif precision <= 14:
        return f"{year}-{month}-{day}T{hour}:{minute}:{second}{suffix}"
    else:
        return f"{year}-{month}-{day}T{hour}:{minute}:{second}.{ms}{suffix}"


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
        # Strip timezone info for precision counting. Offset digits are not
        # date/time precision components.
        s = _strip_datetime_timezone_for_precision(s)
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
    except Exception as e:
        _logger.debug("Unexpected error in UDF cqlPrecision decimal parse: %s", e)
        return None


def _default_boundary_precision(value) -> int | None:
    """CQL default precision for HighBoundary/LowBoundary when omitted."""
    from decimal import Decimal as _Decimal
    from datetime import date, datetime

    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float, _Decimal)):
        return 8
    if isinstance(value, datetime):
        return 17
    if isinstance(value, date):
        return 8
    if isinstance(value, str):
        stripped = value.strip()
        if _NUMBER_RE.fullmatch(stripped) and not _is_year_precision_date_string(stripped):
            return 8
        if _is_time_only_string(stripped):
            return 9
        normalized = stripped.replace(" ", "T")
        if "T" in normalized:
            return 17
        if _validate_temporal_body(normalized, ""):
            return sum(1 for c in normalized if c.isdigit())
    return None


def _message_condition_is_true(condition) -> bool:
    if isinstance(condition, bool):
        return condition
    if condition is None:
        return False
    if isinstance(condition, str):
        return condition.strip().lower() == "true"
    return bool(condition)


def cqlMessage(source, condition, code, severity, message) -> str:
    """CQL Message (§22.15) — raise runtime error when condition and severity require it."""
    if _message_condition_is_true(condition) and str(severity).lower() == 'error':
        raise ValueError(f"{'' if code is None else code}: {'' if message is None else message}")
    return source


def cqlTimezoneOffset(value) -> float | None:
    """CQL §18.12: Extract timezone offset in decimal hours from a datetime string.

    Per CQL §DateTime ISO-8601 representation, ``Z`` is the UTC designator
    and is equivalent to ``+00:00``. The extractor must therefore return
    ``0.0`` for ``Z``-suffixed values, not None.
    """
    if value is None:
        return None
    import re
    s = str(value)
    # CQL §DateTime: ``Z`` is the UTC designator (equivalent to +00:00).
    if s.endswith("Z"):
        return 0.0
    m = re.search(r'([+-])(\d{2}):(\d{2})$', s)
    if not m:
        return None
    suffix = f"{m.group(1)}{m.group(2)}:{m.group(3)}"
    if not _valid_timezone_suffix(suffix):
        return None
    sign = 1 if m.group(1) == '+' else -1
    return float(sign * (int(m.group(2)) + int(m.group(3)) / 60.0))


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
    con.create_function("__fhir4ds_py_HighBoundary", highBoundary, null_handling="special")
    con.create_function("__fhir4ds_py_LowBoundary", lowBoundary, null_handling="special")
    con.execute(
        """
        CREATE OR REPLACE TEMP MACRO HighBoundary(value, prec := NULL) AS
        "__fhir4ds_py_HighBoundary"(value, prec)
        """
    )
    con.execute(
        """
        CREATE OR REPLACE TEMP MACRO LowBoundary(value, prec := NULL) AS
        "__fhir4ds_py_LowBoundary"(value, prec)
        """
    )
    con.create_function("CQLPrecision", cqlPrecision, null_handling="special")
    try:
        con.create_function("CQLMessage", cqlMessage, null_handling="special")
    except Exception as exc:
        msg = str(exc).lower()
        if "cqlmessage" not in msg or (
            "not an scalar function" not in msg
            and "already" not in msg
            and "exists" not in msg
        ):
            raise
        _logger.debug("Skipping CQLMessage UDF registration because macro already exists: %s", exc)
    con.execute(
        """
        CREATE OR REPLACE MACRO CQLMessage(source, condition, code, severity, message) AS
        CASE
            WHEN COALESCE(condition, FALSE) AND lower(CAST(severity AS VARCHAR)) = 'error'
            THEN error(COALESCE(CAST(code AS VARCHAR), '') || ': ' || COALESCE(CAST(message AS VARCHAR), ''))
            ELSE source
        END
        """
    )
    con.create_function("cqlTimezoneOffset", cqlTimezoneOffset, null_handling="special")


__all__ = [
    "mathAbs", "mathRound", "mathFloor", "mathCeiling",
    "mathSqrt", "mathExp", "mathLn", "mathLog",
    "mathPower", "mathTruncate", "registerMathUdfs",
]
