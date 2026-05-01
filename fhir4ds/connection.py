"""
DuckDB connection factory for FHIR4DS.
"""

from __future__ import annotations

from typing import Any, Optional


def create_connection(
    database: str = ":memory:",
    *,
    allow_unsigned_extensions: bool = True,
    register_udfs: bool = True,
    valueset_cache: dict | None = None,
    source: Optional[Any] = None,
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
    source : SourceAdapter, optional
        Optional :class:`~fhir4ds.sources.base.SourceAdapter` to mount as the
        ``resources`` view immediately after connection creation.  If ``None``,
        data must be loaded separately via
        :class:`~fhir4ds.cql.loader.FHIRDataLoader` or
        :func:`fhir4ds.attach`.
    **kwargs
        Additional keyword arguments forwarded to ``duckdb.connect(config=...)``.

    Returns
    -------
    duckdb.DuckDBPyConnection
        A connected DuckDB connection with FHIR4DS UDFs registered.

    Examples
    --------
    Zero-ETL with Parquet::

        import fhir4ds
        from fhir4ds.sources import FileSystemSource

        con = fhir4ds.create_connection(
            source=FileSystemSource('/data/fhir/**/*.parquet')
        )

    Traditional load::

        con = fhir4ds.create_connection()
        loader = FHIRDataLoader(con)
        loader.load_directory('/data/fhir/')

    Basic UDF usage::

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

    if source is not None:
        from .sources.base import SourceAdapter
        if not isinstance(source, SourceAdapter):
            raise TypeError(
                f"Expected a SourceAdapter, got {type(source).__name__}. "
                f"Ensure your adapter implements register() and unregister()."
            )
        source.register(con)

    return con

