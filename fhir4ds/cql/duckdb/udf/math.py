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
    """CQL Exp(x)."""
    if x is None:
        return None
    return math.exp(x)


def mathLn(x: float | None) -> float | None:
    """CQL Ln(x) - natural logarithm."""
    if x is None or x <= 0:
        return None
    return math.log(x)


def mathLog(x: float | None, base: float = 10) -> float | None:
    """CQL Log(x, base)."""
    if x is None or x <= 0 or base is None or base <= 0 or base == 1:
        return None
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


__all__ = [
    "mathAbs", "mathRound", "mathFloor", "mathCeiling",
    "mathSqrt", "mathExp", "mathLn", "mathLog",
    "mathPower", "mathTruncate", "registerMathUdfs",
]
