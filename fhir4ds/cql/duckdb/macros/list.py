"""
CQL List functions as DuckDB SQL macros.

Tier 1 implementation - zero Python overhead.

IMPORTANT: DuckDB uses 1-based indexing for arrays.
These macros implement CQL list semantics with proper NULL handling.

Note: Uses 'system.' prefix to reference built-in functions and avoid
infinite recursion when macro name matches the function name.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import duckdb


def registerListMacros(con: "duckdb.DuckDBPyConnection") -> None:
    """
    Register list function macros (Tier 1).

    Registers native DuckDB SQL macros for CQL list functions:
    - First(list) - Get first element, NULL if empty or NULL input
    - Last(list) - Get last element, NULL if empty or NULL input
    - Skip(list, n) - Skip first n elements
    - Take(list, n) - Take first n elements
    - Distinct(list) - Remove duplicates

    Note: Uses system. prefix to avoid shadowing DuckDB built-ins.
    """
    # ============================================
    # First - Get first element of list
    # Returns NULL if list is NULL or empty
    # ============================================
    con.execute(
        "CREATE MACRO IF NOT EXISTS First(lst) AS "
        "CASE WHEN lst IS NULL OR system.array_length(lst) = 0 THEN NULL ELSE lst[1] END"
    )

    # ============================================
    # Last - Get last element of list
    # Returns NULL if list is NULL or empty
    # ============================================
    con.execute(
        "CREATE MACRO IF NOT EXISTS Last(lst) AS "
        "CASE WHEN lst IS NULL OR system.array_length(lst) = 0 THEN NULL ELSE lst[-1] END"
    )

    # ============================================
    # Skip - Skip first n elements
    # Returns empty list if n >= length, handles n > len gracefully
    # ============================================
    con.execute(
        "CREATE MACRO IF NOT EXISTS Skip(lst, n) AS "
        "CASE WHEN lst IS NULL OR n IS NULL OR n < 0 THEN NULL "
        "WHEN n >= system.array_length(lst) THEN [] "
        "ELSE lst[n + 1:] END"
    )

    # ============================================
    # Take - Take first n elements
    # Returns full list if n > length, handles gracefully
    # DuckDB slicing is inclusive: [1:n] returns elements at positions 1 through n
    # ============================================
    con.execute(
        "CREATE MACRO IF NOT EXISTS Take(lst, n) AS "
        "CASE WHEN lst IS NULL OR n IS NULL OR n < 0 THEN NULL "
        "WHEN n = 0 THEN [] "
        "ELSE lst[1:n] END"
    )

    # ============================================
    # Distinct - Remove duplicates from list
    # Returns NULL if list is NULL, empty list preserved
    # Distinct is a reserved keyword, need quotes
    # Note: Uses list_distinct (not array_unique which returns a count)
    # ============================================
    con.execute(
        'CREATE MACRO IF NOT EXISTS "Distinct"(lst) AS '
        "CASE WHEN lst IS NULL THEN NULL ELSE list_distinct(lst) END"
    )


__all__ = ["registerListMacros"]
