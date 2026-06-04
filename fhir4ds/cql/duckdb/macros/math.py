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
    - Truncate, Sign, Mod, Div, CQLMessage

    All functions have zero Python overhead.

    Note: Uses 'system.' prefix to reference built-in functions and avoid
    infinite recursion when macro name matches the function name.
    """
    # Direct mappings to native DuckDB functions (use system. prefix to avoid recursion)
    con.execute("CREATE OR REPLACE MACRO Abs(x) AS TRY(system.abs(x))")
    con.execute("CREATE OR REPLACE MACRO Ceiling(x) AS TRY(system.ceiling(x))")
    con.execute("CREATE OR REPLACE MACRO Floor(x) AS TRY(system.floor(x))")

    # Round - CQL Appendix B: traditional rounding, with negative half values
    # rounded away from zero. Null precision is defined as precision 0.
    con.execute(
        "CREATE OR REPLACE MACRO Round(x) AS "
        "CASE WHEN x IS NULL THEN NULL ELSE CAST("
        "CASE WHEN CAST(x AS DOUBLE) >= 0 THEN FLOOR(CAST(x AS DOUBLE) + 0.5) "
        "ELSE CEIL(CAST(x AS DOUBLE) - 0.5) END AS DECIMAL(38, 8)) END"
    )
    con.execute(
        "CREATE OR REPLACE MACRO RoundTo(x, prec) AS "
        "CASE WHEN x IS NULL THEN NULL ELSE CAST(("
        "CASE "
        "WHEN CAST(x AS DOUBLE) * POWER(10, COALESCE(prec, 0)) >= 0 "
        "THEN FLOOR(CAST(x AS DOUBLE) * POWER(10, COALESCE(prec, 0)) + 0.5) "
        "ELSE CEIL(CAST(x AS DOUBLE) * POWER(10, COALESCE(prec, 0)) - 0.5) "
        "END) / POWER(10, COALESCE(prec, 0)) AS DECIMAL(38, 8)) END"
    )

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
    # CQL Log is the arbitrary-base two-argument operator. Natural log is Ln.
    con.execute(
        "CREATE OR REPLACE MACRO Log(x, base) AS "
        "CASE WHEN isfinite(TRY(system.ln(CAST(x AS DOUBLE)) / system.ln(CAST(base AS DOUBLE)))) "
        "THEN system.ln(x) / system.ln(base) ELSE NULL END"
    )
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

    # CQL Appendix B Errors and Messaging: Message returns source unchanged,
    # except true-condition Error severity raises a runtime error.
    con.execute(
        """
        CREATE OR REPLACE MACRO CQLMessage(source, condition, code, severity, message) AS
        CASE
            WHEN COALESCE(condition, FALSE) AND lower(CAST(severity AS VARCHAR)) = 'error'
            THEN error(COALESCE(CAST(code AS VARCHAR), '') || ': ' || COALESCE(CAST(message AS VARCHAR), ''))
            ELSE source
        END
        """
    )


__all__ = ["registerMathMacros"]
