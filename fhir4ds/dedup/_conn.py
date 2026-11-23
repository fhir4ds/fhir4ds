"""INV-8 closed-connection wrap for public dedup entry points.

Mirrors the ``fhir4ds.register`` / ``evaluate_measure`` /
``FHIRDataLoader.load_resource`` wrap pattern (cql/AGENTS.md INV-8):
public entry points must raise an actionable, fhir4ds-namespaced
message instead of leaking the raw DuckDB
``Connection Error: Connection already closed!`` string.
"""

from __future__ import annotations

import duckdb


def require_open_connection(conn, action: str) -> None:
    """Fail fast with a typed, actionable error on a bad connection."""
    if conn is None:
        raise TypeError(f"Expected a DuckDB connection for 'conn', got None")
    if not isinstance(conn, duckdb.DuckDBPyConnection):
        raise TypeError(
            f"Expected a DuckDB connection for 'conn', got "
            f"{type(conn).__name__}")
    try:
        conn.execute("SELECT 1").fetchone()
    except duckdb.ConnectionException:
        raise duckdb.ConnectionException(
            f"Cannot {action}: DuckDB connection is closed") from None
    except duckdb.Error:
        pass  # connection is alive; other errors are expected
