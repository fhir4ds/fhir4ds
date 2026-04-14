"""
CQL Logical functions as DuckDB SQL macros.

Tier 1 & 2 implementation - minimal overhead.

IMPORTANT: CQL uses three-valued logic (true/false/null).
The Implies macro handles CQL semantics correctly.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import duckdb


def registerLogicalMacros(con: "duckdb.DuckDBPyConnection") -> None:
    """
    Register logical function macros (Tier 1 & 2).

    Tier 1 (direct mappings):
    - And, Or, Not, Coalesce

    Tier 2 (SQL expressions):
    - Xor: Exclusive or
    - Implies: CQL implication with 3VL
    - AllFalse, AnyFalse: Negated boolean aggregates
    """
    # ============================================
    # Tier 1: Direct mappings
    # ============================================
    con.execute('CREATE MACRO IF NOT EXISTS "And"(a, b) AS a AND b')
    con.execute('CREATE MACRO IF NOT EXISTS "Or"(a, b) AS a OR b')
    con.execute('CREATE MACRO IF NOT EXISTS "Not"(a) AS NOT a')
    con.execute('CREATE MACRO IF NOT EXISTS "Coalesce"(a, b) AS COALESCE(a, b)')

    # ============================================
    # Tier 2: SQL expressions
    # ============================================

    # Xor: true when exactly one operand is true
    con.execute('CREATE MACRO IF NOT EXISTS "Xor"(a, b) AS (a OR b) AND NOT (a AND b)')

    # ============================================
    # CQL Implies with three-valued logic
    # ============================================
    # CQL semantics (CQL spec section 13.2):
    # - false implies X = true (vacuously true)
    # - true implies true = true
    # - true implies false = false
    # - true implies null = null
    # - null implies true = true
    # - null implies false/null = null
    con.execute("""
        CREATE MACRO IF NOT EXISTS "Implies"(a, b) AS
        CASE
            WHEN a = false THEN true
            WHEN b = true THEN true
            WHEN a IS NULL OR b IS NULL THEN NULL
            ELSE NOT a OR b
        END
    """)

    # Null handling helpers
    con.execute('CREATE MACRO IF NOT EXISTS "IsNull"(x) AS x IS NULL')
    con.execute('CREATE MACRO IF NOT EXISTS "IsNotNull"(x) AS x IS NOT NULL')
    con.execute('CREATE MACRO IF NOT EXISTS "IfNull"(a, b) AS COALESCE(a, b)')


__all__ = ["registerLogicalMacros"]
