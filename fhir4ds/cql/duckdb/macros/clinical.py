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
    SELECT r.resource FROM resources r
    WHERE ref IS NOT NULL
    AND r.id = split_part(
        CASE WHEN ref LIKE '{%' THEN json_extract_string(ref::VARCHAR, '$.reference') ELSE ref END,
        '/', -1
    )
    AND r.resourceType = split_part(
        CASE WHEN ref LIKE '{%' THEN json_extract_string(ref::VARCHAR, '$.reference') ELSE ref END,
        '/', 1
    )
    LIMIT 1
)
"""


def registerClinicalMacros(con: "duckdb.DuckDBPyConnection") -> None:
    """Register CQL clinical macros (resolve, etc.) on a DuckDB connection."""
    con.execute(_RESOLVE_MACRO_SQL)
