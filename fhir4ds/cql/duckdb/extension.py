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
from pathlib import Path
from typing import TYPE_CHECKING

import duckdb

if TYPE_CHECKING:
    pass

_logger = logging.getLogger("duckdb_cql")

__all__ = ["register", "register_cql"]


def _try_load_bundled_cpp_extension(con: "duckdb.DuckDBPyConnection") -> bool:
    """
    Try to load the compiled C++ CQL extension bundled inside this wheel.

    Returns True if loaded successfully, False otherwise.
    """
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
    """Register Python UDFs and SQL macros, skipping C++ conflicts when present."""
    if include_fhirpath:
        from fhir4ds.fhirpath.duckdb.extension import register_fhirpath
        register_fhirpath(con)

    # SQL macros always register — they supplement both C++ and Python UDFs
    from .macros import register_all_macros
    try:
        register_all_macros(con)
    except Exception:
        pass  # some macros may conflict with C++ functions; that's OK

    # When C++ is loaded, wrap the connection so create_function silently
    # skips any name that conflicts with an already-registered C++ function.
    class _SafeConnection:
        """Proxy that wraps create_function to skip C++ conflicts."""
        def __init__(self, real_con):
            object.__setattr__(self, '_real', real_con)
        def create_function(self, name, *args, **kwargs):
            try:
                return self._real.create_function(name, *args, **kwargs)
            except Exception:
                _logger.debug("Skipping Python UDF %s (C++ conflict)", name)
        def __getattr__(self, name):
            return getattr(self._real, name)

    reg_con = _SafeConnection(con) if cpp_loaded else con

    from .udf.age import registerAgeUdfs
    from .udf.aggregate import registerAggregateUdfs
    from .udf.clinical import registerClinicalUdfs
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

    if not cpp_loaded:
        # Register a placeholder in_valueset UDF that raises a clear error.
        def _in_valueset_placeholder(resource: str | None, path: str, valueset_url: str) -> bool:
            import duckdb as _duckdb
            raise _duckdb.InvalidInputException(
                "in_valueset requires valueset data to be loaded first. "
                "Call registerValuesetUdfs() with a populated valueset cache. See docs."
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
