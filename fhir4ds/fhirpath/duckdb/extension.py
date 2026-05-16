"""
DuckDB Extension Registration

Provides the register_fhirpath function to register the FHIRPath UDF
with a DuckDB connection.
"""

from __future__ import annotations

import logging
import orjson
import os
from typing import TYPE_CHECKING

import duckdb

if TYPE_CHECKING:
    pass


# Module-level logger for FHIRPath errors
_logger = logging.getLogger("duckdb_fhirpath")

# Global flag for debug logging (can be set via environment variable)
_DEBUG_LOGGING = os.environ.get("FHIRPATH_DEBUG", "").lower() in ("1", "true", "yes")

_STRICT_MODE = os.environ.get("FHIRPATH_STRICT_MODE") == "1"


def set_debug_logging(enabled: bool) -> None:
    """
    Enable or disable debug logging for FHIRPath evaluation errors.

    When enabled, errors during FHIRPath evaluation are logged at DEBUG level
    instead of being silently swallowed. This is useful for debugging while
    still maintaining FHIRPath's empty collection semantics.

    Args:
        enabled: True to enable debug logging, False to disable.

    Example:
        >>> from fhir4ds.fhirpath.duckdb.extension import set_debug_logging
        >>> set_debug_logging(True)  # Enable debug logging
    """
    global _DEBUG_LOGGING
    _DEBUG_LOGGING = enabled


def is_debug_logging() -> bool:
    """
    Check if debug logging is currently enabled.

    Returns:
        True if debug logging is enabled, False otherwise.
    """
    return _DEBUG_LOGGING


def _try_load_bundled_cpp_extension(con: "duckdb.DuckDBPyConnection") -> bool:
    """
    Try to load the compiled C++ FHIRPath extension bundled inside this wheel.

    The build hook (hatch_build.py) copies `fhirpath.duckdb_extension` into
    ``duckdb_fhirpath_py/extensions/`` at wheel-build time when the compiled
    binary is available.  At runtime this function checks for that file and
    loads it via DuckDB's native extension mechanism.

    Note: Development builds of the extension are unsigned. To load them,
    create your DuckDB connection with::

        con = duckdb.connect(config={"allow_unsigned_extensions": True})

    Production releases will be signed and load without this config.

    Returns True if the C++ extension was loaded, False otherwise.
    """
    # Version pre-flight: bundled binary is built for DuckDB 1.5.x
    _duckdb_version = duckdb.__version__
    if not _duckdb_version.startswith("1.5."):
        _logger.info(
            "duckdb_fhirpath_py: skipping C++ extension (built for DuckDB 1.5.x, running %s). "
            "Falling back to Python UDFs.",
            _duckdb_version,
        )
        return False

    from pathlib import Path
    ext_path = Path(__file__).parent / "extensions" / "fhirpath.duckdb_extension"
    if not ext_path.exists():
        return False
    try:
        escaped_path = str(ext_path).replace("'", "''")
        con.execute(f"LOAD '{escaped_path}'")
        _logger.debug("duckdb_fhirpath_py: loaded bundled C++ extension from %s", ext_path)
        return True
    except duckdb.Error as exc:
        msg = str(exc)
        if "already loaded" in msg.lower():
            _logger.debug("duckdb_fhirpath_py: C++ extension already loaded")
            return True
        if "unsigned" in msg or "signature" in msg:
            # Try enabling unsigned extensions and retrying
            try:
                con.execute("SET allow_unsigned_extensions = true")
                con.execute(f"LOAD '{escaped_path}'")
                _logger.debug("duckdb_fhirpath_py: loaded unsigned C++ extension from %s", ext_path)
                return True
            except duckdb.Error:
                _logger.info(
                    "duckdb_fhirpath_py: C++ extension found but not loaded (unsigned dev build). "
                    "Use duckdb.connect(config={'allow_unsigned_extensions': True}) to enable. "
                    "Falling back to Python UDFs."
                )
        else:
            _logger.warning("duckdb_fhirpath_py: failed to load bundled C++ extension: %s", exc)
        return False
    except OSError as exc:
        _logger.debug("duckdb_fhirpath_py: OS error loading C++ extension: %s", exc)
        return False


def _function_exists(con: "duckdb.DuckDBPyConnection", name: str) -> bool:
    """Return True when a function with *name* exists in the connection."""
    try:
        return con.execute(
            "SELECT COUNT(*) FROM duckdb_functions() WHERE lower(function_name) = lower(?)",
            [name],
        ).fetchone()[0] > 0
    except duckdb.Error:
        return False


def _is_cpp_extension_loaded(con: "duckdb.DuckDBPyConnection") -> bool:
    """Detect the bundled FHIRPath C++ extension without attempting to load it."""
    # fhirpath_predicate is registered by the C++ extension and not by the
    # Python fallback, making it a reliable signal for status reporting.
    return _function_exists(con, "fhirpath_predicate")


def register_fhirpath(con: duckdb.DuckDBPyConnection) -> bool:
    """
    Register the fhirpath UDF with a DuckDB connection.

    Attempts to load a bundled compiled C++ extension for maximum performance.
    Falls back to vectorised Python UDFs when the C++ binary is not present.

    This function registers a UDF that evaluates FHIRPath expressions
    against FHIR resources stored as JSON strings.

    Args:
        con: A DuckDB connection object.

    Returns:
        True when the bundled C++ extension is active, False when Python UDFs
        were registered or reused.

    Example:
        >>> import duckdb
        >>> from fhir4ds.fhirpath.duckdb import register_fhirpath
        >>> con = duckdb.connect()
        >>> register_fhirpath(con)
        >>> result = con.execute(
        ...     "SELECT fhirpath('{\"resourceType\":\"Patient\",\"id\":\"123\"}', 'id')"
        ... ).fetchone()
        >>> print(result)
        (['123'],)

    Note:
        The resource parameter accepts JSON strings representing FHIR resources.
        Returns a list of matching values following FHIRPath collection semantics.
    """
    if _is_cpp_extension_loaded(con):
        return True

    # Idempotency guard: if fhirpath UDF already exists, skip registration.
    try:
        con.execute("SELECT fhirpath(NULL, 'id')").fetchone()
        return _is_cpp_extension_loaded(con)
    except duckdb.Error:
        pass  # not yet registered, proceed

    cpp_conflicts = [
        name for name in (
            "fhirpath",
            "fhirpath_bool",
            "fhirpath_date",
            "fhirpath_json",
            "fhirpath_number",
            "fhirpath_quantity",
            "fhirpath_repeat",
            "fhirpath_text",
            "fhirpath_timestamp",
        )
        if _function_exists(con, name)
    ]

    # Try the bundled C++ extension first, unless a user-defined function would
    # make DuckDB's extension initialization fail with a catalog conflict.
    if cpp_conflicts:
        _logger.debug(
            "Skipping bundled FHIRPath C++ extension because functions already exist: %s",
            ", ".join(cpp_conflicts),
        )
    elif _try_load_bundled_cpp_extension(con):
        return True

    def _safe_create_function(name: str, function, *args, **kwargs) -> None:
        """Register a Python UDF unless the name already exists on this connection."""
        try:
            con.create_function(name, function, *args, **kwargs)
        except (
            duckdb.CatalogException,
            duckdb.InvalidInputException,
            duckdb.NotImplementedException,
        ) as exc:
            _logger.debug("Skipping FHIRPath UDF %s registration: %s", name, exc)

    # Register Tier 1 SQL macros first (zero Python overhead)
    from .macros import register_all_macros
    try:
        register_all_macros(con)
    except (
        duckdb.CatalogException,
        duckdb.InvalidInputException,
        duckdb.NotImplementedException,
        duckdb.BinderException,
    ) as exc:
        _logger.debug("Skipping FHIRPath SQL macro registration: %s", exc)

    from .evaluator import FHIRPathEvaluator
    from .udf import (
        fhirpath_scalar,
        fhirpath_is_valid_udf,
        _get_compiled_evaluator,
    )

    # Register the main fhirpath UDF (delegates to shared implementation in udf.py)
    _safe_create_function(
        "fhirpath",
        fhirpath_scalar,
        return_type="VARCHAR[]",
    )

    # Register validation function
    _safe_create_function(
        "fhirpath_is_valid",
        fhirpath_is_valid_udf,
    )

    # Import convenience UDFs
    from .udf import (
        fhirpath_bool_udf,
        fhirpath_date_udf,
        fhirpath_json_udf,
        fhirpath_number_udf,
        fhirpath_text_udf,
        fhirpath_timestamp_udf,
        fhirpath_quantity_udf,
    )

    # Register convenience UDFs with SPECIAL null handling
    # This allows the UDFs to return NULL values when appropriate
    # (e.g., when a FHIRPath doesn't match any values)
    _safe_create_function(
        "fhirpath_text",
        fhirpath_text_udf,
        null_handling="special",
    )

    _safe_create_function(
        "fhirpath_bool",
        fhirpath_bool_udf,
        null_handling="special",
    )

    _safe_create_function(
        "fhirpath_number",
        fhirpath_number_udf,
        null_handling="special",
    )

    _safe_create_function(
        "fhirpath_date",
        fhirpath_date_udf,
        null_handling="special",
    )

    _safe_create_function(
        "fhirpath_json",
        fhirpath_json_udf,
        null_handling="special",
    )

    _safe_create_function(
        "fhirpath_timestamp",
        fhirpath_timestamp_udf,
        null_handling="special",
    )

    _safe_create_function(
        "fhirpath_quantity",
        fhirpath_quantity_udf,
        null_handling="special",
    )

    # Register repeat traversal UDF for SQL-on-FHIR v2 ``repeat`` directive
    from .udf import fhirpath_repeat_udf
    _safe_create_function(
        "fhirpath_repeat",
        fhirpath_repeat_udf,
        return_type="VARCHAR[]",
        null_handling="special",
    )
    return False
