"""CQL conversion-check supplemental UDFs."""

from __future__ import annotations

import json
import re
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING

from .quantity import quantityConvert, toQuantity

if TYPE_CHECKING:
    import duckdb


_BOOL_STRINGS = {"true", "false", "t", "f", "yes", "no", "y", "n", "1", "0"}
_DATE_RE = re.compile(r"^\d{4}(-\d{2}(-\d{2})?)?$")
_DATETIME_RE = re.compile(r"^\d{4}(-\d{2}(-\d{2}(T\d{2}(:\d{2}(:\d{2}(\.\d+)?)?)?(Z|[+-]\d{2}:\d{2})?)?)?)?$")
_TIME_RE = re.compile(r"^T?\d{2}:\d{2}(:\d{2}(\.\d+)?)?$")


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


def ConvertsToBoolean(value) -> bool | None:
    text = _as_text(value)
    if text is None:
        return None
    lowered = text.lower()
    if lowered in _BOOL_STRINGS:
        return True
    dec = _finite_decimal(text)
    return dec is not None and dec in (Decimal(0), Decimal(1))


def ConvertsToInteger(value) -> bool | None:
    text = _as_text(value)
    if text is None:
        return None
    dec = _finite_decimal(text)
    return dec is not None and dec == dec.to_integral_value() and -(2**31) <= int(dec) <= 2**31 - 1


def ConvertsToLong(value) -> bool | None:
    text = _as_text(value)
    if text is None:
        return None
    dec = _finite_decimal(text)
    return dec is not None and dec == dec.to_integral_value() and -(2**63) <= int(dec) <= 2**63 - 1


def ConvertsToDecimal(value) -> bool | None:
    text = _as_text(value)
    if text is None:
        return None
    return _finite_decimal(text) is not None


def ConvertsToString(value) -> bool | None:
    return None if value is None else True


def ConvertsToDate(value) -> bool | None:
    text = _as_text(value)
    if text is None:
        return None
    return _DATE_RE.match(text) is not None or ConvertsToDateTime(text)


def ConvertsToDateTime(value) -> bool | None:
    text = _as_text(value)
    if text is None:
        return None
    return _DATETIME_RE.match(text) is not None


def ConvertsToTime(value) -> bool | None:
    text = _as_text(value)
    if text is None:
        return None
    return _TIME_RE.match(text) is not None


def ConvertsToQuantity(value) -> bool | None:
    text = _as_text(value)
    if text is None:
        return None
    if text.strip().startswith("{"):
        try:
            data = json.loads(text)
            return isinstance(data, dict) and data.get("value") is not None
        except (TypeError, ValueError):
            return False
    return toQuantity(text) is not None


def ConvertsToRatio(value) -> bool | None:
    text = _as_text(value)
    if text is None:
        return None
    try:
        data = json.loads(text)
    except (TypeError, ValueError):
        return False
    if not isinstance(data, dict):
        return False
    numerator = data.get("numerator")
    denominator = data.get("denominator")
    return isinstance(numerator, dict) and isinstance(denominator, dict)


def ConvertQuantity(value, target_unit: str | None) -> str | None:
    if value is None or target_unit is None:
        return None
    text = str(value)
    quantity_json = text if text.strip().startswith("{") else toQuantity(text)
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
    return int(Decimal(str(value)))


def ToRatio(value) -> str | None:
    text = _as_text(value)
    if text is None:
        return None
    try:
        data = json.loads(text)
    except (TypeError, ValueError):
        return None
    if not ConvertsToRatio(text):
        return None
    return json.dumps(data, separators=(",", ":"))


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
        ("ConvertsToString", ConvertsToString),
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
    "ToLong",
    "ToRatio",
]
