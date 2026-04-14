"""
CQL Type Conversion functions as DuckDB SQL macros.

Tier 1 implementation - zero Python overhead.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import duckdb


def registerConversionMacros(con: "duckdb.DuckDBPyConnection") -> None:
    """
    Register type conversion macros (Tier 1).

    Registers native DuckDB SQL macros for CQL type conversion functions.
    All use CAST for zero Python overhead.
    """
    # String conversion
    con.execute("CREATE MACRO IF NOT EXISTS ToString(x) AS CAST(x AS VARCHAR)")

    # Numeric conversions
    con.execute("CREATE MACRO IF NOT EXISTS ToInteger(x) AS CAST(x AS INTEGER)")
    con.execute("CREATE MACRO IF NOT EXISTS ToDecimal(x) AS CAST(x AS DECIMAL)")

    # Boolean conversion
    con.execute("CREATE MACRO IF NOT EXISTS ToBoolean(x) AS CAST(x AS BOOLEAN)")

    # Date/Time conversions
    con.execute("CREATE MACRO IF NOT EXISTS ToDate(x) AS CAST(x AS DATE)")
    con.execute("CREATE MACRO IF NOT EXISTS ToDateTime(x) AS CAST(x AS TIMESTAMP)")
    con.execute("CREATE MACRO IF NOT EXISTS ToTime(x) AS CAST(x AS TIME)")


__all__ = ["registerConversionMacros"]
