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
    # When C++ is loaded, DuckDB silently ignores re-registration of functions
    # that already exist from C++. Only Python-exclusive functions (variable
    # state, string wrappers, expand, uncertain ops, etc.) will register.
    # When C++ is NOT loaded, all Python UDFs register normally.
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

    def _safe_register(register_fn, con, name=""):
        """Register UDFs, ignoring errors when C++ already provides them."""
        try:
            register_fn(con)
        except Exception as e:
            if cql_cpp:
                _logger.debug("Skipping Python UDF group %s (C++ provides): %s", name, e)
            else:
                raise

    _safe_register(registerAgeUdfs, con, "age")
    _safe_register(registerAggregateUdfs, con, "aggregate")
    _safe_register(registerClinicalUdfs, con, "clinical")
    _safe_register(registerDatetimeUdfs, con, "datetime")
    _safe_register(registerIntervalUdfs, con, "interval")
    _safe_register(registerValuesetUdfs, con, "valueset")
    _safe_register(registerRatioUdfs, con, "ratio")
    _safe_register(registerQuantityUdfs, con, "quantity")
    _safe_register(registerListUdfs, con, "list")
    _safe_register(registerVariableUdfs, con, "variable")
    _safe_register(registerMathUdfs, con, "math")
    _safe_register(registerStringUdfs, con, "string")
    _safe_register(registerLogicalUdfs, con, "logical")

    # Step 2b: Always register SQL macros — they supplement both C++ and Python UDFs
    # with functions like Truncate, IsTrue, IsFalse, Skip, Take, Tail, etc.
    from fhir4ds.cql.duckdb.macros import register_all_macros
    try:
        register_all_macros(con)
    except Exception:
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
