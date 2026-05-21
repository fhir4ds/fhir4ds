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


def registerClinicalMacros(con: "duckdb.DuckDBPyConnection") -> None:
    """Register CQL clinical macros (resolve, etc.) on a DuckDB connection."""
    con.execute(_RESOLVE_MACRO_SQL)
