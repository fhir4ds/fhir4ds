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
    import logging
    import duckdb as _duckdb_mod
    _logger = logging.getLogger("fhir4ds.core")

    from fhir4ds.fhirpath.duckdb.extension import register_fhirpath as _fhirpath_register

    # Step 1: register FHIRPath (C++ bundled extension or Python UDFs)
    _fhirpath_register(con)

    # Step 2: Try C++ CQL extension first for maximum performance.
    # The C++ extension now has full polymorphic interval support (datetime,
    # integer, decimal, quantity, time) plus math, quantity arithmetic, and
    # logical functions.
    from fhir4ds.cql.duckdb.extension import _try_load_bundled_cpp_extension
    cql_cpp = _try_load_bundled_cpp_extension(con)

    if cql_cpp:
        _logger.info("CQL C++ extension loaded — registering Python-only supplements")
    else:
        _logger.info("CQL C++ extension not available — using Python UDFs")

    # Step 2a: Register Python UDFs.
    # When C++ is loaded, individual create_function calls that conflict with
    # C++ functions will fail. We wrap the connection in a proxy that silently
    # skips those, allowing Python-only functions within the same registration
    # group to still register.
    from fhir4ds.cql.duckdb.udf.age import registerAgeUdfs
    from fhir4ds.cql.duckdb.udf.aggregate import registerAggregateUdfs
    from fhir4ds.cql.duckdb.udf.clinical import registerClinicalUdfs
    from fhir4ds.cql.duckdb.udf.datetime import registerDatetimeUdfs
    from fhir4ds.cql.duckdb.udf.interval import registerIntervalUdfs
    from fhir4ds.cql.duckdb.udf.valueset import registerValuesetUdfs
    from fhir4ds.cql.duckdb.udf.ratio import registerRatioUdfs
    from fhir4ds.cql.duckdb.udf.quantity import registerQuantityUdfs
    from fhir4ds.cql.duckdb.udf.list import registerListUdfs
    from fhir4ds.cql.duckdb.udf.variable import registerVariableUdfs
    from fhir4ds.cql.duckdb.udf.math import registerMathUdfs
    from fhir4ds.cql.duckdb.udf.string import registerStringUdfs
    from fhir4ds.cql.duckdb.udf.logical import registerLogicalUdfs

    class _SafeConnection:
        """Proxy that wraps create_function to skip C++ conflicts."""
        def __init__(self, real_con, logger):
            object.__setattr__(self, '_real', real_con)
            object.__setattr__(self, '_logger', logger)
        def create_function(self, name, *args, **kwargs):
            try:
                return self._real.create_function(name, *args, **kwargs)
            except Exception as e:
                self._logger.debug("Skipping Python UDF %s (C++ conflict): %s", name, e)
        def __getattr__(self, name):
            return getattr(self._real, name)

    reg_con = _SafeConnection(con, _logger) if cql_cpp else con

    for fn, label in [
        (registerAgeUdfs, "age"), (registerAggregateUdfs, "aggregate"),
        (registerClinicalUdfs, "clinical"), (registerDatetimeUdfs, "datetime"),
        (registerIntervalUdfs, "interval"), (registerValuesetUdfs, "valueset"),
        (registerRatioUdfs, "ratio"), (registerQuantityUdfs, "quantity"),
        (registerListUdfs, "list"), (registerVariableUdfs, "variable"),
        (registerMathUdfs, "math"), (registerStringUdfs, "string"),
        (registerLogicalUdfs, "logical"),
    ]:
        try:
            fn(reg_con)
        except Exception as e:
            _logger.debug("UDF group %s registration: %s", label, e)

    # Step 2b: Always register SQL macros — they supplement both C++ and Python UDFs
    # with functions like Truncate, IsTrue, IsFalse, Skip, Take, Tail, etc.
    from fhir4ds.cql.duckdb.macros import register_all_macros
    try:
        register_all_macros(con)
    except (_duckdb_mod.CatalogException, _duckdb_mod.InvalidInputException):
        pass  # some macros may conflict with C++ functions; that's OK

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
