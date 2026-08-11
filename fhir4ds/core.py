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


def _register_valueset_cache(con: "duckdb.DuckDBPyConnection", valueset_cache: dict) -> None:
    """Register cache-backed ValueSet membership functions for standalone use."""
    from fhir4ds.cql.duckdb.udf.valueset import createValuesetMembershipUdf

    udf_func = createValuesetMembershipUdf(valueset_cache)

    # Use an internal function name and public macros. This lets a caller-provided
    # cache override the placeholder Python UDF or native C++ function without
    # relying on DuckDB's remove_function behavior.
    try:
        con.remove_function("_fhir4ds_in_valueset_cache")
    except Exception:
        pass

    con.create_function(
        "_fhir4ds_in_valueset_cache",
        udf_func,
        null_handling="special",
    )
    con.execute(
        "CREATE OR REPLACE MACRO in_valueset(res, path, vs_url) AS "
        "_fhir4ds_in_valueset_cache(res, path, vs_url)"
    )
    con.execute(
        "CREATE OR REPLACE MACRO fhirpath_in_valueset(res, path, vs_url) AS "
        "_fhir4ds_in_valueset_cache(res, path, vs_url)"
    )


def _ensure_valueset_membership_surface(con: "duckdb.DuckDBPyConnection") -> None:
    """Ensure generated CQL can call in_valueset even before valuesets load."""
    import duckdb as _duckdb_mod

    try:
        con.execute("SELECT in_valueset(NULL, 'code', 'http://example.org/ValueSet/empty')").fetchone()
        return
    except _duckdb_mod.CatalogException:
        _register_valueset_cache(con, {})


def register_fhirpath(con: "duckdb.DuckDBPyConnection") -> bool:
    """
    Register FHIRPath UDFs on the given DuckDB connection.

    Tries the bundled C++ extension first; falls back to Python UDFs.
    Returns True if the C++ extension was loaded, False if Python fallback is used.
    """
    import duckdb as _duckdb_mod
    if not isinstance(con, _duckdb_mod.DuckDBPyConnection):
        raise TypeError(
            f"Expected a DuckDB connection for 'con', got {type(con).__name__}"
        )
    from fhir4ds.fhirpath.duckdb.extension import register_fhirpath as _register
    return bool(_register(con))


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

    if not isinstance(con, _duckdb_mod.DuckDBPyConnection):
        raise TypeError(
            f"Expected a DuckDB connection for 'con', got {type(con).__name__}"
        )

    from fhir4ds.fhirpath.duckdb.extension import register_fhirpath as _fhirpath_register

    # Step 1: register FHIRPath (C++ bundled extension or Python UDFs)
    _fhirpath_register(con)

    # Step 2: Try C++ CQL extension first for browser-required native functions.
    # Known conformance-sensitive interval/time/boundary conflicts are shadowed
    # back to Python below when running through the Python registration surface.
    from fhir4ds.cql.duckdb.extension import (
        _PYTHON_PREFERRED_CPP_CONFLICTS,
        _try_load_bundled_cpp_extension,
    )
    cql_cpp = _try_load_bundled_cpp_extension(con)

    if cql_cpp:
        _logger.info("CQL C++ extension loaded — registering Python-only supplements")
    else:
        _logger.info("CQL C++ extension not available — using Python UDFs")

    # Step 2a: Register Python UDFs.
    # When C++ is loaded, individual create_function calls that conflict with
    # C++ functions will fail. We wrap the connection in a proxy that silently
    # skips those, allowing Python-only functions within the same registration
    # group to still register. Known C++ functions that remain less complete
    # than Python are shadowed by temporary macros that call private Python UDFs.
    from fhir4ds.cql.duckdb.udf.age import registerAgeUdfs
    from fhir4ds.cql.duckdb.udf.aggregate import registerAggregateUdfs
    from fhir4ds.cql.duckdb.udf.clinical import registerClinicalUdfs
    from fhir4ds.cql.duckdb.udf.conversion import registerConversionCheckUdfs
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
        """Proxy that wraps create_function to skip conflicts and duplicates."""
        def __init__(self, real_con, logger):
            object.__setattr__(self, '_real', real_con)
            object.__setattr__(self, '_logger', logger)

        def _function_exists(self, name: str) -> bool:
            try:
                row = self._real.execute(
                    """
                    SELECT 1
                    FROM duckdb_functions()
                    WHERE lower(function_name) = lower(?)
                    LIMIT 1
                    """,
                    [name],
                ).fetchone()
                return row is not None
            except _duckdb_mod.Error:
                return False

        def _parameter_count(self, fn, args, kwargs) -> int | None:
            import inspect
            parameters = kwargs.get("parameters")
            if parameters is None and len(args) >= 2:
                parameters = args[1]
            if isinstance(parameters, (list, tuple)):
                return len(parameters)
            try:
                signature = inspect.signature(fn)
            except (TypeError, ValueError):
                return None
            count = 0
            for param in signature.parameters.values():
                if param.kind in (param.POSITIONAL_ONLY, param.POSITIONAL_OR_KEYWORD):
                    count += 1
                elif param.kind is param.VAR_POSITIONAL:
                    return None
            return count

        def _register_python_shadow(self, name, *args, **kwargs):
            if not args or not callable(args[0]):
                return None
            private_name = f"__fhir4ds_py_{name}"
            try:
                self._real.create_function(private_name, *args, **kwargs)
            except (_duckdb_mod.CatalogException, _duckdb_mod.InvalidInputException):
                self._logger.debug("Skipping private Python UDF %s (already registered)", private_name)
            arity = self._parameter_count(args[0], args, kwargs)
            if arity is None:
                self._logger.debug("Cannot shadow %s with Python macro: unknown arity", name)
                return None
            params = ", ".join(f"arg{i}" for i in range(arity))
            call_args = ", ".join(f"arg{i}" for i in range(arity))
            quoted_name = name.replace('"', '""')
            quoted_private = private_name.replace('"', '""')
            try:
                self._real.execute(
                    f'CREATE OR REPLACE TEMP MACRO "{quoted_name}"({params}) '
                    f'AS "{quoted_private}"({call_args})'
                )
                self._logger.debug("Shadowing C++ UDF %s with Python fallback macro", name)
            except _duckdb_mod.Error as exc:
                self._logger.warning("Failed to shadow C++ UDF %s with Python fallback: %s", name, exc)
            return None

        def create_function(self, name, *args, **kwargs):
            if cql_cpp and self._function_exists(name):
                if name in _PYTHON_PREFERRED_CPP_CONFLICTS:
                    return self._register_python_shadow(name, *args, **kwargs)
                self._logger.debug("Skipping UDF %s (already registered by C++)", name)
                return None
            try:
                return self._real.create_function(name, *args, **kwargs)
            except (_duckdb_mod.CatalogException, _duckdb_mod.InvalidInputException,
                    _duckdb_mod.NotImplementedException) as e:
                self._logger.debug("Skipping UDF %s (already registered or conflict): %s", name, e)
        def __getattr__(self, name):
            return getattr(self._real, name)

    # Always use _SafeConnection for idempotent registration
    reg_con = _SafeConnection(con, _logger)

    for fn, label in [
        (registerAgeUdfs, "age"), (registerAggregateUdfs, "aggregate"),
        (registerClinicalUdfs, "clinical"), (registerConversionCheckUdfs, "conversion"),
        (registerDatetimeUdfs, "datetime"),
        (registerIntervalUdfs, "interval"), (registerValuesetUdfs, "valueset"),
        (registerRatioUdfs, "ratio"), (registerQuantityUdfs, "quantity"),
        (registerListUdfs, "list"), (registerVariableUdfs, "variable"),
        (registerMathUdfs, "math"), (registerStringUdfs, "string"),
        (registerLogicalUdfs, "logical"),
    ]:
        try:
            fn(reg_con)
        except (_duckdb_mod.CatalogException, _duckdb_mod.InvalidInputException,
                _duckdb_mod.NotImplementedException) as e:
            _logger.debug("UDF group %s registration: %s", label, e)

    # Step 2b: Always register SQL macros — they supplement both C++ and Python UDFs
    # with functions like Truncate, IsTrue, IsFalse, Skip, Take, Tail, etc.
    from fhir4ds.cql.duckdb.macros import register_all_macros
    try:
        register_all_macros(con)
    except (_duckdb_mod.CatalogException, _duckdb_mod.InvalidInputException,
            _duckdb_mod.NotImplementedException, _duckdb_mod.BinderException):
        pass  # macros may already exist; that's OK

    # Step 3: ValueSet expansion always uses Python
    if valueset_cache is not None:
        _register_valueset_cache(con, valueset_cache)
    else:
        _ensure_valueset_membership_surface(con)

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

    This function is idempotent — calling it multiple times on the same
    connection is safe and will skip already-registered UDFs.

    Parameters
    ----------
    con : duckdb.DuckDBPyConnection
    valueset_cache : dict, optional
        Mapping of valueset URLs → sets of codes for ``in_valueset``.

    Returns
    -------
    dict  ``{"fhirpath_cpp": bool, "cql_cpp": bool}``

    Raises
    ------
    TypeError
        If *con* is not a DuckDB connection.
    duckdb.ConnectionException
        If the connection is closed (mirrors the ``evaluate_measure``
        wrap pattern so callers get an actionable, fhir4ds-typed
        message instead of the raw DuckDB string).
    """
    if con is None:
        raise TypeError(
            "Expected a DuckDB connection for 'con', got None"
        )
    import duckdb as _duckdb_mod
    if not isinstance(con, _duckdb_mod.DuckDBPyConnection):
        raise TypeError(
            f"Expected a DuckDB connection for 'con', got {type(con).__name__}"
        )
    try:
        con.execute("SELECT 1").fetchone()
    except _duckdb_mod.ConnectionException:
        raise _duckdb_mod.ConnectionException(
            "Cannot register fhir4ds UDFs: DuckDB connection is closed"
        ) from None
    except _duckdb_mod.Error:
        pass  # connection is alive, other DuckDB errors are expected
    cql_cpp = register_cql(con, valueset_cache=valueset_cache)
    from fhir4ds.fhirpath.duckdb.extension import _is_cpp_extension_loaded
    fhirpath_cpp = _is_cpp_extension_loaded(con)
    return {"fhirpath_cpp": fhirpath_cpp, "cql_cpp": cql_cpp}
