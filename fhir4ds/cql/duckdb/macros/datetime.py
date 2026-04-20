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
    # Hour/Minute/Second/Millisecond: CQL time values may be strings ('T12:00:00'),
    # so try TIME cast first (stripping leading T), then TIMESTAMP cast.
    # CAST(dt AS VARCHAR) ensures non-string types work with system.ltrim.
    con.execute(
        "CREATE MACRO IF NOT EXISTS Hour(dt) AS "
        "COALESCE("
        "  system.hour(TRY_CAST(system.ltrim(CAST(dt AS VARCHAR), 'T') AS TIME)),"
        "  system.hour(TRY_CAST(dt AS TIMESTAMP))"
        ")"
    )
    con.execute(
        "CREATE MACRO IF NOT EXISTS Minute(dt) AS "
        "COALESCE("
        "  system.minute(TRY_CAST(system.ltrim(CAST(dt AS VARCHAR), 'T') AS TIME)),"
        "  system.minute(TRY_CAST(dt AS TIMESTAMP))"
        ")"
    )
    con.execute(
        "CREATE MACRO IF NOT EXISTS Second(dt) AS "
        "COALESCE("
        "  system.second(TRY_CAST(system.ltrim(CAST(dt AS VARCHAR), 'T') AS TIME)),"
        "  system.second(TRY_CAST(dt AS TIMESTAMP))"
        ")"
    )
    con.execute(
        "CREATE MACRO IF NOT EXISTS Millisecond(dt) AS "
        "COALESCE("
        "  system.millisecond(TRY_CAST(system.ltrim(CAST(dt AS VARCHAR), 'T') AS TIME)),"
        "  system.millisecond(TRY_CAST(dt AS TIMESTAMP))"
        ") % 1000"
    )

    # ============================================
    # Date constructors (avoiding reserved keywords)
    # Note: 'Date' is a reserved type in DuckDB, use MakeDate
    # ============================================
    con.execute("CREATE MACRO IF NOT EXISTS MakeDate(yr, mo, dy) AS system.make_date(yr, mo, dy)")
    con.execute("CREATE MACRO IF NOT EXISTS MakeTime(hr, mi, sc) AS system.make_time(hr, mi, sc)")
    con.execute("CREATE MACRO IF NOT EXISTS MakeDateTime(yr, mo, dy) AS system.make_timestamp(yr, mo, dy, 0, 0, 0)")

    # ============================================
    # Date differences — ALL registered as Python UDFs
    # CQL §22.21: DurationBetween with uncertainty interval support.
    # Python UDFs handle partial ISO 8601 strings and return
    # uncertainty intervals (JSON) when input precision < unit precision.
    # See registerDatetimeUdfs() in datetime.py.
    # ============================================


__all__ = ["registerDateTimeMacros"]
