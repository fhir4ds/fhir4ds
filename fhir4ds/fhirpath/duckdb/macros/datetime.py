"""
FHIRPath DateTime functions as DuckDB SQL macros.

Tier 1 implementation - zero Python overhead.

Note: Uses 'system.' prefix to reference built-in functions and avoid
infinite recursion when macro name matches the function name.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import duckdb


def register_datetime_macros(con: "duckdb.DuckDBPyConnection") -> None:
    """
    Register datetime function macros (Tier 1).

    Registers native DuckDB SQL macros for FHIRPath datetime functions:
    - Current time: Now, Today, TimeOfDay
    - Date part extraction: Year, Month, Day, Hour, Minute, Second

    Note: Uses system. prefix to avoid shadowing DuckDB built-ins.
    """
    # ============================================
    # Current time functions (no conflict with built-ins)
    # ============================================
    con.execute("CREATE MACRO IF NOT EXISTS Now() AS CURRENT_TIMESTAMP")
    con.execute("CREATE MACRO IF NOT EXISTS Today() AS CURRENT_DATE")
    con.execute("CREATE MACRO IF NOT EXISTS TimeOfDay() AS CURRENT_TIME")

    # ============================================
    # Date part extraction (use system. prefix to avoid recursion)
    # ============================================
    con.execute("CREATE MACRO IF NOT EXISTS Year(dt) AS system.year(dt)")
    con.execute("CREATE MACRO IF NOT EXISTS Month(dt) AS system.month(dt)")
    con.execute("CREATE MACRO IF NOT EXISTS Day(dt) AS system.day(dt)")
    con.execute("CREATE MACRO IF NOT EXISTS Hour(dt) AS system.hour(dt)")
    con.execute("CREATE MACRO IF NOT EXISTS Minute(dt) AS system.minute(dt)")
    con.execute("CREATE MACRO IF NOT EXISTS Second(dt) AS system.second(dt)")


__all__ = ["register_datetime_macros"]
