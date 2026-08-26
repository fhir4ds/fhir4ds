"""
CQL Type Conversion functions as DuckDB SQL macros.

Tier 1 implementation - zero Python overhead.
"""

import logging
from typing import TYPE_CHECKING

import duckdb


_logger = logging.getLogger(__name__)


def _create_private_function(con: "duckdb.DuckDBPyConnection", name: str, fn) -> None:
    """Register a private scalar helper, tolerating repeated extension setup."""
    try:
        con.create_function(name, fn, null_handling="special")
    except (duckdb.CatalogException, duckdb.InvalidInputException) as exc:
        _logger.debug("Skipping private conversion helper %s registration: %s", name, exc)


def registerConversionMacros(con: "duckdb.DuckDBPyConnection") -> None:
    """
    Register type conversion macros (Tier 1).

    Registers native DuckDB SQL macros for CQL type conversion functions.
    All use CAST for zero Python overhead.
    """
    # String conversion. CQL Appendix B defines String conversions for scalar
    # primitive/temporal/Quantity/Ratio values, not structural List/Tuple values.
    structural_type_guard = (
        "ends_with(typeof(x), '[]') "
        "OR starts_with(typeof(x), 'STRUCT') "
        "OR starts_with(typeof(x), 'MAP') "
        "OR typeof(x) = 'JSON'"
    )
    # CQL §ToString Table 9-G defines the Decimal string representation
    # format as (-)?#0.0# — at least one digit before AND after the decimal
    # point, with optional trailing digits. §ToString also states: "The
    # result of any ToString must be round-trippable back to the source
    # value." DuckDB's CAST(decimal AS VARCHAR) emits all declared scale
    # digits (e.g., DECIMAL(38,8) renders 0.1 as '0.10000000'), violating
    # both rules. Normalize DECIMAL inputs by trimming trailing zeros
    # while preserving at least one fractional digit (so 5.0 stays '5.0',
    # not '5'). Mirrors the trailing-zero trim already performed by
    # QuantityToString below.
    con.execute(f"""
        CREATE OR REPLACE MACRO ToString(x) AS
        CASE
            WHEN x IS NULL THEN NULL
            WHEN {structural_type_guard} THEN NULL
            WHEN starts_with(typeof(x), 'DECIMAL') THEN
                CASE
                    WHEN ends_with(
                        regexp_replace(CAST(x AS VARCHAR), '0+$', ''),
                        '.'
                    )
                    THEN regexp_replace(CAST(x AS VARCHAR), '0+$', '') || '0'
                    ELSE regexp_replace(CAST(x AS VARCHAR), '0+$', '')
                END
            WHEN typeof(x) = 'VARCHAR'
                AND regexp_full_match(
                    CAST(x AS VARCHAR),
                    '^T[0-9]{{2}}(:[0-9]{{2}}(:[0-9]{{2}}(\\.[0-9]{{1,3}})?)?)?(Z|[+-][0-9]{{2}}:[0-9]{{2}})?$'
                )
                THEN substr(CAST(x AS VARCHAR), 2)
            WHEN typeof(x) = 'VARCHAR'
                AND regexp_full_match(CAST(x AS VARCHAR), '^[0-9]{{4}}(-[0-9]{{2}}){{0,2}}T$')
                THEN regexp_replace(CAST(x AS VARCHAR), 'T$', '')
            ELSE CAST(x AS VARCHAR)
        END
    """)
    con.execute(f"""
        CREATE OR REPLACE MACRO ConvertsToString(x) AS
        CASE
            WHEN x IS NULL THEN NULL
            WHEN {structural_type_guard} THEN false
            ELSE true
        END
    """)

    # Numeric conversions
    con.execute("""
        CREATE OR REPLACE MACRO ToInteger(x) AS
        CASE
            WHEN x IS NULL THEN NULL
            WHEN typeof(x) = 'BOOLEAN' THEN CASE WHEN TRY_CAST(x AS BOOLEAN) THEN 1 ELSE 0 END
            WHEN typeof(x) IN ('TINYINT', 'SMALLINT', 'INTEGER', 'BIGINT') THEN TRY_CAST(x AS INTEGER)
            -- CQL 1.5 Appendix B Table 9-E defines NO Decimal->Integer
            -- conversion and ToInteger has no Decimal overload (only
            -- Boolean/String/Long), so a Decimal argument yields NULL.
            -- Truncation is the separate Truncate operator, not a conversion.
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
                AND regexp_full_match(CAST(x AS VARCHAR), '^[+-]?[0-9]+(\\.[0-9]+)?$')
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

    # Quantity to string: CQL 1.5 Appendix B §ToString (Table 9-G) — Quantity
    # format is (-)?#0.0# (('<unit>')|(<unit>)): UCUM units are rendered as a
    # quoted string literal, while calendar duration keywords are rendered as
    # a bare keyword ("ToString(4 days) results in `4 days`, i.e. not
    # `4 'd'`"). The keyword set is data-driven from the calendar-duration
    # registry in udf/quantity.py.
    from ..udf.quantity import _CQL_CALENDAR_DURATION_UNITS

    _calendar_units_sql = ", ".join(
        f"'{u}'" for u in sorted(_CQL_CALENDAR_DURATION_UNITS)
    )
    con.execute(
        "CREATE OR REPLACE MACRO QuantityToString(q) AS "
        "CASE WHEN q IS NULL THEN NULL "
        "WHEN starts_with(LTRIM(CAST(q AS VARCHAR)), '{') "
        "AND TRY_CAST(json_extract_string(CAST(q AS VARCHAR), '$.value') AS DECIMAL(38, 8)) IS NOT NULL THEN "
        "regexp_replace("
        "regexp_replace("
        "CAST(TRY_CAST(json_extract_string(CAST(q AS VARCHAR), '$.value') AS DECIMAL(38, 8)) AS VARCHAR), "
        "'0+$', ''), "
        "'\\.$', '') || "
        "CASE WHEN COALESCE("
        "json_extract_string(CAST(q AS VARCHAR), '$.unit'), "
        "json_extract_string(CAST(q AS VARCHAR), '$.code'), '1') "
        f"IN ({_calendar_units_sql}) "
        "THEN ' ' || COALESCE("
        "json_extract_string(CAST(q AS VARCHAR), '$.unit'), "
        "json_extract_string(CAST(q AS VARCHAR), '$.code'), '1') "
        "ELSE ' ''' || COALESCE("
        "json_extract_string(CAST(q AS VARCHAR), '$.unit'), "
        "json_extract_string(CAST(q AS VARCHAR), '$.code'), '1') || '''' END "
        "ELSE CAST(q AS VARCHAR) END"
    )


__all__ = ["registerConversionMacros"]
