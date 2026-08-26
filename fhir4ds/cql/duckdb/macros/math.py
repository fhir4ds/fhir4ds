"""
CQL Math functions as DuckDB SQL macros.

Tier 1 implementation - zero Python overhead.
These macros are inlined at query planning time.
"""

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation, localcontext
from typing import TYPE_CHECKING

import duckdb

if TYPE_CHECKING:
    import duckdb


def _cql_divide(a, b):
    """CQL §16.4 divide: exact Decimal division at implementation scale 8.

    DuckDB's native ``/`` always promotes DECIMAL operands to DOUBLE,
    producing binary floating-point artifacts (e.g. ``9.9 / 3.0`` ->
    3.3000000000000003). CQL defines divide as *Decimal* division limited
    to the implementation precision/scale (28/8 here), so the result must
    be quantized half-up to 8 fractional digits, not a DOUBLE. Returns
    NULL for NULL operands, a zero divisor, non-numeric operands, or a
    result outside the representable Decimal range (spec: "If the result
    of the division cannot be represented ... the result is null").
    Operands arrive as VARCHAR (DuckDB casts DECIMAL/ints exactly; DOUBLE
    via its shortest round-trip representation).
    """
    if a is None or b is None:
        return None
    try:
        da = a if isinstance(a, Decimal) else Decimal(str(a).strip())
        db = b if isinstance(b, Decimal) else Decimal(str(b).strip())
    except (ValueError, InvalidOperation, ArithmeticError):
        return None
    if db == 0:
        return None
    try:
        with localcontext() as ctx:
            ctx.prec = 60
            quotient = da / db
            result = quotient.quantize(Decimal("1.00000000"), rounding=ROUND_HALF_UP)
    except (InvalidOperation, ArithmeticError):
        return None
    if result.copy_abs() >= Decimal(10) ** 28:
        # Exceeds the implementation Decimal range (28 digits, scale 8).
        return None
    return result


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
    # CQL 1.5 Appendix B Ceiling/Floor: "If the result of the operation
    # cannot be represented as an Integer, the result is null."
    # TRY_CAST to INTEGER nulls out-of-Integer-extent results (e.g.
    # Ceiling(3147483647.05), Floor(2147483648.2)) and NULL inputs.
    con.execute(
        "CREATE OR REPLACE MACRO Ceiling(x) AS TRY_CAST(system.ceiling(x) AS INTEGER)"
    )
    con.execute(
        "CREATE OR REPLACE MACRO Floor(x) AS TRY_CAST(system.floor(x) AS INTEGER)"
    )

    # Round - CQL Appendix B: traditional rounding. Half ties round away from
    # zero, so -0.5 becomes -1 and -1.5 becomes -2.
    # CQL-11 HISTORIAN QA-001: use system.floor/system.ceil, NOT the bare
    # FLOOR/CEIL names — Floor(x) is overridden above as the CQL Floor macro
    # (TRY_CAST to INTEGER), which nulls any rounded magnitude above the
    # Integer range (e.g. Round(3147483647.05) -> NULL instead of
    # 3147483647). Round returns a Decimal, so only Decimal-unrepresentable
    # results (|x| >= 10^30) are null: TRY_CAST to DECIMAL(38, 8).
    con.execute(
        "CREATE OR REPLACE MACRO Round(x) AS "
        "CASE WHEN x IS NULL THEN NULL ELSE TRY_CAST("
        "CASE WHEN CAST(x AS DOUBLE) >= 0 "
        "THEN system.floor(CAST(x AS DOUBLE) + 0.5) "
        "ELSE system.ceil(CAST(x AS DOUBLE) - 0.5) END "
        "AS DECIMAL(38, 8)) END"
    )
    con.execute(
        "CREATE OR REPLACE MACRO RoundTo(x, prec) AS "
        "CASE WHEN x IS NULL THEN NULL ELSE TRY_CAST(("
        "CASE WHEN CAST(x AS DOUBLE) * POWER(10, COALESCE(prec, 0)) >= 0 "
        "THEN system.floor(CAST(x AS DOUBLE) * POWER(10, COALESCE(prec, 0)) + 0.5) "
        "ELSE system.ceil(CAST(x AS DOUBLE) * POWER(10, COALESCE(prec, 0)) - 0.5) END"
        ") / POWER(10, COALESCE(prec, 0)) AS DECIMAL(38, 8)) END"
    )

    # Other math functions
    con.execute("CREATE OR REPLACE MACRO Sqrt(x) AS TRY(system.sqrt(x))")
    # CQL v1.5.3 §16.6 Exp: "If the result of the operation cannot be
    # represented, the result is null." Reinforced by section header:
    # "operations that cause arithmetic overflow or underflow ... will
    # result in null, rather than a run-time error." So return NULL on
    # overflow (e.g. Exp(710), Exp(1000)), not a runtime error.
    # CQL signature Exp(argument Decimal) Decimal — the result is a
    # Decimal at the implementation scale (8), not a DOUBLE.
    con.execute(
        "CREATE OR REPLACE MACRO Exp(x) AS "
        "CASE "
        "WHEN x IS NULL THEN NULL "
        "WHEN isfinite(TRY(system.exp(CAST(x AS DOUBLE)))) "
        "THEN TRY_CAST(system.exp(x) AS DECIMAL(38, 8)) "
        "ELSE NULL END"
    )
    # CQL v1.5.3 §16.12 Ln: "If the result of the operation cannot be
    # represented, the result is null." Ln(0) is -infinity (cannot be
    # represented) and Ln(negative) is undefined; both return NULL per
    # spec, not runtime errors.
    # CQL signature Ln(argument Decimal) Decimal — Decimal result.
    con.execute(
        "CREATE OR REPLACE MACRO Ln(x) AS "
        "CASE "
        "WHEN x IS NULL THEN NULL "
        "WHEN TRY_CAST(x AS DOUBLE) = 0 THEN NULL "
        "WHEN TRY_CAST(x AS DOUBLE) < 0 THEN NULL "
        "WHEN isfinite(TRY(system.ln(CAST(x AS DOUBLE)))) "
        "THEN TRY_CAST(system.ln(x) AS DECIMAL(38, 8)) "
        "ELSE NULL END"
    )
    # CQL Log is the arbitrary-base two-argument operator. Natural log is Ln.
    # CQL signature Log(argument Decimal, base Decimal) Decimal.
    con.execute(
        "CREATE OR REPLACE MACRO Log(x, base) AS "
        "CASE WHEN isfinite(TRY(system.ln(CAST(x AS DOUBLE)) / system.ln(CAST(base AS DOUBLE)))) "
        "THEN TRY_CAST(system.ln(x) / system.ln(base) AS DECIMAL(38, 8)) ELSE NULL END"
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
    con.execute("CREATE MACRO IF NOT EXISTS Truncate(x) AS TRY_CAST(system.trunc(x) AS INTEGER)")
    con.execute("CREATE MACRO IF NOT EXISTS Sign(x) AS system.sign(x)")

    # Modulo and integer division
    con.execute("CREATE MACRO IF NOT EXISTS Mod(x, y) AS x % y")
    con.execute("CREATE MACRO IF NOT EXISTS Div(x, y) AS system.trunc(x / NULLIF(y, 0))")

    # CQL §16.4 divide (`/`): exact Decimal division. DuckDB `/` promotes
    # DECIMAL operands to DOUBLE (9.9 / 3.0 -> 3.3000000000000003), which
    # violates the Decimal result type and scale-8 quantization CQL
    # requires. Scalar-UDF (Tier 3) because exact base-10 division is not
    # expressible with DuckDB's DOUBLE-only decimal divide. Registered as
    # cqlDivide and referenced directly by the translator's divide lowering.
    try:
        con.create_function(
            "cqlDivide",
            _cql_divide,
            parameters=["VARCHAR", "VARCHAR"],
            return_type=duckdb.decimal_type(38, 8),
            null_handling="special",
        )
    except (duckdb.CatalogException, duckdb.InvalidInputException):
        # Already registered on this connection (repeated extension setup).
        pass

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
