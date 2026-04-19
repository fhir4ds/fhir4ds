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
    # Date differences — CQL calendar duration semantics
    # CQL §5.6.2: duration-between counts whole calendar units,
    # adjusting when the sub-unit components of end < start.
    # DuckDB date_diff counts boundary crossings, which over-counts
    # when the birthday/day-of-month has not yet been reached.
    # ============================================
    con.execute(
        "CREATE MACRO IF NOT EXISTS YearsBetween(start_dt, end_dt) AS "
        "CASE WHEN CAST(start_dt AS DATE) IS NULL OR CAST(end_dt AS DATE) IS NULL THEN NULL ELSE "
        "EXTRACT(YEAR FROM CAST(end_dt AS DATE)) - EXTRACT(YEAR FROM CAST(start_dt AS DATE)) "
        "- CASE WHEN EXTRACT(MONTH FROM CAST(end_dt AS DATE)) < EXTRACT(MONTH FROM CAST(start_dt AS DATE)) "
        "OR (EXTRACT(MONTH FROM CAST(end_dt AS DATE)) = EXTRACT(MONTH FROM CAST(start_dt AS DATE)) "
        "AND EXTRACT(DAY FROM CAST(end_dt AS DATE)) < EXTRACT(DAY FROM CAST(start_dt AS DATE))) "
        "THEN 1 ELSE 0 END END"
    )
    con.execute(
        "CREATE MACRO IF NOT EXISTS MonthsBetween(start_dt, end_dt) AS "
        "CASE WHEN CAST(start_dt AS DATE) IS NULL OR CAST(end_dt AS DATE) IS NULL THEN NULL ELSE "
        "(EXTRACT(YEAR FROM CAST(end_dt AS DATE)) * 12 + EXTRACT(MONTH FROM CAST(end_dt AS DATE))) "
        "- (EXTRACT(YEAR FROM CAST(start_dt AS DATE)) * 12 + EXTRACT(MONTH FROM CAST(start_dt AS DATE))) "
        "- CASE WHEN EXTRACT(DAY FROM CAST(end_dt AS DATE)) < EXTRACT(DAY FROM CAST(start_dt AS DATE)) "
        "THEN 1 ELSE 0 END END"
    )
    # CQL §22.21 DurationBetween: floor of elapsed time, NOT boundary crossings.
    # Use epoch_ms-based calculation with TIMESTAMPTZ for timezone support.
    # TIMESTAMPTZ preserves timezone offsets; time strings fall back to anchored TIMESTAMP.
    # Pad partial time strings (e.g., "06" → "06:00:00") for valid TIMESTAMP parsing.
    _time_pad = (
        "CASE "
        "WHEN length(system.ltrim(CAST({0} AS VARCHAR), 'T')) <= 2 "
        "THEN system.ltrim(CAST({0} AS VARCHAR), 'T') || ':00:00' "
        "WHEN length(system.ltrim(CAST({0} AS VARCHAR), 'T')) <= 5 "
        "THEN system.ltrim(CAST({0} AS VARCHAR), 'T') || ':00' "
        "ELSE system.ltrim(CAST({0} AS VARCHAR), 'T') END"
    )
    _ems = (
        "COALESCE("
        "epoch_ms(TRY_CAST({0} AS TIMESTAMPTZ)), "
        "epoch_ms(CAST('1970-01-01T' || (" + _time_pad + ") AS TIMESTAMP))"
        ")"
    )
    _start_ems = _ems.format("start_dt")
    _end_ems = _ems.format("end_dt")
    _diff = f"({_end_ems} - {_start_ems})"
    con.execute(f"CREATE MACRO IF NOT EXISTS DaysBetween(start_dt, end_dt) AS CAST(TRUNC({_diff} / 86400000.0) AS BIGINT)")
    con.execute(f"CREATE MACRO IF NOT EXISTS WeeksBetween(start_dt, end_dt) AS CAST(TRUNC({_diff} / 604800000.0) AS BIGINT)")
    con.execute(f"CREATE MACRO IF NOT EXISTS HoursBetween(start_dt, end_dt) AS CAST(TRUNC({_diff} / 3600000.0) AS BIGINT)")
    con.execute(f"CREATE MACRO IF NOT EXISTS MinutesBetween(start_dt, end_dt) AS CAST(TRUNC({_diff} / 60000.0) AS BIGINT)")
    con.execute(f"CREATE MACRO IF NOT EXISTS SecondsBetween(start_dt, end_dt) AS CAST(TRUNC({_diff} / 1000.0) AS BIGINT)")
    con.execute(f"CREATE MACRO IF NOT EXISTS MillisecondsBetween(start_dt, end_dt) AS CAST({_diff} AS BIGINT)")


__all__ = ["registerDateTimeMacros"]
