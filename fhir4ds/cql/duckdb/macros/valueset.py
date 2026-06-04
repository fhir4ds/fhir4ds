"""CQL terminology macros that are safe for no-Python runtimes."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import duckdb


_EXPAND_VALUESET_MACRO_SQL = """
CREATE OR REPLACE MACRO ExpandValueSet(vs) AS (
    CASE
      WHEN vs IS NULL THEN NULL
      ELSE (
        SELECT list(
            CAST(
              CASE
                WHEN display IS NULL THEN json_object('system', system, 'code', code)
                ELSE json_object('system', system, 'code', code, 'display', display)
              END
              AS VARCHAR
            )
        )
        FROM valueset_codes
        WHERE valueset_url = COALESCE(
            CASE
              WHEN json_extract_string(TRY_CAST(vs AS JSON), '$.id') IS NULL THEN NULL
              WHEN json_extract_string(TRY_CAST(vs AS JSON), '$.version') IS NULL
                THEN json_extract_string(TRY_CAST(vs AS JSON), '$.id')
              ELSE
                json_extract_string(TRY_CAST(vs AS JSON), '$.id')
                || '|'
                || json_extract_string(TRY_CAST(vs AS JSON), '$.version')
            END,
            CAST(vs AS VARCHAR)
        )
      )
    END
)
"""


def registerValuesetMacros(con: "duckdb.DuckDBPyConnection") -> None:
    """Register ValueSet macros and their backing table for SQL-only execution."""
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS valueset_codes (
            valueset_url VARCHAR,
            system VARCHAR,
            code VARCHAR,
            display VARCHAR
        )
        """
    )
    con.execute(_EXPAND_VALUESET_MACRO_SQL)
