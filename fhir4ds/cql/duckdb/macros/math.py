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
    con.execute("CREATE OR REPLACE MACRO Abs(x) AS TRY(system.abs(x))")
    con.execute("CREATE OR REPLACE MACRO Ceiling(x) AS TRY(system.ceiling(x))")
    con.execute("CREATE OR REPLACE MACRO Floor(x) AS TRY(system.floor(x))")

    # Round - CQL §16.16: Round half up (toward positive infinity).
    # DuckDB's built-in ROUND uses half-away-from-zero which gives wrong
    # results for negative ties (-0.5 → -1 instead of 0).
    # Use FLOOR(x + 0.5) for the 0-precision case.
    con.execute("CREATE OR REPLACE MACRO Round(x) AS CASE WHEN x IS NULL THEN NULL ELSE CAST(FLOOR(CAST(x AS DOUBLE) + 0.5) AS DECIMAL(38, 8)) END")
    con.execute("CREATE OR REPLACE MACRO RoundTo(x, prec) AS CASE WHEN x IS NULL THEN NULL ELSE CAST(FLOOR(CAST(x AS DOUBLE) * POWER(10, prec) + 0.5) / POWER(10, prec) AS DECIMAL(38, 8)) END")

    # Other math functions
    con.execute("CREATE OR REPLACE MACRO Sqrt(x) AS TRY(system.sqrt(x))")
    con.execute(
        "CREATE OR REPLACE MACRO Exp(x) AS "
        "CASE "
        "WHEN x IS NULL THEN NULL "
        "WHEN isfinite(TRY(system.exp(CAST(x AS DOUBLE)))) THEN system.exp(x) "
        "ELSE error('Exp results in overflow (positive infinity)') END"
    )
    con.execute(
        "CREATE OR REPLACE MACRO Ln(x) AS "
        "CASE "
        "WHEN x IS NULL THEN NULL "
        "WHEN TRY_CAST(x AS DOUBLE) = 0 THEN error('Ln(0) results in negative infinity') "
        "WHEN TRY_CAST(x AS DOUBLE) < 0 THEN NULL "
        "WHEN isfinite(TRY(system.ln(CAST(x AS DOUBLE)))) THEN system.ln(x) "
        "ELSE NULL END"
    )
    con.execute(
        "CREATE OR REPLACE MACRO Log(x) AS "
        "CASE WHEN isfinite(TRY(system.log(CAST(x AS DOUBLE)))) "
        "THEN system.log(x) ELSE NULL END"
    )  # Base 10

    # Arbitrary base logarithm
    con.execute(
        "CREATE OR REPLACE MACRO LogBase(x, base) AS "
        "CASE WHEN isfinite(TRY(system.ln(CAST(x AS DOUBLE)) / system.ln(CAST(base AS DOUBLE)))) "
        "THEN system.ln(x) / system.ln(base) ELSE NULL END"
    )

    con.execute(
        "CREATE OR REPLACE MACRO Power(x, y) AS "
        "CASE "
        "WHEN x IS NULL OR y IS NULL THEN NULL "
        "WHEN isfinite(TRY(system.pow(TRY_CAST(x AS DOUBLE), TRY_CAST(y AS DOUBLE)))) "
        "THEN system.pow(TRY_CAST(x AS DOUBLE), TRY_CAST(y AS DOUBLE)) "
        "ELSE NULL END"
    )
    con.execute("CREATE MACRO IF NOT EXISTS Truncate(x) AS system.trunc(x)")
    con.execute("CREATE MACRO IF NOT EXISTS Sign(x) AS system.sign(x)")

    # Modulo and integer division
    con.execute("CREATE MACRO IF NOT EXISTS Mod(x, y) AS x % y")
    con.execute("CREATE MACRO IF NOT EXISTS Div(x, y) AS system.trunc(x / NULLIF(y, 0))")


__all__ = ["registerMathMacros"]
