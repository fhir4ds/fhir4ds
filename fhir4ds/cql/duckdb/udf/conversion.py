"""CQL conversion-check supplemental UDFs."""

from __future__ import annotations

import json
import re
from decimal import Decimal, InvalidOperation
from datetime import date, datetime, time
from typing import TYPE_CHECKING

from .quantity import is_valid_quantity_object, quantityConvert, toQuantity, _format_cql_quantity

if TYPE_CHECKING:
    import duckdb


_BOOL_STRINGS = {"true", "false", "t", "f", "yes", "no", "y", "n", "1", "0"}
# CQL §Formatting Strings defines ``0`` and ``#`` placeholders as ASCII
# digits. The CQL lexer only accepts ASCII ``[0-9]`` for numeric literals
# and ISO-8601 (referenced by CQL for date/time) is ASCII-only. Python's
# ``\d`` regex class and ``int()`` / ``Decimal()`` constructors accept
# Unicode decimal digits (Arabic-Indic, Devanagari, full-width, etc.),
# so we MUST compile these regexes with re.ASCII to reject pathological
# Unicode-digit strings like ``'٢٠٢٤-٠١-٠١'`` that real Mideast FHIR data
# can carry.
_INTEGER_STRING_RE = re.compile(r"^[+-]?\d+$", re.ASCII)
# CQL 1.5 Appendix B §ToDecimal: accepted string format is (+|-)?#0(.0#)?
# — any number of fractional digits. The RESULT is "limited in precision
# and scale to the maximum precision and scale representable" (CQL-01
# doctrine: rounding at 8 fractional digits, matching the ToDecimal macro's
# TRY_CAST(... AS DECIMAL(38, 8))). ConvertsToDecimal must therefore accept
# any digit count the To function accepts; only the integer-digit extent
# (30 digits for DECIMAL(38, 8)) is a hard limit.
_DECIMAL_STRING_RE = re.compile(r"^[+-]?\d+(?:\.\d+)?$", re.ASCII)
_DUCKDB_DECIMAL_INTEGER_DIGITS = 30
_DUCKDB_DECIMAL_SCALE = 8
_DATE_RE = re.compile(r"^(?P<year>\d{4})(?:-(?P<month>\d{2})(?:-(?P<day>\d{2}))?)?$", re.ASCII)
_DATETIME_RE = re.compile(
    r"^(?P<year>\d{4})(?:-(?P<month>\d{2})(?:-(?P<day>\d{2})"
    r"(?:T(?P<hour>\d{2})(?::(?P<minute>\d{2})(?::(?P<second>\d{2})"
    r"(?:\.(?P<millisecond>\d{1,3}))?)?)?(?P<tz>Z|[+-]\d{2}:\d{2})?)?)?)?$",
    re.ASCII,
)
_TIME_RE = re.compile(
    r"^T?(?P<hour>\d{2})(?::(?P<minute>\d{2})(?::(?P<second>\d{2})"
    r"(?:\.(?P<millisecond>\d{1,3}))?)?)?(?P<tz>Z|[+-]\d{2}:\d{2})?$",
    re.ASCII,
)
_TZ_RE = re.compile(r"^(?P<sign>[+-])(?P<hour>\d{2}):(?P<minute>\d{2})$", re.ASCII)


def _as_text(value) -> str | None:
    if value is None:
        return None
    return str(value)


def _finite_decimal(text: str) -> Decimal | None:
    try:
        value = Decimal(text)
    except (InvalidOperation, ValueError):
        return None
    if not value.is_finite():
        return None
    return value


def _fits_duckdb_decimal(value: Decimal) -> bool:
    if not value.is_finite():
        return False
    if value.as_tuple().exponent < -_DUCKDB_DECIMAL_SCALE:
        return False
    if value.is_zero():
        return True
    integer_digits = value.copy_abs().adjusted() + 1
    return integer_digits <= _DUCKDB_DECIMAL_INTEGER_DIGITS


def _fits_duckdb_decimal_rounded(value: Decimal) -> bool:
    """Like _fits_duckdb_decimal, but excess FRACTIONAL scale is allowed
    because ToDecimal rounds to the representable scale (CQL-01 doctrine).
    Only the integer-digit extent is a hard limit."""
    if not value.is_finite():
        return False
    if value.is_zero():
        return True
    integer_digits = value.copy_abs().adjusted() + 1
    return integer_digits <= _DUCKDB_DECIMAL_INTEGER_DIGITS


def _valid_year(year: str) -> bool:
    return 1 <= int(year) <= 9999


def _valid_month(month: str | None) -> bool:
    return month is None or 1 <= int(month) <= 12


def _valid_date_parts(year: str, month: str | None, day: str | None) -> bool:
    if not _valid_year(year) or not _valid_month(month):
        return False
    if day is None:
        return True
    try:
        date(int(year), int(month), int(day))
        return True
    except (TypeError, ValueError):
        return False


def _valid_time_parts(hour: str | None, minute: str | None, second: str | None) -> bool:
    if hour is None:
        return True
    if not 0 <= int(hour) <= 23:
        return False
    if minute is not None and not 0 <= int(minute) <= 59:
        return False
    if second is not None and not 0 <= int(second) <= 59:
        return False
    return True


def _valid_timezone(tz: str | None) -> bool:
    if tz is None or tz == "Z":
        return True
    match = _TZ_RE.fullmatch(tz)
    if match is None:
        return False
    hour = int(match.group("hour"))
    minute = int(match.group("minute"))
    return 0 <= hour <= 14 and 0 <= minute <= 59 and (hour < 14 or minute == 0)


def _is_valid_cql_date(text: str) -> bool:
    match = _DATE_RE.fullmatch(text)
    if match is None:
        return False
    return _valid_date_parts(match.group("year"), match.group("month"), match.group("day"))


def _is_valid_cql_datetime(text: str) -> bool:
    match = _DATETIME_RE.fullmatch(text)
    if match is None:
        return False
    groups = match.groupdict()
    if groups["tz"] is not None and groups["hour"] is None:
        return False
    return (
        _valid_date_parts(groups["year"], groups["month"], groups["day"])
        and _valid_time_parts(groups["hour"], groups["minute"], groups["second"])
        and _valid_timezone(groups["tz"])
    )


def _is_valid_cql_time(text: str) -> bool:
    # hh:mm:ss.fff (any precision). The official cql-tests fixtures
    # (CqlTypeOperatorsTest ToTime2/3/4) accept a trailing timezone marker
    # and normalize it away — fixtures outrank spec prose — so offsets are
    # parsed and validated but not retained in the Time result.
    match = _TIME_RE.fullmatch(text)
    if match is None:
        return False
    groups = match.groupdict()
    return (
        _valid_time_parts(groups["hour"], groups["minute"], groups["second"])
        and _valid_timezone(groups["tz"])
    )


def ConvertsToBoolean(value) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return True
    if isinstance(value, (int, float, Decimal)):
        dec = _finite_decimal(str(value))
        return dec is not None and dec in (Decimal(0), Decimal(1))
    if isinstance(value, str):
        return value.lower() in _BOOL_STRINGS
    return False


def ConvertsToInteger(value) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return True
    if isinstance(value, Decimal):
        # CQL 1.5 Appendix B Table 9-E defines no Decimal->Integer conversion
        # and ToInteger has no Decimal overload (Boolean/String/Long only).
        return False
    if isinstance(value, int):
        # Long -> Integer is an explicit conversion, valid within Integer range.
        return -(2**31) <= value <= 2**31 - 1
    if isinstance(value, str):
        if _INTEGER_STRING_RE.fullmatch(value) is None:
            return False
        integer = int(value)
        return -(2**31) <= integer <= 2**31 - 1
    return False


def ConvertsToLong(value) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return True
    if isinstance(value, Decimal):
        # CQL 1.5 Appendix B Table 9-E defines no Decimal->Long conversion
        # and ToLong has no Decimal overload (Boolean/String only).
        return False
    if isinstance(value, int):
        return -(2**63) <= value <= 2**63 - 1
    if isinstance(value, str):
        if _INTEGER_STRING_RE.fullmatch(value) is None:
            return False
        integer = int(value)
        return -(2**63) <= integer <= 2**63 - 1
    return False


def ConvertsToDecimal(value) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return True
    if isinstance(value, (int, float, Decimal)):
        dec = _finite_decimal(str(value))
        return dec is not None and _fits_duckdb_decimal_rounded(dec)
    if isinstance(value, str):
        dec = _finite_decimal(value)
        return _DECIMAL_STRING_RE.fullmatch(value) is not None and dec is not None and _fits_duckdb_decimal_rounded(dec)
    return False


def ConvertsToString(value) -> bool | None:
    if value is None:
        return None
    if isinstance(value, (dict, list, tuple)):
        return False
    return True


def ConvertsToDate(value) -> bool | None:
    if value is None:
        return None
    if isinstance(value, (datetime, date)):
        return True
    if not isinstance(value, str):
        return False
    text = value
    if "T" in text:
        return _is_valid_cql_datetime(text)
    return _is_valid_cql_date(text)


def ConvertsToDateTime(value) -> bool | None:
    if value is None:
        return None
    if isinstance(value, (datetime, date)):
        return True
    if not isinstance(value, str):
        return False
    text = value
    return _is_valid_cql_datetime(text)


def ConvertsToTime(value) -> bool | None:
    if value is None:
        return None
    if isinstance(value, time):
        return True
    if not isinstance(value, str):
        return False
    text = value
    return _is_valid_cql_time(text)


def ConvertsToQuantity(value) -> bool | None:
    text = _as_text(value)
    if text is None:
        return None
    if text.strip().startswith("{"):
        try:
            data = json.loads(text)
            if is_valid_quantity_object(data):
                return True
            return toQuantity(text) is not None
        except (TypeError, ValueError):
            return False
    try:
        return toQuantity(text) is not None
    except (TypeError, ValueError):
        return False


def ConvertsToRatio(value) -> bool | None:
    text = _as_text(value)
    if text is None:
        return None
    ratio = _parse_ratio_text(text)
    if ratio is not None:
        return True
    try:
        data = json.loads(text)
    except (TypeError, ValueError):
        return False
    if not isinstance(data, dict):
        return False
    numerator = data.get("numerator")
    denominator = data.get("denominator")
    return _is_valid_quantity_object(numerator) and _is_valid_quantity_object(denominator)


def _is_valid_quantity_object(value) -> bool:
    return is_valid_quantity_object(value)


def _split_ratio_text(text: str) -> tuple[str, str] | None:
    in_quote = False
    for idx, char in enumerate(text):
        if char == "'":
            in_quote = not in_quote
        elif char == ":" and not in_quote:
            return text[:idx].strip(), text[idx + 1:].strip()
    return None


def _parse_ratio_text(text: str) -> dict | None:
    parts = _split_ratio_text(text)
    if parts is None:
        return None
    numerator_json = toQuantity(parts[0])
    denominator_json = toQuantity(parts[1])
    if numerator_json is None or denominator_json is None:
        return None
    numerator = json.loads(numerator_json)
    denominator = json.loads(denominator_json)
    if not _is_valid_quantity_object(numerator) or not _is_valid_quantity_object(denominator):
        return None
    return {"numerator": numerator, "denominator": denominator}


def ToDate(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if not isinstance(value, str):
        return None
    text = value
    if "T" in text:
        if not _is_valid_cql_datetime(text):
            return None
        return text.split("T", 1)[0]
    return text if _is_valid_cql_date(text) else None


def ToDateTime(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if not isinstance(value, str):
        return None
    text = value
    if not _is_valid_cql_datetime(text):
        return None
    return text[:-1] + "+00:00" if text.endswith("Z") else text


def ToTime(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, time):
        return value.isoformat()
    if not isinstance(value, str):
        return None
    text = value
    match = _TIME_RE.fullmatch(text)
    if match is None or not _is_valid_cql_time(text):
        return None
    # Drop any timezone marker (official fixtures: ToTime('T14:30:00.0+05:30')
    # -> @T14:30:00.000 — the CQL Time type carries no offset; the marker is
    # accepted on input and normalized away).
    groups = match.groupdict()
    if groups["tz"] is not None:
        text = text[: match.start("tz")] if match.start("tz") else text
    # CQL Time values are transported as T-prefixed strings (same convention
    # as Time literals and TimeOfDay()); stripping the marker breaks
    # component extraction and time comparisons downstream.
    return "T" + (text[1:] if text.startswith("T") else text)


def ConvertQuantity(value, target_unit: str | None) -> str | None:
    if value is None or target_unit is None:
        return None
    text = str(value)
    if text.strip().startswith("{"):
        try:
            data = json.loads(text)
        except (TypeError, ValueError):
            return None
        if not is_valid_quantity_object(data):
            return None
        quantity_json = text
    else:
        quantity_json = toQuantity(text)
    if quantity_json is None:
        return None
    return quantityConvert(quantity_json, target_unit)


def CanConvertQuantity(value, target_unit: str | None) -> bool | None:
    if value is None or target_unit is None:
        return None
    return ConvertQuantity(value, target_unit) is not None


def ToLong(value) -> int | None:
    if not ConvertsToLong(value):
        return None
    if isinstance(value, bool):
        return 1 if value else 0
    return int(value)


def ToRatio(value) -> str | None:
    text = _as_text(value)
    if text is None:
        return None
    ratio = _parse_ratio_text(text)
    if ratio is not None:
        return json.dumps(ratio, separators=(",", ":"))
    try:
        data = json.loads(text)
    except (TypeError, ValueError):
        return None
    if not ConvertsToRatio(text):
        return None
    # CQL-07 EXPLORER (2026-07-01): Normalize JSON-object Ratio input through
    # the same _format_cql_quantity canonicalization path used by
    # _parse_ratio_text for text input. Without this, JSON input is echoed
    # verbatim and lacks the `code`/`system` fields the text-input path
    # produces, breaking the ToString(ToRatio(x)) round-trip invariant for
    # JSON input.
    numerator = _normalize_quantity_object(data.get("numerator"))
    denominator = _normalize_quantity_object(data.get("denominator"))
    if numerator is None or denominator is None:
        return None
    normalized = {"numerator": numerator, "denominator": denominator}
    return json.dumps(normalized, separators=(",", ":"))


def _normalize_quantity_object(value) -> dict | None:
    """Render a Quantity-shaped dict through _format_cql_quantity so its
    serialized form matches the canonical form produced by toQuantity for
    text input (i.e., contains `value`, `unit`, `code`, and `system` keys).

    Accepts a dict or a JSON-string-encoded dict. Returns None when the input
    is not a valid CQL Quantity shape.
    """
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (TypeError, ValueError):
            return None
    if not is_valid_quantity_object(value):
        return None
    unit = value.get("unit") or value.get("code") or "1"
    quantity_value = value.get("value")
    formatted = _format_cql_quantity(quantity_value, unit)
    if formatted is None:
        return None
    try:
        return json.loads(formatted)
    except (TypeError, ValueError):
        return None


def registerConversionCheckUdfs(con: "duckdb.DuckDBPyConnection") -> None:
    for name, fn in [
        ("ConvertsToBoolean", ConvertsToBoolean),
        ("ConvertsToDate", ConvertsToDate),
        ("ConvertsToDateTime", ConvertsToDateTime),
        ("ConvertsToDecimal", ConvertsToDecimal),
        ("ConvertsToInteger", ConvertsToInteger),
        ("ConvertsToLong", ConvertsToLong),
        ("ConvertsToQuantity", ConvertsToQuantity),
        ("ConvertsToRatio", ConvertsToRatio),
        ("ConvertsToTime", ConvertsToTime),
        ("CanConvertQuantity", CanConvertQuantity),
        ("ToLong", ToLong),
        ("ToRatio", ToRatio),
    ]:
        con.create_function(name, fn, null_handling="special")
    con.create_function("ConvertQuantity", ConvertQuantity, null_handling="special")


__all__ = [
    "registerConversionCheckUdfs",
    "ConvertsToBoolean",
    "ConvertsToDate",
    "ConvertsToDateTime",
    "ConvertsToDecimal",
    "ConvertsToInteger",
    "ConvertsToLong",
    "ConvertsToQuantity",
    "ConvertsToRatio",
    "ConvertsToString",
    "ConvertsToTime",
    "CanConvertQuantity",
    "ConvertQuantity",
    "ToDate",
    "ToDateTime",
    "ToLong",
    "ToRatio",
    "ToTime",
]
