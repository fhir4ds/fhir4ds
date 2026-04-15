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
    if _try_load_bundled_cpp_extension(con):
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

    if include_fhirpath:
        from fhir4ds.fhirpath.duckdb.extension import register_fhirpath
        register_fhirpath(con)

    # Tier 1 & 2: Native SQL macros
    from .macros import register_all_macros
    register_all_macros(con)

    # Tier 3: Vectorized Arrow UDFs (with scalar fallback)
    from .udf.age import registerAgeUdfs
    from .udf.aggregate import registerAggregateUdfs
    from .udf.clinical import registerClinicalUdfs
    from .udf.datetime import registerDatetimeUdfs
    from .udf.interval import registerIntervalUdfs
    from .udf.valueset import registerValuesetUdfs, createValuesetMembershipUdf
    from .udf.ratio import registerRatioUdfs
    from .udf.quantity import registerQuantityUdfs
    from .udf.list import registerListUdfs
    from .udf.variable import registerVariableUdfs

    registerAgeUdfs(con)
    registerAggregateUdfs(con)
    registerClinicalUdfs(con)
    registerDatetimeUdfs(con)
    registerIntervalUdfs(con)
    registerValuesetUdfs(con)
    registerRatioUdfs(con)
    registerQuantityUdfs(con)
    registerListUdfs(con)
    registerVariableUdfs(con)  # Registers getvariable, setvariable

    # Register a placeholder in_valueset UDF that raises a clear error.
    # In production, call registerValuesetUdfs() with loaded valueset data
    # to replace this with a functioning implementation.
    def _in_valueset_placeholder(resource: str | None, path: str, valueset_url: str) -> bool:
        import duckdb as _duckdb
        raise _duckdb.InvalidInputException(
            "in_valueset requires valueset data to be loaded first. "
            "Call registerValuesetUdfs() with a populated valueset cache. See docs."
        )
    con.create_function("in_valueset", _in_valueset_placeholder, null_handling="special")

    # Legacy scalar UDFs (for backward compatibility)
    from .udf.math import registerMathUdfs
    from .udf.string import registerStringUdfs
    from .udf.logical import registerLogicalUdfs

    registerMathUdfs(con)    # Registers mathAbs, mathRound, etc.
    registerStringUdfs(con)  # Registers stringLength, etc.
    registerLogicalUdfs(con)


def register_cql(con: "duckdb.DuckDBPyConnection", include_fhirpath: bool = True) -> None:
    """Alias for register() for backward compatibility."""
    register(con, include_fhirpath=include_fhirpath)
