"""
CQL Math functions as DuckDB SQL macros.

Tier 1 implementation - zero Python overhead.
These macros are inlined at query planning time.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import duckdb


def registerMathMacros(con: "duckdb.DuckDBPyConnection") -> None:
    """
    Register math function macros (Tier 1).

    Registers native DuckDB SQL macros for CQL math functions:
    - Abs, Ceiling, Floor, Round, RoundTo, Sqrt, Exp, Ln, Log, Power
    - Truncate, Sign, Mod, Div

    All functions have zero Python overhead.

    Note: Uses 'system.' prefix to reference built-in functions and avoid
    infinite recursion when macro name matches the function name.
    """
    # Direct mappings to native DuckDB functions (use system. prefix to avoid recursion)
    con.execute("CREATE MACRO IF NOT EXISTS Abs(x) AS system.abs(x)")
    con.execute("CREATE MACRO IF NOT EXISTS Ceiling(x) AS system.ceiling(x)")
    con.execute("CREATE MACRO IF NOT EXISTS Floor(x) AS system.floor(x)")

    # Round - CQL §16.16: Round half up (toward positive infinity).
    # DuckDB's built-in ROUND uses half-away-from-zero which gives wrong
    # results for negative ties (-0.5 → -1 instead of 0).
    # Use FLOOR(x + 0.5) for the 0-precision case.
    con.execute("CREATE OR REPLACE MACRO Round(x) AS CASE WHEN x IS NULL THEN NULL ELSE CAST(FLOOR(CAST(x AS DOUBLE) + 0.5) AS DECIMAL(38, 8)) END")
    con.execute("CREATE OR REPLACE MACRO RoundTo(x, prec) AS CASE WHEN x IS NULL THEN NULL ELSE CAST(FLOOR(CAST(x AS DOUBLE) * POWER(10, prec) + 0.5) / POWER(10, prec) AS DECIMAL(38, 8)) END")

    # Other math functions
    con.execute("CREATE MACRO IF NOT EXISTS Sqrt(x) AS system.sqrt(x)")
    con.execute("CREATE MACRO IF NOT EXISTS Exp(x) AS system.exp(x)")
    con.execute("CREATE MACRO IF NOT EXISTS Ln(x) AS system.ln(x)")
    con.execute("CREATE MACRO IF NOT EXISTS Log(x) AS system.log(x)")  # Base 10

    # Arbitrary base logarithm
    con.execute("CREATE MACRO IF NOT EXISTS LogBase(x, base) AS system.ln(x) / system.ln(base)")

    con.execute("CREATE MACRO IF NOT EXISTS Power(x, y) AS system.pow(x, y)")
    con.execute("CREATE MACRO IF NOT EXISTS Truncate(x) AS system.trunc(x)")
    con.execute("CREATE MACRO IF NOT EXISTS Sign(x) AS system.sign(x)")

    # Modulo and integer division
    con.execute("CREATE MACRO IF NOT EXISTS Mod(x, y) AS x % y")
    con.execute("CREATE MACRO IF NOT EXISTS Div(x, y) AS x // y")


__all__ = ["registerMathMacros"]
