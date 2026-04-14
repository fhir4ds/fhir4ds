"""
FHIRPath String functions as DuckDB SQL macros.

Tier 1 implementation - zero Python overhead.

IMPORTANT: FHIRPath uses 0-based indexing, DuckDB uses 1-based indexing.
These macros handle the conversion automatically.

Note: Uses 'system.' prefix to reference built-in functions and avoid
infinite recursion when macro name matches the function name.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import duckdb


def register_string_macros(con: "duckdb.DuckDBPyConnection") -> None:
    """
    Register string function macros (Tier 1).

    Registers native DuckDB SQL macros for FHIRPath string functions.
    Handles 0-based to 1-based index conversion for Substring and IndexOf.

    Note: Uses system. prefix to avoid shadowing DuckDB built-ins.
    """
    # Direct mappings (use system. prefix to avoid recursion)
    con.execute("CREATE MACRO IF NOT EXISTS Length(s) AS system.length(s)")
    con.execute("CREATE MACRO IF NOT EXISTS Upper(s) AS system.upper(s)")
    con.execute("CREATE MACRO IF NOT EXISTS Lower(s) AS system.lower(s)")

    # Concat with NULL propagation (FHIRPath semantics)
    con.execute("CREATE MACRO IF NOT EXISTS Concat(s1, s2) AS s1 || s2")

    # String checking functions
    con.execute("CREATE MACRO IF NOT EXISTS StartsWith(s, prefix) AS system.starts_with(s, prefix)")
    con.execute("CREATE MACRO IF NOT EXISTS EndsWith(s, suffix) AS system.ends_with(s, suffix)")
    con.execute("CREATE MACRO IF NOT EXISTS Contains(s, pattern) AS system.contains(s, pattern)")

    # String manipulation
    con.execute("CREATE MACRO IF NOT EXISTS Replace(s, from_str, to_str) AS system.replace(s, from_str, to_str)")

    # Trimming functions
    con.execute("CREATE MACRO IF NOT EXISTS Trim(s) AS system.trim(s)")
    con.execute("CREATE MACRO IF NOT EXISTS LTrim(s) AS system.ltrim(s)")
    con.execute("CREATE MACRO IF NOT EXISTS RTrim(s) AS system.rtrim(s)")

    # ============================================
    # INDEX CONVERSION: FHIRPath 0-based -> DuckDB 1-based
    # ============================================

    # Substring with index conversion: FHIRPath uses 0-based, DuckDB uses 1-based
    # 2-argument version: Substring(s, start) -> from position to end
    con.execute(
        "CREATE MACRO IF NOT EXISTS Substring(s, start) AS "
        "system.substring(s, start + 1)"
    )

    # 3-argument version: SubstringLen(s, start, length)
    con.execute(
        "CREATE MACRO IF NOT EXISTS SubstringLen(s, start, len) AS "
        "system.substring(s, start + 1, len)"
    )

    # IndexOf: FHIRPath returns -1 if not found, 0-based index if found
    # DuckDB STRPOS returns 0 if not found, 1-based index if found
    con.execute(
        "CREATE MACRO IF NOT EXISTS IndexOf(s, pattern) AS "
        "CASE WHEN system.strpos(s, pattern) = 0 THEN -1 ELSE system.strpos(s, pattern) - 1 END"
    )


__all__ = ["register_string_macros"]
