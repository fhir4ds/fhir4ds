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

    # Round - two versions:
    # Round(x) defaults to 0 decimal places (CQL default)
    # RoundTo(x, precision) allows specifying precision
    con.execute("CREATE MACRO IF NOT EXISTS Round(x) AS system.round(x, 0)")
    con.execute("CREATE MACRO IF NOT EXISTS RoundTo(x, prec) AS system.round(x, prec)")

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
