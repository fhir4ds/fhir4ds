"""
CQL functions as DuckDB SQL macros.

This module provides Tier 1 native SQL macros for CQL functions,
offering zero Python overhead execution.

After registration, all CQL functions are available directly in SQL:
    SELECT Abs(value), Length(name) FROM table
"""

from typing import TYPE_CHECKING

from .math import registerMathMacros
from .string import registerStringMacros
from .datetime import registerDateTimeMacros
from .aggregate import registerAggregateMacros
from .logical import registerLogicalMacros
from .conversion import registerConversionMacros
from .list import registerListMacros
from .audit import register_audit_macros

if TYPE_CHECKING:
    import duckdb

__all__ = [
    "register_all_macros",
    "registerMathMacros",
    "registerStringMacros",
    "registerDateTimeMacros",
    "registerAggregateMacros",
    "registerLogicalMacros",
    "registerConversionMacros",
    "registerListMacros",
    "register_audit_macros",
]


def register_all_macros(con: "duckdb.DuckDBPyConnection") -> None:
    """
    Register all Tier 1 SQL macros with a DuckDB connection.

    This registers native DuckDB SQL macros for CQL functions,
    providing zero Python overhead execution.

    Registered categories:
    - Math: Abs, Ceiling, Floor, Round, Sqrt, Exp, Ln, Log, Power, Truncate, Sign, Mod, Div
    - String: Length, Upper, Lower, Concat, Substring, IndexOf, StartsWith, EndsWith, etc.
    - DateTime: Year, Month, Day, Hour, Minute, Second, Now, Today, DateBetween, etc.
    - Aggregate: Count, Sum, Min, Max, Avg, Median, Mode, StdDev, Variance, etc.
    - Logical: And, Or, Not, Xor, Implies, Coalesce, etc.
    - Conversion: ToString, ToInteger, ToDecimal, ToBoolean, ToDate, ToDateTime, ToTime
    - List: First, Last, Skip, Take, Distinct

    Args:
        con: A DuckDB connection object.
    """
    registerMathMacros(con)
    registerStringMacros(con)
    registerDateTimeMacros(con)
    registerAggregateMacros(con)
    registerLogicalMacros(con)
    registerConversionMacros(con)
    registerListMacros(con)
    register_audit_macros(con)
