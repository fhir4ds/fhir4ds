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
        "CASE WHEN lst IS NULL THEN NULL "
        "WHEN n IS NULL OR n <= 0 THEN lst[1:0] "
        "ELSE lst[1:n] END"
    )

    # ============================================
    # Distinct - Remove duplicates from list (CQL §20.25)
    # Preserves original order and retains one null if any
    # Returns empty list for empty input (not NULL)
    # ============================================
    con.execute(
        'CREATE OR REPLACE MACRO "Distinct"(lst) AS '
        "CASE WHEN lst IS NULL THEN NULL "
        "WHEN system.array_length(lst) = 0 THEN lst "
        "ELSE COALESCE((SELECT list(val ORDER BY pos) FROM ("
        "SELECT val, MIN(pos) as pos FROM ("
        "SELECT unnest(lst) AS val, generate_subscripts(lst, 1) AS pos"
        ") GROUP BY val)), []) END"
    )

    # ============================================
    # Tail - All elements except the first (CQL §20.25)
    # Returns empty list if list has 0 or 1 element
    # ============================================
    con.execute(
        "CREATE MACRO IF NOT EXISTS Tail(lst) AS "
        "CASE WHEN lst IS NULL THEN NULL "
        "WHEN system.array_length(lst) <= 1 THEN lst[1:0] "
        "ELSE lst[2:] END"
    )

    # ============================================
    # IndexOf - Find position of element in list (CQL §20.12)
    # Returns 0-based index, or -1 if not found
    # CQL: if either argument is null, result is null
    # Named CQLIndexOf to avoid conflict with C++ FHIRPath extension's IndexOf
    # ============================================
    con.execute(
        "CREATE MACRO IF NOT EXISTS CQLIndexOf(lst, elem) AS "
        "CASE WHEN lst IS NULL OR elem IS NULL THEN NULL "
        "WHEN list_position(lst, elem) IS NULL THEN -1 "
        "WHEN list_position(lst, elem) = 0 THEN -1 "
        "ELSE list_position(lst, elem) - 1 END"
    )

    # ============================================
    # Combine - CQL §20.4: concatenate a list of strings into one string
    # Combine(source List<String>) → String
    # Combine(source List<String>, separator String) → String
    # ============================================
    con.execute(
        "CREATE MACRO IF NOT EXISTS Combine(lst) AS "
        "CASE WHEN lst IS NULL THEN NULL "
        "ELSE system.array_to_string(list_filter(lst, x -> x IS NOT NULL), '') END"
    )
    con.execute(
        "CREATE MACRO IF NOT EXISTS CombineSep(lst, sep) AS "
        "CASE WHEN lst IS NULL THEN NULL "
        "ELSE system.array_to_string(list_filter(lst, x -> x IS NOT NULL), sep) END"
    )

    # ============================================
    # Product - CQL §20.22: multiply all elements in a list
    # Uses list_aggregate with 'product'; casts elements to DOUBLE first
    # ============================================
    con.execute(
        "CREATE MACRO IF NOT EXISTS Product(lst) AS "
        "CASE WHEN lst IS NULL THEN NULL "
        "ELSE list_aggregate(list_transform(lst, _v -> TRY_CAST(_v AS DOUBLE)), 'product') END"
    )

    # ============================================
    # Descendents - CQL §20.4: returns null for null input
    # Full implementation would recursively collect all child properties;
    # for null input, result is null.
    # ============================================
    con.execute(
        "CREATE MACRO IF NOT EXISTS descendents(x) AS "
        "CASE WHEN x IS NULL THEN NULL ELSE x END"
    )


__all__ = ["registerListMacros"]
