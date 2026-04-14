"""
FHIRPath functions as DuckDB SQL macros.

This module provides Tier 1 native SQL macros for FHIRPath functions,
offering zero Python overhead execution.

After registration, all FHIRPath functions are available directly in SQL:
    SELECT Abs(value), Length(name) FROM table
"""

from typing import TYPE_CHECKING

from .math import register_math_macros
from .string import register_string_macros
from .datetime import register_datetime_macros
from .logical import register_logical_macros
from .conversion import register_conversion_macros

if TYPE_CHECKING:
    import duckdb

__all__ = [
    "register_all_macros",
    "register_math_macros",
    "register_string_macros",
    "register_datetime_macros",
    "register_logical_macros",
    "register_conversion_macros",
]


def register_all_macros(con: "duckdb.DuckDBPyConnection") -> None:
    """
    Register all Tier 1 SQL macros with a DuckDB connection.

    This registers native DuckDB SQL macros for FHIRPath functions,
    providing zero Python overhead execution.

    Registered categories:
    - Math: Abs, Ceiling, Floor, Round, Sqrt, Exp, Ln, Log, Power, Truncate
    - String: Length, Upper, Lower, Concat, Substring, IndexOf, StartsWith, EndsWith, etc.
    - DateTime: Year, Month, Day, Hour, Minute, Second, Now, Today, TimeOfDay
    - Logical: And, Or, Not, Xor, Implies, Coalesce
    - Conversion: ToString, ToInteger, ToDecimal, ToBoolean, ToDate, ToDateTime

    Args:
        con: A DuckDB connection object.
    """
    register_math_macros(con)
    register_string_macros(con)
    register_datetime_macros(con)
    register_logical_macros(con)
    register_conversion_macros(con)
