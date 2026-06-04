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
    - And, Or, Not

    Tier 2 (SQL expressions):
    - Xor: Exclusive or
    - Implies: CQL implication with 3VL
    - AllFalse, AnyFalse: Negated boolean aggregates
    """
    # ============================================
    # Tier 1: guarded logical mappings
    # ============================================
    con.execute(
        """
        CREATE OR REPLACE TEMP MACRO "__cql_bool_strict_valid"(x) AS
        (typeof(x) = 'BOOLEAN' OR typeof(x) = '"NULL"')
        """
    )
    con.execute(
        """
        CREATE OR REPLACE TEMP MACRO "__cql_bool_strict"(x) AS
        CASE WHEN typeof(x) = 'BOOLEAN' THEN CAST(x AS BOOLEAN) ELSE NULL END
        """
    )
    con.execute(
        """
        CREATE OR REPLACE TEMP MACRO "__cql_bool_text_valid"(x) AS
        (
            typeof(x) = 'BOOLEAN'
            OR typeof(x) = '"NULL"'
            OR (typeof(x) = 'VARCHAR' AND lower(CAST(x AS VARCHAR)) IN ('true', 'false'))
        )
        """
    )
    con.execute(
        """
        CREATE OR REPLACE TEMP MACRO "__cql_bool_text"(x) AS
        CASE
            WHEN typeof(x) = 'BOOLEAN' THEN CAST(x AS BOOLEAN)
            WHEN typeof(x) = 'VARCHAR' AND lower(CAST(x AS VARCHAR)) = 'true' THEN true
            WHEN typeof(x) = 'VARCHAR' AND lower(CAST(x AS VARCHAR)) = 'false' THEN false
            ELSE NULL
        END
        """
    )
    con.execute(
        """
        CREATE OR REPLACE TEMP MACRO "And"(a, b) AS
        CASE
            WHEN NOT "__cql_bool_strict_valid"(a) OR NOT "__cql_bool_strict_valid"(b) THEN NULL
            ELSE "__cql_bool_strict"(a) AND "__cql_bool_strict"(b)
        END
        """
    )
    con.execute(
        """
        CREATE OR REPLACE TEMP MACRO "Or"(a, b) AS
        CASE
            WHEN NOT "__cql_bool_strict_valid"(a) OR NOT "__cql_bool_strict_valid"(b) THEN NULL
            ELSE "__cql_bool_strict"(a) OR "__cql_bool_strict"(b)
        END
        """
    )
    con.execute(
        """
        CREATE OR REPLACE TEMP MACRO "Not"(a) AS
        CASE
            WHEN NOT "__cql_bool_strict_valid"(a) THEN NULL
            ELSE NOT "__cql_bool_strict"(a)
        END
        """
    )

    # ============================================
    # Tier 2: SQL expressions
    # ============================================

    # Xor: true when exactly one operand is true
    con.execute(
        """
        CREATE OR REPLACE TEMP MACRO "Xor"(a, b) AS
        CASE
            WHEN NOT "__cql_bool_strict_valid"(a) OR NOT "__cql_bool_strict_valid"(b) THEN NULL
            ELSE ("__cql_bool_strict"(a) OR "__cql_bool_strict"(b))
                 AND NOT ("__cql_bool_strict"(a) AND "__cql_bool_strict"(b))
        END
        """
    )

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
        CREATE OR REPLACE TEMP MACRO "Implies"(a, b) AS
        CASE
            WHEN NOT "__cql_bool_strict_valid"(a) OR NOT "__cql_bool_strict_valid"(b) THEN NULL
            WHEN "__cql_bool_strict"(a) = false THEN true
            WHEN "__cql_bool_strict"(b) = true THEN true
            WHEN "__cql_bool_strict"(a) IS NULL OR "__cql_bool_strict"(b) IS NULL THEN NULL
            ELSE NOT "__cql_bool_strict"(a) OR "__cql_bool_strict"(b)
        END
    """)

    # Legacy public helper name used by translator/list helpers and the native
    # extension. Accept only Booleans, NULL, and exact Boolean text.
    con.execute("""
        CREATE OR REPLACE TEMP MACRO "logicalImplies"(a, b) AS
        CASE
            WHEN NOT "__cql_bool_text_valid"(a) OR NOT "__cql_bool_text_valid"(b) THEN NULL
            WHEN "__cql_bool_text"(a) = false THEN true
            WHEN "__cql_bool_text"(b) = true THEN true
            WHEN "__cql_bool_text"(a) IS NULL OR "__cql_bool_text"(b) IS NULL THEN NULL
            ELSE NOT "__cql_bool_text"(a) OR "__cql_bool_text"(b)
        END
    """)

    # Null handling helpers
    con.execute('CREATE MACRO IF NOT EXISTS "IsNull"(x) AS x IS NULL')
    con.execute('CREATE MACRO IF NOT EXISTS "IsNotNull"(x) AS x IS NOT NULL')
    con.execute('CREATE MACRO IF NOT EXISTS "IfNull"(a, b) AS COALESCE(a, b)')

    # CQL §22.16 IsTrue / §22.15 IsFalse
    # IsTrue returns true only if the argument is explicitly true (not null)
    # IsFalse returns true only if the argument is explicitly false (not null)
    con.execute("""
        CREATE OR REPLACE MACRO "IsTrue"(x) AS (
            (typeof(x) = 'BOOLEAN' AND COALESCE(x = true, false))
            OR (typeof(x) = 'VARIANT' AND COALESCE(x::JSON = true::JSON, false))
        )
    """)
    con.execute("""
        CREATE OR REPLACE MACRO "IsFalse"(x) AS (
            (typeof(x) = 'BOOLEAN' AND COALESCE(x = false, false))
            OR (typeof(x) = 'VARIANT' AND COALESCE(x::JSON = false::JSON, false))
        )
    """)


__all__ = ["registerLogicalMacros"]
