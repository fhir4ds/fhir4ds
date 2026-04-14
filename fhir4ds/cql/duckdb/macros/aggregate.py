"""
CQL Aggregate functions as DuckDB SQL macros.

Tier 1 implementation - zero Python overhead.

Note: Count, Sum, Min, Max, Avg are intentionally NOT registered as macros.
DuckDB already provides these as built-in aggregates; registering macros
for them shadows the built-ins and breaks COUNT(DISTINCT x), FILTER clauses,
and window function syntax.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import duckdb


def registerAggregateMacros(con: "duckdb.DuckDBPyConnection") -> None:
    """
    Register aggregate function macros (Tier 1).

    Registers native DuckDB SQL macros for CQL aggregate functions:
    - Statistical: Median, Mode, StdDev, Variance
    - Boolean: AllTrue, AnyTrue, AllFalse, AnyFalse

    Note: Count, Sum, Min, Max, Avg are NOT registered as macros because
    DuckDB already provides these as built-in aggregates with identical
    semantics. Registering macros for them shadows the built-ins and breaks
    COUNT(DISTINCT x), SUM(x) FILTER (...), window functions, etc.
    """
    # ============================================
    # Statistical aggregates
    # ============================================
    con.execute("CREATE MACRO IF NOT EXISTS Median(x) AS system.median(x)")
    con.execute("CREATE MACRO IF NOT EXISTS Mode(x) AS system.mode(x)")
    con.execute("CREATE MACRO IF NOT EXISTS StdDev(x) AS system.stddev_samp(x)")
    con.execute("CREATE MACRO IF NOT EXISTS StdDevPop(x) AS system.stddev_pop(x)")
    con.execute("CREATE MACRO IF NOT EXISTS Variance(x) AS system.var_samp(x)")
    con.execute("CREATE MACRO IF NOT EXISTS VarPop(x) AS system.var_pop(x)")

    # ============================================
    # Boolean aggregates
    # ============================================
    con.execute("CREATE MACRO IF NOT EXISTS AllTrue(x) AS system.bool_and(x)")
    con.execute("CREATE MACRO IF NOT EXISTS AnyTrue(x) AS system.bool_or(x)")
    con.execute("CREATE MACRO IF NOT EXISTS AllFalse(x) AS NOT system.bool_or(x)")
    con.execute("CREATE MACRO IF NOT EXISTS AnyFalse(x) AS NOT system.bool_and(x)")


__all__ = ["registerAggregateMacros"]
