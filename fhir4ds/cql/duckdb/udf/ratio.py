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

from .quantity import is_valid_quantity_object, quantityCompare, toQuantity

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


def _parse_valid_ratio(value: str | None) -> dict | None:
    ratio = _parse_ratio(value) if value is not None else None
    if not isinstance(ratio, dict):
        return None
    numerator = ratio.get("numerator")
    denominator = ratio.get("denominator")
    if not is_valid_quantity_object(numerator) or not is_valid_quantity_object(denominator):
        return None
    return ratio


def _quantity_json(value: dict) -> str:
    return orjson.dumps(value).decode("utf-8")


def _cql_and(left: bool | None, right: bool | None) -> bool | None:
    if left is False or right is False:
        return False
    if left is None or right is None:
        return None
    return True


def _decimal_value(value) -> float | None:
    if isinstance(value, (bool, str)):
        return None
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
    if not is_valid_quantity_object(num):
        return None
    return _decimal_value(num.get("value"))


def ratioDenominatorValue(ratio: str | None) -> float | None:
    """Get denominator value from ratio."""
    r = _parse_ratio(ratio)
    if not r:
        return None
    denom = r.get("denominator", {})
    if not is_valid_quantity_object(denom):
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
    if not is_valid_quantity_object(num):
        return None
    return num.get("unit") or num.get("code")


def ratioDenominatorUnit(ratio: str | None) -> str | None:
    """Get denominator unit from ratio."""
    r = _parse_ratio(ratio)
    if not r:
        return None
    denom = r.get("denominator", {})
    if not is_valid_quantity_object(denom):
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


def ratioCompare(left: str | None, right: str | None, op: str | None) -> bool | None:
    """Compare CQL Ratio values for equality or equivalence.

    Equality is component-wise Quantity equality. Equivalence compares the
    represented ratio value, matching CQL Appendix B Ratio comparison semantics.
    """
    if op not in {"==", "!=", "~", "!~"}:
        return None

    if op in {"~", "!~"}:
        if left is None and right is None:
            equivalent = True
        elif left is None or right is None:
            equivalent = False
        elif _parse_valid_ratio(left) is None or _parse_valid_ratio(right) is None:
            equivalent = False
        else:
            equivalent_result = quantityCompare(toQuantity(left), toQuantity(right), "~")
            equivalent = bool(equivalent_result) if equivalent_result is not None else False
        return not equivalent if op == "!~" else equivalent

    if left is None or right is None:
        return None
    left_ratio = _parse_valid_ratio(left)
    right_ratio = _parse_valid_ratio(right)
    if left_ratio is None or right_ratio is None:
        return None

    numerator_equal = quantityCompare(
        _quantity_json(left_ratio["numerator"]),
        _quantity_json(right_ratio["numerator"]),
        "==",
    )
    denominator_equal = quantityCompare(
        _quantity_json(left_ratio["denominator"]),
        _quantity_json(right_ratio["denominator"]),
        "==",
    )
    equal = _cql_and(numerator_equal, denominator_equal)
    if op == "!=":
        return None if equal is None else not equal
    return equal


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
    con.create_function(
        "ratioCompare",
        ratioCompare,
        return_type="BOOLEAN",
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
    "ratioCompare",
]
