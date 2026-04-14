"""
CQL DateTime functions as DuckDB SQL macros.

Tier 1 implementation - zero Python overhead.

Note: Uses 'system.' prefix to reference built-in functions and avoid
infinite recursion when macro name matches the function name.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import duckdb


def registerDateTimeMacros(con: "duckdb.DuckDBPyConnection") -> None:
    """
    Register datetime function macros (Tier 1).

    Registers native DuckDB SQL macros for CQL datetime functions:
    - Current time: Now, Today, TimeOfDay
    - Date part extraction: Year, Month, Day, Hour, Minute, Second
    - Date constructors: Date, Time, DateTime
    - Date differences: YearsBetween, MonthsBetween, DaysBetween, etc.

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

    # ============================================
    # Date constructors (avoiding reserved keywords)
    # Note: 'Date' is a reserved type in DuckDB, use MakeDate
    # ============================================
    con.execute("CREATE MACRO IF NOT EXISTS MakeDate(yr, mo, dy) AS system.make_date(yr, mo, dy)")
    con.execute("CREATE MACRO IF NOT EXISTS MakeTime(hr, mi, sc) AS system.make_time(hr, mi, sc)")
    con.execute("CREATE MACRO IF NOT EXISTS MakeDateTime(yr, mo, dy) AS system.make_timestamp(yr, mo, dy, 0, 0, 0)")

    # ============================================
    # Date differences (using DATE_DIFF)
    # Note: Cast to DATE/TIMESTAMP to handle string inputs
    # ============================================
    con.execute("CREATE MACRO IF NOT EXISTS YearsBetween(start_dt, end_dt) AS system.date_diff('year', CAST(start_dt AS DATE), CAST(end_dt AS DATE))")
    con.execute("CREATE MACRO IF NOT EXISTS MonthsBetween(start_dt, end_dt) AS system.date_diff('month', CAST(start_dt AS DATE), CAST(end_dt AS DATE))")
    con.execute("CREATE MACRO IF NOT EXISTS DaysBetween(start_dt, end_dt) AS system.date_diff('day', CAST(start_dt AS DATE), CAST(end_dt AS DATE))")
    con.execute("CREATE MACRO IF NOT EXISTS HoursBetween(start_dt, end_dt) AS system.date_diff('hour', CAST(start_dt AS TIMESTAMP), CAST(end_dt AS TIMESTAMP))")
    con.execute("CREATE MACRO IF NOT EXISTS MinutesBetween(start_dt, end_dt) AS system.date_diff('minute', CAST(start_dt AS TIMESTAMP), CAST(end_dt AS TIMESTAMP))")
    con.execute("CREATE MACRO IF NOT EXISTS SecondsBetween(start_dt, end_dt) AS system.date_diff('second', CAST(start_dt AS TIMESTAMP), CAST(end_dt AS TIMESTAMP))")


__all__ = ["registerDateTimeMacros"]
