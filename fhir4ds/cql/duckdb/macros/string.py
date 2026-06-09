"""
CQL String functions as DuckDB SQL macros.

Tier 1 implementation - zero Python overhead.

IMPORTANT: CQL uses 0-based indexing, DuckDB uses 1-based indexing.
These macros handle the conversion automatically.

Note: Uses 'system.' prefix to reference built-in functions and avoid
infinite recursion when macro name matches the function name.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import duckdb


def registerStringMacros(con: "duckdb.DuckDBPyConnection") -> None:
    """
    Register string function macros (Tier 1).

    Registers native DuckDB SQL macros for CQL string functions.
    Handles 0-based to 1-based index conversion for Substring and IndexOf.

    Note: Uses system. prefix to avoid shadowing DuckDB built-ins.
    """
    # Direct mappings (use system. prefix to avoid recursion)
    con.execute(
        "CREATE OR REPLACE MACRO Length(s) AS "
        "CASE WHEN s IS NULL AND ends_with(typeof(s), '[]') THEN 0 "
        "ELSE system.length(s) END"
    )
    con.execute("CREATE MACRO IF NOT EXISTS Upper(s) AS system.upper(s)")
    con.execute("CREATE MACRO IF NOT EXISTS Lower(s) AS system.lower(s)")

    # Concat with NULL propagation (FHIRPath/CQL semantics)
    con.execute(
        "CREATE OR REPLACE MACRO Concat(s1, s2) AS "
        "CASE WHEN typeof(s1) NOT IN ('VARCHAR', '\"NULL\"') "
        "OR typeof(s2) NOT IN ('VARCHAR', '\"NULL\"') "
        "THEN error('CQL Concat requires String operands') "
        "WHEN s1 IS NULL OR s2 IS NULL THEN NULL "
        "ELSE s1 || s2 END"
    )

    # String checking functions
    con.execute("CREATE MACRO IF NOT EXISTS StartsWith(s, prefix) AS system.starts_with(s, prefix)")
    con.execute("CREATE MACRO IF NOT EXISTS EndsWith(s, suffix) AS system.ends_with(s, suffix)")
    con.execute("CREATE MACRO IF NOT EXISTS Contains(s, pattern) AS system.contains(s, pattern)")

    # String manipulation
    con.execute("CREATE MACRO IF NOT EXISTS Replace(s, from_str, to_str) AS system.replace(s, from_str, to_str)")
    con.execute("CREATE MACRO IF NOT EXISTS Split(s, delim) AS system.string_split(s, delim)")
    con.execute(
        "CREATE MACRO IF NOT EXISTS SplitOnMatches(s, pattern) AS "
        "cqlRegexSplitOnMatches(s, pattern)"
    )

    # Trimming functions
    con.execute("CREATE MACRO IF NOT EXISTS Trim(s) AS system.trim(s)")
    con.execute("CREATE MACRO IF NOT EXISTS LTrim(s) AS system.ltrim(s)")
    con.execute("CREATE MACRO IF NOT EXISTS RTrim(s) AS system.rtrim(s)")

    # Additional string functions
    con.execute("CREATE MACRO IF NOT EXISTS Reverse(s) AS system.reverse(s)")
    # Left and Right are reserved keywords, need quotes
    con.execute('CREATE MACRO IF NOT EXISTS "Left"(s, n) AS system.left(s, n)')
    con.execute('CREATE MACRO IF NOT EXISTS "Right"(s, n) AS system.right(s, n)')

    # ============================================
    # INDEX CONVERSION: CQL 0-based → DuckDB 1-based
    # ============================================

    # Substring with index conversion: CQL uses 0-based, DuckDB uses 1-based.
    # CQL defines both Substring(s, start) and Substring(s, start, length).
    # DuckDB macros do not distinguish omitted defaults from explicit NULL, so
    # use a sentinel outside CQL Integer range for the optional length.
    con.execute(
        "CREATE OR REPLACE MACRO Substring(s, start, len := -2147483649) AS "
        "CASE WHEN s IS NULL OR start IS NULL OR start < 0 OR start >= system.length(s) THEN NULL "
        "WHEN len = -2147483649 THEN system.substring(s, start + 1) "
        "WHEN len IS NULL OR len < 0 THEN NULL "
        "ELSE system.substring(s, start + 1, len) END"
    )

    # Backward-compatible alias used by older direct SQL checks.
    con.execute(
        "CREATE OR REPLACE MACRO SubstringLen(s, start, len) AS "
        "Substring(s, start, len)"
    )

    # NOTE: CQL IndexOf is a LIST operation (§20.13), not a string operation.
    # String position finding is PositionOf (§17.11), translated directly by
    # the translator to strpos().  The list IndexOf macro is in list.py.
    con.execute(
        "CREATE MACRO IF NOT EXISTS PositionOf(pattern, s) AS "
        "CASE WHEN s IS NULL OR pattern IS NULL THEN NULL "
        "WHEN system.strpos(s, pattern) = 0 THEN -1 "
        "ELSE system.strpos(s, pattern) - 1 END"
    )

    # Indexer: CQL §17.6 — character at position (0-based)
    con.execute(
        "CREATE MACRO IF NOT EXISTS Indexer(s, idx) AS "
        "CASE WHEN s IS NULL OR idx IS NULL THEN NULL "
        "WHEN idx < 0 OR idx >= system.length(s) THEN NULL "
        "ELSE system.substring(s, idx + 1, 1) END"
    )

    # Matches: CQL §17.8 — test if string matches a regex pattern
    con.execute(
        "CREATE MACRO IF NOT EXISTS Matches(s, pattern) AS "
        "cqlRegexMatches(s, pattern)"
    )

    # ReplaceMatches: CQL §17.13 — replace regex matches in string
    # CQL uses Java regex replacement: $1-$9 = group backrefs, \$ = literal $, \\ = literal \
    con.execute(
        "CREATE MACRO IF NOT EXISTS ReplaceMatches(s, pattern, replacement) AS "
        "cqlRegexReplaceMatches(s, pattern, replacement)"
    )

    # Concatenate: CQL §17.1 — if any argument is null, result is null
    con.execute(
        "CREATE OR REPLACE MACRO Concatenate(s1, s2) AS "
        "CASE WHEN typeof(s1) NOT IN ('VARCHAR', '\"NULL\"') "
        "OR typeof(s2) NOT IN ('VARCHAR', '\"NULL\"') "
        "THEN error('CQL Concatenate requires String operands') "
        "WHEN s1 IS NULL OR s2 IS NULL THEN NULL "
        "ELSE s1 || s2 END"
    )

    # LastPositionOf: CQL §17.7 — last position of pattern in string (0-based)
    con.execute(
        "CREATE MACRO IF NOT EXISTS LastPositionOf(pattern, s) AS "
        "CASE WHEN s IS NULL OR pattern IS NULL THEN NULL "
        "WHEN system.strpos(system.reverse(s), system.reverse(pattern)) = 0 THEN -1 "
        "ELSE system.length(s) - system.strpos(system.reverse(s), system.reverse(pattern)) - system.length(pattern) + 1 END"
    )


__all__ = ["registerStringMacros"]
