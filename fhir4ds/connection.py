"""
DuckDB connection factory for FHIR4DS.
"""

from __future__ import annotations

from typing import Any


def create_connection(
    database: str = ":memory:",
    *,
    allow_unsigned_extensions: bool = True,
    register_udfs: bool = True,
    valueset_cache: dict | None = None,
    **kwargs: Any,
) -> "duckdb.DuckDBPyConnection":
    """
    Create a DuckDB connection pre-configured for FHIR4DS.

    This is the recommended way to create a connection when using the bundled
    C++ extensions, which are unsigned in development builds and require
    ``allow_unsigned_extensions=True``.

    Parameters
    ----------
    database : str
        DuckDB database path or ``:memory:`` (default).
    allow_unsigned_extensions : bool
        Allow loading unsigned (dev-build) DuckDB extensions. Default True.
        Set to False in production if extensions are signed.
    register_udfs : bool
        Automatically call ``fhir4ds.register()`` to register all UDFs.
        Default True.
    valueset_cache : dict, optional
        Passed to ``register()`` for ``in_valueset`` ValueSet membership checks.
    **kwargs
        Additional keyword arguments forwarded to ``duckdb.connect(config=...)``.

    Returns
    -------
    duckdb.DuckDBPyConnection
        A connected DuckDB connection with FHIR4DS UDFs registered.

    Example
    -------
    >>> import fhir4ds
    >>> con = fhir4ds.create_connection()
    >>> con.execute("SELECT fhirpath('{\"id\":\"abc\"}', 'id')").fetchone()
    (['abc'],)
    """
    import duckdb

    config = {**kwargs, "allow_unsigned_extensions": allow_unsigned_extensions}
    con = duckdb.connect(database=database, config=config)

    if register_udfs:
        from .core import register
        register(con, valueset_cache=valueset_cache)

    return con
