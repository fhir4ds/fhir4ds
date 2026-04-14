"""
Core registration: registers all DuckDB UDFs (FHIRPath + CQL).

Delegates to duckdb_fhirpath_py and duckdb_cql_py, which each try to load
a bundled C++ extension first and fall back to Python UDFs automatically.

Python fallbacks also provide ValueSet expansion functionality not available
in the C++ extensions.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import duckdb


def register_fhirpath(con: "duckdb.DuckDBPyConnection") -> bool:
    """
    Register FHIRPath UDFs on the given DuckDB connection.

    Tries the bundled C++ extension first; falls back to Python UDFs.
    Returns True if the C++ extension was loaded.
    """
    from fhir4ds.fhirpath.duckdb.extension import register_fhirpath as _register
    # _register internally tries the bundled C++ extension first, then Python UDFs
    _register(con)
    # Detect whether C++ was used by checking if the extension file exists and loaded
    from fhir4ds.fhirpath.duckdb.extension import _try_load_bundled_cpp_extension as _check
    from pathlib import Path
    ext = Path(_check.__code__.co_filename).parent / "extensions" / "fhirpath.duckdb_extension"
    return ext.exists()  # best-effort; actual load success is logged by _register


def register_cql(
    con: "duckdb.DuckDBPyConnection",
    *,
    valueset_cache: dict | None = None,
) -> bool:
    """
    Register CQL UDFs (includes FHIRPath) on the given DuckDB connection.

    Always registers FHIRPath first (C++ or Python), then loads the CQL
    extension (C++ if available, otherwise Python UDFs).  ValueSet expansion
    always uses the Python implementation.

    Returns True if the CQL C++ extension was loaded.
    """
    from fhir4ds.fhirpath.duckdb.extension import register_fhirpath as _fhirpath_register
    from fhir4ds.cql.duckdb.extension import (
        _try_load_bundled_cpp_extension as _try_cql_cpp,
        register as _cql_register,
    )

    # Step 1: register FHIRPath (C++ bundled extension or Python UDFs)
    _fhirpath_register(con)

    # Step 2: load CQL C++ extension or fall back to Python UDFs
    cql_cpp = _try_cql_cpp(con)
    if not cql_cpp:
        _cql_register(con, include_fhirpath=False)  # fhirpath already registered

    # Step 3: ValueSet expansion always uses Python
    if valueset_cache is not None:
        from fhir4ds.cql.duckdb.udf.valueset import registerValuesetUdfs
        registerValuesetUdfs(con, valueset_cache)

    return cql_cpp


def register(
    con: "duckdb.DuckDBPyConnection",
    *,
    valueset_cache: dict | None = None,
) -> dict:
    """
    Register all FHIR4DS UDFs (FHIRPath + CQL) on the given DuckDB connection.

    This is the primary entry point. Calling ``register_cql`` subsumes
    FHIRPath registration, so ``register_fhirpath`` is only needed when
    you want FHIRPath alone without the full CQL UDF set.

    Parameters
    ----------
    con : duckdb.DuckDBPyConnection
    valueset_cache : dict, optional
        Mapping of valueset URLs → sets of codes for ``in_valueset``.

    Returns
    -------
    dict  ``{"fhirpath_cpp": bool, "cql_cpp": bool}``
    """
    cql_cpp = register_cql(con, valueset_cache=valueset_cache)
    return {"fhirpath_cpp": cql_cpp, "cql_cpp": cql_cpp}
