"""
DuckDB CQL Extension Registration

Three-tier execution model:
- Tier 1: Native SQL macros (zero Python overhead)
- Tier 2: SQL expressions (minimal overhead)
- Tier 3: Vectorized Arrow UDFs (batch processing)

A compiled C++ extension (`cql.duckdb_extension`) may be bundled inside
this wheel at build time.  When present, it is loaded automatically and
replaces the Python UDF tiers for maximum performance.
"""

from __future__ import annotations

import logging
import inspect
from pathlib import Path
from typing import TYPE_CHECKING

import duckdb

if TYPE_CHECKING:
    pass

_logger = logging.getLogger("duckdb_cql")

__all__ = ["register", "register_cql"]


_PYTHON_PREFERRED_CPP_CONFLICTS = {
    # These C++ functions are needed in WASM, but the Python UDFs remain the
    # native conformance authority until the C++ implementations close the full
    # CQL interval/time/boundary edge-case surface.
    "intervalStart",
    "intervalEnd",
    "intervalWidth",
    "intervalContains",
    "intervalProperlyContains",
    "intervalOverlaps",
    "intervalBefore",
    "intervalAfter",
    "intervalMeets",
    "intervalIncludes",
    "intervalIncludedIn",
    "intervalProperlyIncludes",
    "intervalProperlyIncludedIn",
    "intervalOverlapsBefore",
    "intervalOverlapsAfter",
    "intervalMeetsBefore",
    "intervalMeetsAfter",
    "intervalStartsSame",
    "intervalEndsSame",
    "intervalEquals",
    "intervalEquivalent",
    "intervalContainsPrecise",
    "intervalOverlapsPrecise",
    "intervalIncludesPrecise",
    "intervalIncludedInPrecise",
    "intervalBeforePrecise",
    "intervalAfterPrecise",
    "intervalOverlapsBeforePrecise",
    "intervalOverlapsAfterPrecise",
    "intervalFromBounds",
    "intervalIntersect",
    "intervalUnion",
    "intervalExcept",
    "intervalOnOrAfter",
    "intervalOnOrBefore",
    "pointFrom",
    "collapse_intervals",
    "quantityToInterval",
    "dateAddQuantity",
    "dateSubtractQuantity",
    "HighBoundary",
    "LowBoundary",
    "predecessorOf",
    "successorOf",
    "ToQuantity",
}


def _try_load_bundled_cpp_extension(con: "duckdb.DuckDBPyConnection") -> bool:
    """
    Try to load the compiled C++ CQL extension bundled inside this wheel.

    Returns True if loaded successfully, False otherwise.
    """
    # Version pre-flight: bundled binary is built for DuckDB 1.5.x
    _duckdb_version = duckdb.__version__
    if not _duckdb_version.startswith("1.5."):
        _logger.info(
            "duckdb_cql_py: skipping C++ extension (built for DuckDB 1.5.x, running %s). "
            "Falling back to Python UDFs.",
            _duckdb_version,
        )
        return False

    ext_path = Path(__file__).parent / "extensions" / "cql.duckdb_extension"
    if not ext_path.exists():
        return False
    try:
        escaped_path = str(ext_path).replace("'", "''")
        con.execute(f"LOAD '{escaped_path}'")
        _logger.debug("duckdb_cql_py: loaded bundled C++ extension from %s", ext_path)
        return True
    except duckdb.Error as exc:
        msg = str(exc).lower()
        if "already loaded" in msg:
            _logger.debug("duckdb_cql_py: C++ extension already loaded")
            return True
        if "unsigned" in msg or "signature" in msg:
            # Try enabling unsigned extensions and retrying
            try:
                con.execute("SET allow_unsigned_extensions = true")
                con.execute(f"LOAD '{escaped_path}'")
                _logger.debug("duckdb_cql_py: loaded unsigned C++ extension from %s", ext_path)
                return True
            except duckdb.Error:
                _logger.info(
                    "duckdb_cql_py: C++ extension found but not loaded (unsigned dev build). "
                    "Use duckdb.connect(config={'allow_unsigned_extensions': True}) to enable. "
                    "Falling back to Python UDFs."
                )
        else:
            _logger.warning("duckdb_cql_py: failed to load bundled C++ extension: %s", exc)
        return False
    except OSError as exc:
        _logger.debug("duckdb_cql_py: OS error loading C++ extension: %s", exc)
        return False


def _register_python_supplements(
    con: "duckdb.DuckDBPyConnection",
    *,
    cpp_loaded: bool = False,
    include_fhirpath: bool = True,
) -> None:
    """Register Python UDFs and SQL macros, skipping or shadowing C++ conflicts."""
    if include_fhirpath:
        from fhir4ds.fhirpath.duckdb.extension import register_fhirpath
        register_fhirpath(con)

    # When C++ is loaded, wrap the connection so create_function can skip
    # C++-owned names or shadow known conformance-sensitive conflicts.
    class _SafeConnection:
        """Proxy that wraps create_function to handle C++ conflicts."""
        def __init__(self, real_con):
            object.__setattr__(self, '_real', real_con)

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
            except duckdb.Error:
                return False

        def _parameter_count(self, fn, args, kwargs) -> int | None:
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
            except (duckdb.CatalogException, duckdb.InvalidInputException):
                _logger.debug("Skipping private Python UDF %s (already registered)", private_name)
            arity = self._parameter_count(args[0], args, kwargs)
            if arity is None:
                _logger.debug("Cannot shadow %s with Python macro: unknown arity", name)
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
                _logger.debug("Shadowing C++ UDF %s with Python fallback macro", name)
            except duckdb.Error as exc:
                _logger.warning("Failed to shadow C++ UDF %s with Python fallback: %s", name, exc)
            return None

        def create_function(self, name, *args, **kwargs):
            if self._function_exists(name):
                if name in _PYTHON_PREFERRED_CPP_CONFLICTS:
                    return self._register_python_shadow(name, *args, **kwargs)
                _logger.debug("Skipping Python UDF %s (C++ function already registered)", name)
                return None
            try:
                return self._real.create_function(name, *args, **kwargs)
            except (duckdb.CatalogException, duckdb.InvalidInputException):
                _logger.debug("Skipping Python UDF %s (C++ conflict)", name)
        def __getattr__(self, name):
            return getattr(self._real, name)

    reg_con = _SafeConnection(con) if cpp_loaded else con

    # Regex-backed string macros depend on these helper UDFs. Register them
    # before macro creation for Python fallback connections; native C++ builds
    # provide the same functions and the safe wrapper skips duplicate names.
    from .udf.string import registerRegexStringUdfs
    try:
        registerRegexStringUdfs(reg_con)
    except Exception as e:
        _logger.warning("Regex string UDF registration failed: %s", e)

    # SQL macros always register — they supplement both C++ and Python UDFs.
    from .macros import register_all_macros
    try:
        register_all_macros(con)
    except (
        duckdb.CatalogException,
        duckdb.InvalidInputException,
        duckdb.NotImplementedException,
        duckdb.BinderException,
    ):
        pass  # some macros may conflict with C++ functions; that's OK

    from .udf.age import registerAgeUdfs
    from .udf.aggregate import registerAggregateUdfs
    from .udf.clinical import registerClinicalUdfs
    from .udf.conversion import registerConversionCheckUdfs
    from .udf.datetime import registerDatetimeUdfs
    from .udf.interval import registerIntervalUdfs
    from .udf.valueset import registerValuesetUdfs
    from .udf.ratio import registerRatioUdfs
    from .udf.quantity import registerQuantityUdfs
    from .udf.list import registerListUdfs
    from .udf.variable import registerVariableUdfs
    from .udf.math import registerMathUdfs
    from .udf.string import registerStringUdfs
    from .udf.logical import registerLogicalUdfs

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
        except Exception as e:
            _logger.warning("UDF group '%s' registration failed: %s", label, e)

    if not cpp_loaded:
        # Register a placeholder in_valueset UDF that raises a clear error.
        def _in_valueset_placeholder(resource: str | None, path: str, valueset_url: str) -> bool:
            import duckdb as _duckdb
            raise _duckdb.InvalidInputException(
                f"in_valueset('{path}', '{valueset_url}') cannot execute: "
                "value set data has not been loaded into this connection. "
                "When using the DQM evaluator (MeasureEvaluator), value sets are loaded "
                "automatically. For standalone CQL queries, call "
                "fhir4ds.cql.duckdb.valueset.register_valueset_udfs(conn, cache) "
                "with a populated ValueSetCache before executing queries that use "
                "value set membership tests."
            )
        con.create_function("in_valueset", _in_valueset_placeholder, null_handling="special")


def register(con: "duckdb.DuckDBPyConnection", include_fhirpath: bool = True) -> None:
    """
    Register all CQL functions with a DuckDB connection.

    Attempts to load a bundled compiled C++ extension for maximum performance.
    Falls back to the three-tier Python UDF implementation when the C++ binary
    is not present.

    After calling this, all CQL functions are available in SQL:
        SELECT Abs(value), AgeInYears(resource) FROM table

    Args:
        con: A DuckDB connection object.
        include_fhirpath: If True (default), also register FHIRPath UDFs.
    """
    # Try the bundled C++ extension first (bundled at wheel-build time when available)
    cpp_loaded = _try_load_bundled_cpp_extension(con)
    if cpp_loaded:
        # C++ extension loaded — still register Python-only UDFs that the C++
        # extension doesn't provide (interval algebra, extended datetime, etc.)
        # and SQL macros that supplement both backends.
        _register_python_supplements(con, cpp_loaded=True, include_fhirpath=include_fhirpath)
        return

    # Idempotency guard: if CQL UDFs already exist, skip registration
    try:
        con.execute("SELECT AgeInYears(NULL)").fetchone()
        # If we get here, CQL UDFs are already registered; just ensure FHIRPath
        if include_fhirpath:
            from fhir4ds.fhirpath.duckdb.extension import register_fhirpath
            register_fhirpath(con)
        return
    except duckdb.Error:
        pass  # not yet registered, proceed

    _register_python_supplements(con, cpp_loaded=False, include_fhirpath=include_fhirpath)


def register_cql(con: "duckdb.DuckDBPyConnection", include_fhirpath: bool = True) -> None:
    """Alias for register() for backward compatibility."""
    register(con, include_fhirpath=include_fhirpath)
