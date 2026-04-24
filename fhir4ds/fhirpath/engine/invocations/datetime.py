from decimal import Decimal, ROUND_HALF_UP, ROUND_DOWN, ROUND_FLOOR, ROUND_CEILING, getcontext, localcontext
from ...engine.nodes import FP_DateTime, FP_Time, FP_Date, FP_Quantity
from ...engine.util import get_data

# FHIRPath precision constants
FHIRPATH_MAX_PRECISION = 28
DEFAULT_OUTPUT_PRECISION = 8
CONTEXT_PRECISION_MIN = 40


def _count_decimal_places(value):
    """Count the number of decimal places in a Decimal value."""
    # Convert to string to count decimal places as written
    s = str(value)
    if '.' in s:
        return len(s.split('.')[1])
    return 0


def _decimal_low_boundary(value, precision_param):
    """
    Calculate the low boundary of a decimal value.

    The boundary is based on the precision of the INPUT value, where we subtract
    half a unit at that precision. The precision parameter only affects the output format.

    lowBoundary = value - 0.5 * 10^(-decimal_places_of_input)
    """
    if precision_param is not None:
        if precision_param < 0:
            return []  # Empty for negative precision
        if precision_param > FHIRPATH_MAX_PRECISION:
            return []  # Empty for precision > 28 (FHIRPath max)
        output_precision = precision_param
    else:
        output_precision = DEFAULT_OUTPUT_PRECISION

    # Use a context with sufficient precision for the calculation
    with localcontext() as ctx:
        ctx.prec = max(CONTEXT_PRECISION_MIN, output_precision + 10)

        # The half-unit is ALWAYS based on the input's decimal places
        decimal_places = _count_decimal_places(value)

        # Calculate half-unit at the input's precision
        half_unit = Decimal("0.5") * (Decimal("10") ** (-decimal_places))

        # For both positive and negative, lowBoundary goes down
        result = value - half_unit

        # Special case: check if the result rounds to zero
        # When truncating to output_precision, if the result is in (-0.5*10^-output_precision, 0.5*10^-output_precision)
        # and the original value was negative, we need to return -0.0 instead of 0.0
        output_half_unit = Decimal("0.5") * (Decimal("10") ** (-output_precision if output_precision > 0 else 0))

        if result < 0 and abs(result) <= output_half_unit:
            # Result will round to zero, preserve negative sign
            if output_precision > 0:
                quantize_str = "0." + "0" * output_precision
                result = Decimal("-0." + "0" * output_precision)
            else:
                result = Decimal("0")
        else:
            # Normal FLOOR rounding
            if output_precision > 0:
                quantize_str = "0." + "0" * output_precision
                result = result.quantize(Decimal(quantize_str), rounding=ROUND_FLOOR)
            else:
                result = result.quantize(Decimal("1"), rounding=ROUND_FLOOR)

    return result


def _decimal_high_boundary(value, precision_param):
    """
    Calculate the high boundary of a decimal value.

    The boundary is based on the precision of the INPUT value, where we add
    half a unit at that precision. The precision parameter only affects the output format.

    highBoundary = value + 0.5 * 10^(-decimal_places_of_input)
    """
    if precision_param is not None:
        if precision_param < 0:
            return []  # Empty for negative precision
        if precision_param > FHIRPATH_MAX_PRECISION:
            return []  # Empty for precision > 28 (FHIRPath max)
        output_precision = precision_param
    else:
        output_precision = DEFAULT_OUTPUT_PRECISION

    # Use a context with sufficient precision for the calculation
    with localcontext() as ctx:
        ctx.prec = max(CONTEXT_PRECISION_MIN, output_precision + 10)

        # The half-unit is ALWAYS based on the input's decimal places
        decimal_places = _count_decimal_places(value)

        # Calculate half-unit at the input's precision
        half_unit = Decimal("0.5") * (Decimal("10") ** (-decimal_places))

        # For both positive and negative, highBoundary goes up
        result = value + half_unit

        # Special case: check if the result rounds to zero
        # For positive values approaching zero, highBoundary should be 0.0
        output_half_unit = Decimal("0.5") * (Decimal("10") ** (-output_precision if output_precision > 0 else 0))

        if result > 0 and result <= output_half_unit:
            # Result will round to zero from positive side
            if output_precision > 0:
                result = Decimal("0." + "0" * output_precision)
            else:
                result = Decimal("0")
        elif result < 0 and abs(result) <= output_half_unit:
            # Negative value approaching zero from below
            if output_precision > 0:
                result = Decimal("0." + "0" * output_precision)
            else:
                result = Decimal("0")
        else:
            # Normal CEILING rounding
            if output_precision > 0:
                quantize_str = "0." + "0" * output_precision
                result = result.quantize(Decimal(quantize_str), rounding=ROUND_CEILING)
            else:
                result = result.quantize(Decimal("1"), rounding=ROUND_CEILING)

    return result


def _get_last_day_of_month(year_str, month_str):
    """Return last day of the given month, defaulting to 31 on error."""
    try:
        import calendar
        return calendar.monthrange(int(year_str), int(month_str))[1]
    except (ValueError, OverflowError):
        return 31


# Fill-value configs for low/high boundary
_LOW_FILL = {
    "month": "01", "day": "01", "hour": "00", "minute": "00",
    "second": "00", "ms": "000", "tz_default": "+14:00",
    "date_month": "01", "date_day": "01",
    "decimal_fn": _decimal_low_boundary,
}
_HIGH_FILL = {
    "month": "12", "day": "31", "hour": "23", "minute": "59",
    "second": "59", "ms": "999", "tz_default": "-12:00",
    "date_month": "12", "date_day": "31",
    "decimal_fn": _decimal_high_boundary,
}


def _time_boundary(data, precision, fill):
    """Shared Time boundary logic."""
    match_list = data._getMatchAsList()
    hour = match_list[0] if match_list[0] is not None else fill["hour"]
    minute = match_list[1] if match_list[1] is not None else fill["minute"]
    second = fill["second"]
    ms = fill["ms"]
    tz = match_list[4] if len(match_list) > 4 and match_list[4] else ""

    # Preserve the 'T' prefix only when the input had it (FHIRPath literals
    # use @T14:30 format; FHIR resource values use 14:30 without 'T').
    prefix = "T" if data.asStr.startswith("T") else ""

    if precision is not None:
        if precision <= 2:
            result = f"{prefix}{hour}"
        elif precision <= 4:
            result = f"{prefix}{hour}:{minute}"
        elif precision <= 6:
            result = f"{prefix}{hour}:{minute}:{second}"
        else:
            result = f"{prefix}{hour}:{minute}:{second}.{ms}"
            if tz:
                result += tz
        return ["@" + result]

    result = f"{prefix}{hour}:{minute}:{second}.{ms}"
    if tz:
        result += tz
    return [result]


def _date_boundary(data, precision, fill, is_high):
    """Shared Date boundary logic."""
    match_list = data._getMatchAsList()
    year = match_list[0] if match_list[0] is not None else "1970"
    month = match_list[1] if match_list[1] is not None else fill["date_month"]
    day = match_list[2] if match_list[2] is not None else fill["date_day"]

    if precision is not None:
        if precision <= 4:
            return [f"@{year}"]
        elif precision <= 6:
            return [f"@{year}-{month}"]
        else:
            return [f"@{year}-{month}-{day}"]

    dp = data._precision
    if dp == 1:
        if is_high:
            return [FP_Date(f"{year}-12-31")]
        return [FP_Date(f"{year}-01-01")]
    elif dp == 2:
        if is_high:
            last_day = _get_last_day_of_month(year, month)
            return [FP_Date(f"{year}-{month}-{last_day:02d}")]
        return [FP_Date(f"{year}-{month}-01")]
    else:
        return [FP_Date(f"{year}-{month}-{day}")]


def _datetime_boundary(data, precision, fill, is_high):
    """Shared DateTime boundary logic."""
    match_list = data._getMatchAsList()
    year = match_list[0] if match_list[0] is not None else "1970"
    month = match_list[1] if match_list[1] is not None else fill["date_month"]
    day = match_list[2] if match_list[2] is not None else fill["date_day"]
    hour = match_list[3] if match_list[3] is not None else fill["hour"]
    minute = match_list[4] if match_list[4] is not None else fill["minute"]
    second = fill["second"]
    ms = fill["ms"]
    tz = match_list[7] if len(match_list) > 7 and match_list[7] else ""

    if precision is not None:
        h_p = match_list[3] if match_list[3] is not None else "00"
        m_p = match_list[4] if match_list[4] is not None else "00"
        if precision <= 4:
            return [f"@{year}"]
        elif precision <= 6:
            return [f"@{year}-{month}"]
        elif precision <= 8:
            return [f"@{year}-{month}-{day}"]
        elif precision <= 10:
            return [f"@{year}-{month}-{day}T{h_p}"]
        elif precision <= 12:
            return [f"@{year}-{month}-{day}T{h_p}:{m_p}"]
        elif precision <= 14:
            return [f"@{year}-{month}-{day}T{h_p}:{m_p}:{second}"]
        else:
            result = f"{year}-{month}-{day}T{h_p}:{m_p}:{second}.{ms}"
            result += tz if tz else fill["tz_default"]
            return [f"@{result}"]

    dp = data._precision
    if dp == 1:
        if is_high:
            return [FP_Date(f"{year}-12-31")]
        return [FP_Date(f"{year}-01-01")]
    elif dp == 2:
        if is_high:
            last_day = _get_last_day_of_month(year, month)
            return [FP_Date(f"{year}-{month}-{last_day:02d}")]
        return [FP_Date(f"{year}-{month}-01")]
    elif dp == 3:
        # Date-only precision dateTime: expand to full dateTime with tz
        result = f"{year}-{month}-{day}T{fill['hour']}:{fill['minute']}:{fill['second']}.{fill['ms']}"
        result += fill.get("tz_default", "")
        return [result]
    else:
        result = f"{year}-{month}-{day}T{hour}:{minute}:{second}.{ms}"
        if tz:
            result += tz
        return [FP_DateTime(result)]


def _boundary(ctx, coll, precision, fill, is_high):
    """Shared entry point for lowBoundary/highBoundary."""
    if not coll or len(coll) == 0:
        return []

    value = coll[0]
    data = get_data(value)

    if isinstance(data, (Decimal, int)):
        result = fill["decimal_fn"](Decimal(str(data)), precision)
        return [] if result == [] else [result]

    if isinstance(data, FP_Quantity):
        result = fill["decimal_fn"](Decimal(str(data.value)), precision)
        return [] if result == [] else [FP_Quantity(result, data.unit)]

    # Coerce plain strings (from FHIR resources) to FP date/time types.
    # Use ResourceNode type info when available to distinguish date vs dateTime.
    if isinstance(data, str):
        import re
        from ...engine.nodes import ResourceNode, TypeInfo
        is_datetime_typed = False
        if isinstance(value, ResourceNode):
            ti = TypeInfo.from_value(value)
            is_datetime_typed = ti.name in ('dateTime', 'DateTime', 'instant')

        if re.match(r'^\d{2}:\d{2}', data):
            data = FP_Time(data)
        elif 'T' in data and re.match(r'^\d{4}', data):
            data = FP_DateTime(data)
        elif re.match(r'^\d{4}(-\d{2}(-\d{2})?)?$', data):
            if is_datetime_typed:
                # dateTime with date-only precision — use FP_Date but dispatch
                # to datetime boundary logic below
                data = FP_Date(data)
            else:
                data = FP_Date(data)

    if isinstance(data, FP_Time):
        return _time_boundary(data, precision, fill)
    elif isinstance(data, FP_Date):
        # Check if the original value was typed as dateTime — if so, use
        # datetime boundary semantics (which include time+tz expansion)
        from ...engine.nodes import ResourceNode, TypeInfo
        is_datetime_typed = False
        if isinstance(value, ResourceNode):
            ti = TypeInfo.from_value(value)
            is_datetime_typed = ti.name in ('dateTime', 'DateTime', 'instant')
        if is_datetime_typed:
            return _datetime_boundary(data, precision, fill, is_high)
        return _date_boundary(data, precision, fill, is_high)
    elif isinstance(data, FP_DateTime):
        return _datetime_boundary(data, precision, fill, is_high)

    return []


def lowBoundary(ctx, coll, precision=None):
    """
    Returns the lowest possible value for a date/time at the given precision.

    For Decimal/Integer:
    - 1.587.lowBoundary() -> 1.58650000 (default precision 8)
    - 1.587.lowBoundary(2) -> 1.58
    - (-1.587).lowBoundary() -> -1.58750000

    For Date:
    - @2014.lowBoundary() -> @2014-01-01
    - @2014-01.lowBoundary() -> @2014-01-01

    For DateTime:
    - @2014-01-01.lowBoundary() -> @2014-01-01T00:00:00.000
    - @2014-01-01T14.lowBoundary() -> @2014-01-01T14:00:00.000

    For Time:
    - @T14.lowBoundary() -> @T14:00:00.000
    - @T14:30.lowBoundary() -> @T14:30:00.000
    """
    return _boundary(ctx, coll, precision, _LOW_FILL, is_high=False)


def highBoundary(ctx, coll, precision=None):
    """
    Returns the highest possible value for a date/time at the given precision.

    For Decimal/Integer:
    - 1.587.highBoundary() -> 1.58750000 (default precision 8)
    - 1.587.highBoundary(2) -> 1.59
    - (-1.587).highBoundary() -> -1.58650000

    For Date:
    - @2014.highBoundary() -> @2014-12-31
    - @2014-01.highBoundary() -> @2014-01-31

    For DateTime:
    - @2014-01-01.highBoundary() -> @2014-01-01T23:59:59.999
    - @2014-01-01T14.highBoundary() -> @2014-01-01T14:59:59.999

    For Time:
    - @T14.highBoundary() -> @T14:59:59.999
    - @T14:30.highBoundary() -> @T14:30:59.999
    """
    return _boundary(ctx, coll, precision, _HIGH_FILL, is_high=True)


def precision(ctx, coll):
    """
    Returns the precision of a date/time or decimal value as an integer.

    For Date/DateTime, returns the count of digits in the representation:
    - @2014.precision() -> 4
    - @2014-01-05T10:30:00.000.precision() -> 17

    For Time, returns the count of digits in the representation:
    - @T10:30.precision() -> 4
    - @T10:30:00.000.precision() -> 9

    For Decimal, returns the number of decimal places:
    - 1.58700.precision() -> 5
    """
    if not coll or len(coll) == 0:
        return []

    value = coll[0]
    data = get_data(value)

    # Handle decimal numbers - count decimal places
    if isinstance(data, Decimal):
        # Count the number of decimal places (digits after decimal point)
        return [_count_decimal_places(data)]

    if isinstance(data, FP_Time):
        # Time precision - count digits in the original string representation
        # Use asStr which contains the original input
        str_repr = data.asStr or ""
        # Remove 'T' prefix if present and count only digits
        if str_repr.startswith('T'):
            str_repr = str_repr[1:]
        # Count only digits (exclude colons, decimal points, timezone)
        digit_count = sum(1 for c in str_repr if c.isdigit())
        return [digit_count]

    elif isinstance(data, FP_Date):
        # Date precision - count digits in the original string representation
        str_repr = data.asStr or ""
        # Count only digits (exclude -)
        digit_count = sum(1 for c in str_repr if c.isdigit())
        return [digit_count]

    elif isinstance(data, FP_DateTime):
        # DateTime precision - count digits in the original string representation
        str_repr = data.asStr or ""
        # Count only digits (exclude -, T, :, ., timezone)
        digit_count = sum(1 for c in str_repr if c.isdigit())
        return [digit_count]

    return []


def now(ctx, data):
    c = ctx["_constants"]
    if not c.now:
        _now = c.systemtime.now()
        if not _now.tzinfo:
            _now = _now.astimezone()
        isoStr = _now.isoformat()
        c.now = [FP_DateTime(isoStr)]
    return c.now


def today(ctx, data):
    c = ctx["_constants"]
    if not c.today:
        _now = c.systemtime.now()
        isoStr = _now.date().isoformat()
        c.today = [FP_Date(isoStr)]
    return c.today


def timeOfDay(ctx, data):
    c = ctx["_constants"]
    if not c.timeOfDay:
        _now = c.systemtime.now()
        isoStr = _now.time().isoformat()
        c.timeOfDay = str(FP_Time(isoStr))
    return c.timeOfDay
