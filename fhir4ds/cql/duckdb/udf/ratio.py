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

from typing import TYPE_CHECKING

import orjson

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


def ratioNumeratorValue(ratio: str | None) -> float | None:
    """Get numerator value from ratio."""
    r = _parse_ratio(ratio)
    if not r:
        return None
    num = r.get("numerator", {})
    return num.get("value")


def ratioDenominatorValue(ratio: str | None) -> float | None:
    """Get denominator value from ratio."""
    r = _parse_ratio(ratio)
    if not r:
        return None
    denom = r.get("denominator", {})
    return denom.get("value")


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
    return num.get("unit") or num.get("code")


def ratioDenominatorUnit(ratio: str | None) -> str | None:
    """Get denominator unit from ratio."""
    r = _parse_ratio(ratio)
    if not r:
        return None
    denom = r.get("denominator", {})
    return denom.get("unit") or denom.get("code")


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


__all__ = [
    "registerRatioUdfs",
    "ratioNumeratorValue",
    "ratioDenominatorValue",
    "ratioValue",
    "ratioNumeratorUnit",
    "ratioDenominatorUnit",
]
