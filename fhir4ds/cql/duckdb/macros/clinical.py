"""
CQL clinical function macros — resolve() and related reference-following functions.

These are implemented as DuckDB scalar subquery macros so they can reference
the ``resources`` table without requiring Python UDF overhead.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import duckdb

_RESOLVE_MACRO_SQL = """\
CREATE OR REPLACE MACRO resolve(ref) AS (
    WITH _ref AS (
        SELECT CASE
            WHEN ref IS NULL THEN NULL
            WHEN LTRIM(ref::VARCHAR) LIKE '{%' THEN json_extract_string(ref::VARCHAR, '$.reference')
            ELSE TRIM(BOTH '"' FROM ref::VARCHAR)
        END AS raw_ref
    )
    SELECT r.resource FROM resources r
    CROSS JOIN _ref
    WHERE ref IS NOT NULL
    AND raw_ref IS NOT NULL
    AND r.id = regexp_replace(split_part(raw_ref, '/', -1), '^urn:uuid:', '')
    AND (
        split_part(raw_ref, '/', -2) = ''
        OR r.resourceType = split_part(raw_ref, '/', -2)
    )
    LIMIT 1
)
"""

# CQL `is` type-check disambiguation macros.
#
# These encapsulate the inline ``CASE WHEN starts_with(LTRIM(value), '{') ...``
# blocks emitted by ``_translate_is_type_check`` (fhir4ds/cql/translator/
# expressions/_query.py) for ``is Interval<DateTime>``, ``is Interval<Quantity>``,
# ``is Period``, and ``is Range``. Emitting a macro call instead of the inline
# CASE keeps the SQL DRY: the disambiguation logic lives in one place, and the
# audit emission path (which copies expression fragments verbatim into
# ``__pre_...`` CTEs) can copy a ``cql_value_is_period(x)`` reference into any
# scope — the macro is globally resolvable, unlike the LATERAL-alias approach
# attempted in Option A/C which left dangling references.
#
# NULL semantics: ``starts_with(NULL, '{')`` returns NULL in DuckDB, which the
# CASE treats as not-TRUE → ELSE branch → FALSE. The macros preserve this.

_CQL_VALUE_IS_PERIOD_MACRO_SQL = (
    "CREATE OR REPLACE MACRO cql_value_is_period(value) AS "
    "CASE WHEN starts_with(LTRIM(value), '{') "
    "THEN json_extract_string(value, '$.start') IS NOT NULL "
    "OR json_extract_string(value, '$.end') IS NOT NULL "
    "ELSE FALSE END"
)

_CQL_VALUE_IS_RANGE_MACRO_SQL = (
    "CREATE OR REPLACE MACRO cql_value_is_range(value) AS "
    "CASE WHEN starts_with(LTRIM(value), '{') "
    "THEN json_extract_string(value, '$.low') IS NOT NULL "
    "OR json_extract_string(value, '$.high') IS NOT NULL "
    "ELSE FALSE END"
)

# Combined Period-or-Range shape used by CQL ``is Interval<DateTime>`` /
# ``is Interval<Quantity>`` disambiguation. A CQL interval value may be
# serialized as a FHIR Period (``$.start``/``$.end``) or as an internal
# interval JSON (``$.low``/``$.high``); the ``is Interval<...>`` check
# accepts either shape.
_CQL_VALUE_IS_INTERVAL_LIKE_MACRO_SQL = (
    "CREATE OR REPLACE MACRO cql_value_is_interval_like(value) AS "
    "CASE WHEN starts_with(LTRIM(value), '{') "
    "THEN json_extract_string(value, '$.start') IS NOT NULL "
    "OR json_extract_string(value, '$.end') IS NOT NULL "
    "OR json_extract_string(value, '$.low') IS NOT NULL "
    "OR json_extract_string(value, '$.high') IS NOT NULL "
    "ELSE FALSE END"
)

# Quantity ``$.value`` extraction macro.
#
# Used by arithmetic/comparison coercion (fhir4ds/cql/translator/expressions/
# _operators.py) to unwrap a Quantity JSON object (``{"value": 0.5, "unit":
# "mg/dL"}``) into its scalar value when the operand is a fhirpath_text /
# quantity-returning call. For non-JSON input the value is returned unchanged
# (bare numeric strings pass through to a downstream CAST). NULL propagates
# through both branches to NULL.
_CQL_QUANTITY_VALUE_MACRO_SQL = (
    "CREATE OR REPLACE MACRO cql_quantity_value(value) AS "
    "CASE WHEN starts_with(LTRIM(value), '{') "
    "THEN json_extract_string(value, '$.value') "
    "ELSE value END"
)


def registerClinicalMacros(con: "duckdb.DuckDBPyConnection") -> None:
    """Register CQL clinical macros (resolve, etc.) on a DuckDB connection.

    The ``resolve`` macro is a table-valued macro that references the
    ``resources`` table; its CREATE may fail on connections without that
    table (e.g. bare test connections). The disambiguation macros are
    scalar and always safe to register.
    """
    try:
        con.execute(_RESOLVE_MACRO_SQL)
    except Exception:
        # resolve() requires a `resources` table; skip on bare connections.
        pass
    con.execute(_CQL_VALUE_IS_PERIOD_MACRO_SQL)
    con.execute(_CQL_VALUE_IS_RANGE_MACRO_SQL)
    con.execute(_CQL_VALUE_IS_INTERVAL_LIKE_MACRO_SQL)
    con.execute(_CQL_QUANTITY_VALUE_MACRO_SQL)
