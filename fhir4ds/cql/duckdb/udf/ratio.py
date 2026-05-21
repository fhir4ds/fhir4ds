"""
CQL Ratio UDFs

Implements operations on FHIR Ratio type:
- ratioNumeratorValue(ratio) -> float
- ratioDenominatorValue(ratio) -> float
- ratioValue(ratio) -> decimal (numerator.value / denominator.value)
- ratioNumeratorUnit(ratio) -> str
- ratioDenominatorUnit(ratio) -> str

Ratio format: FHIR Ratio JSON {"numerator": {"value": 5, "unit": "mg"}, "denominator": {"value": 1, "unit": "mL"}}
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
import math
from typing import TYPE_CHECKING

import orjson

from .quantity import is_valid_quantity_object

if TYPE_CHECKING:
    import duckdb




import logging

_logger = logging.getLogger(__name__)


def _parse_ratio(value: str) -> dict | None:
    """Parse FHIR Ratio JSON."""
    if not value:
        return None
    try:
        return orjson.loads(value)
    except orjson.JSONDecodeError as e:
        _logger.warning("_parse_ratio failed: %s", e)
        return None


def _decimal_value(value) -> float | None:
    try:
        decimal_value = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    if not decimal_value.is_finite():
        return None
    float_value = float(decimal_value)
    return float_value if math.isfinite(float_value) else None


def ratioNumeratorValue(ratio: str | None) -> float | None:
    """Get numerator value from ratio."""
    r = _parse_ratio(ratio)
    if not r:
        return None
    num = r.get("numerator", {})
    if not isinstance(num, dict):
        return None
    return _decimal_value(num.get("value"))


def ratioDenominatorValue(ratio: str | None) -> float | None:
    """Get denominator value from ratio."""
    r = _parse_ratio(ratio)
    if not r:
        return None
    denom = r.get("denominator", {})
    if not isinstance(denom, dict):
        return None
    return _decimal_value(denom.get("value"))


def ratioValue(ratio: str | None) -> float | None:
    """Calculate ratio value (numerator / denominator)."""
    num = ratioNumeratorValue(ratio)
    denom = ratioDenominatorValue(ratio)

    if num is None or denom is None or denom == 0:
        return None

    return num / denom


def ratioNumeratorUnit(ratio: str | None) -> str | None:
    """Get numerator unit from ratio."""
    r = _parse_ratio(ratio)
    if not r:
        return None
    num = r.get("numerator", {})
    if not isinstance(num, dict):
        return None
    return num.get("unit") or num.get("code")


def ratioDenominatorUnit(ratio: str | None) -> str | None:
    """Get denominator unit from ratio."""
    r = _parse_ratio(ratio)
    if not r:
        return None
    denom = r.get("denominator", {})
    if not isinstance(denom, dict):
        return None
    return denom.get("unit") or denom.get("code")


def _format_quantity_text(quantity) -> str | None:
    if not is_valid_quantity_object(quantity):
        return None
    value = _decimal_value(quantity.get("value"))
    if value is None:
        return None
    unit = quantity.get("unit") or quantity.get("code") or "1"
    return f"{value} '{unit}'"


def RatioToString(ratio: str | None) -> str | None:
    """Format a CQL Ratio as ``<quantity>:<quantity>`` text."""
    r = _parse_ratio(ratio)
    if not isinstance(r, dict):
        return None
    numerator = _format_quantity_text(r.get("numerator"))
    denominator = _format_quantity_text(r.get("denominator"))
    if numerator is None or denominator is None:
        return None
    return f"{numerator}:{denominator}"


# ========================================
# Registration
# ========================================

def registerRatioUdfs(con: "duckdb.DuckDBPyConnection") -> None:
    """Register all ratio UDFs."""
    con.create_function(
        "ratioNumeratorValue",
        ratioNumeratorValue,
        null_handling="special"
    )
    con.create_function(
        "ratioDenominatorValue",
        ratioDenominatorValue,
        null_handling="special"
    )
    con.create_function(
        "ratioValue",
        ratioValue,
        null_handling="special"
    )
    con.create_function(
        "ratioNumeratorUnit",
        ratioNumeratorUnit,
        null_handling="special"
    )
    con.create_function(
        "ratioDenominatorUnit",
        ratioDenominatorUnit,
        null_handling="special"
    )
    con.create_function(
        "RatioToString",
        RatioToString,
        return_type="VARCHAR",
        null_handling="special"
    )


__all__ = [
    "registerRatioUdfs",
    "ratioNumeratorValue",
    "ratioDenominatorValue",
    "ratioValue",
    "ratioNumeratorUnit",
    "ratioDenominatorUnit",
    "RatioToString",
]
