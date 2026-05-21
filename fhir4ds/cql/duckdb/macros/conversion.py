"""
CQL Type Conversion functions as DuckDB SQL macros.

Tier 1 implementation - zero Python overhead.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import duckdb


def _create_private_function(con: "duckdb.DuckDBPyConnection", name: str, fn) -> None:
    """Register a private scalar helper, tolerating repeated extension setup."""
    try:
        con.create_function(name, fn, null_handling="special")
    except Exception:
        pass


def registerConversionMacros(con: "duckdb.DuckDBPyConnection") -> None:
    """
    Register type conversion macros (Tier 1).

    Registers native DuckDB SQL macros for CQL type conversion functions.
    All use CAST for zero Python overhead.
    """
    # String conversion
    con.execute("CREATE OR REPLACE MACRO ToString(x) AS CAST(x AS VARCHAR)")

    # Numeric conversions
    con.execute("""
        CREATE OR REPLACE MACRO ToInteger(x) AS
        CASE
            WHEN x IS NULL THEN NULL
            WHEN typeof(x) = 'BOOLEAN' THEN CASE WHEN TRY_CAST(x AS BOOLEAN) THEN 1 ELSE 0 END
            WHEN typeof(x) IN ('TINYINT', 'SMALLINT', 'INTEGER', 'BIGINT') THEN TRY_CAST(x AS INTEGER)
            WHEN typeof(x) = 'VARCHAR' AND regexp_full_match(CAST(x AS VARCHAR), '^[+-]?[0-9]+$') THEN TRY_CAST(x AS INTEGER)
            ELSE NULL
        END
    """)
    con.execute("""
        CREATE OR REPLACE MACRO ToDecimal(x) AS
        CASE
            WHEN x IS NULL THEN NULL
            WHEN typeof(x) = 'BOOLEAN' THEN CAST(CASE WHEN TRY_CAST(x AS BOOLEAN) THEN 1 ELSE 0 END AS DECIMAL(38, 8))
            WHEN typeof(x) IN ('TINYINT', 'SMALLINT', 'INTEGER', 'BIGINT', 'FLOAT', 'DOUBLE')
                OR starts_with(typeof(x), 'DECIMAL')
                THEN TRY_CAST(x AS DECIMAL(38, 8))
            WHEN typeof(x) = 'VARCHAR'
                AND regexp_full_match(CAST(x AS VARCHAR), '^[+-]?[0-9]+(\\.[0-9]{1,8})?$')
                AND TRY_CAST(x AS DECIMAL(38, 8)) IS NOT NULL
                THEN TRY_CAST(x AS DECIMAL(38, 8))
            ELSE NULL
        END
    """)

    # Boolean conversion
    con.execute("""
        CREATE OR REPLACE MACRO ToBoolean(x) AS
        CASE
            WHEN x IS NULL THEN NULL
            WHEN typeof(x) = 'BOOLEAN' THEN TRY_CAST(x AS BOOLEAN)
            WHEN (
                typeof(x) IN ('TINYINT', 'SMALLINT', 'INTEGER', 'BIGINT', 'FLOAT', 'DOUBLE')
                OR starts_with(typeof(x), 'DECIMAL')
            ) AND TRY_CAST(x AS DOUBLE) IN (0, 1) THEN TRY_CAST(x AS BOOLEAN)
            WHEN typeof(x) = 'VARCHAR'
                AND LOWER(CAST(x AS VARCHAR)) IN ('true', 'false', 't', 'f', 'yes', 'no', 'y', 'n', '1', '0')
                THEN TRY_CAST(x AS BOOLEAN)
            ELSE NULL
        END
    """)

    # Date/Time conversions use spec-aware helpers so partial precision,
    # timezone syntax, and invalid calendar values are not delegated to
    # DuckDB's more permissive casts.
    from ..udf.conversion import ToDate, ToDateTime, ToTime

    _create_private_function(con, "__cql_to_date", ToDate)
    _create_private_function(con, "__cql_to_datetime", ToDateTime)
    _create_private_function(con, "__cql_to_time", ToTime)
    con.execute('CREATE OR REPLACE MACRO ToDate(x) AS "__cql_to_date"(x)')
    con.execute('CREATE OR REPLACE MACRO ToDateTime(x) AS "__cql_to_datetime"(x)')
    con.execute('CREATE OR REPLACE MACRO ToTime(x) AS "__cql_to_time"(x)')

    # Quantity to string: CQL §22.31 — format as "<value> '<unit>'"
    con.execute(
        "CREATE OR REPLACE MACRO QuantityToString(q) AS "
        "CASE WHEN q IS NULL THEN NULL "
        "WHEN typeof(q) = 'VARCHAR' AND q LIKE '{%' THEN "
        "CAST(json_extract(q, '$.value') AS VARCHAR) || ' ''' || "
        "COALESCE(json_extract_string(q, '$.unit'), json_extract_string(q, '$.code'), '1') || '''' "
        "ELSE CAST(q AS VARCHAR) END"
    )


__all__ = ["registerConversionMacros"]
