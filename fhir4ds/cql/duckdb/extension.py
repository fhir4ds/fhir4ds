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
import os
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
    "collapse_intervals_per",
    "quantityToInterval",
    "dateAddQuantity",
    "dateSubtractQuantity",
    # S32 WASM parity: C++ mirrors exist for the browser runtime, but the
    # Python UDFs remain the desktop conformance authority.
    "ToLong",
    "ToRatio",
    "CanConvertQuantity",
    "ConvertsToBoolean",
    "ConvertsToDate",
    "ConvertsToDateTime",
    "ConvertsToDecimal",
    "ConvertsToInteger",
    "ConvertsToLong",
    "ConvertsToQuantity",
    "ConvertsToRatio",
    "ConvertsToString",
    "ConvertsToTime",
    # cqlDateTimeAdd delegates to the dateAddQuantity core; the C++ core
    # nulls sub-input-precision quantity units where the Python authority
    # truncates-and-returns, so Python stays the desktop conformance
    # authority for this name too (C++ remains the WASM fallback).
    "cqlDateTimeAdd",
    # ratioCompare equivalence routes through quantity_compare on divided
    # compound units (mg/mL vs g/mL); the C++ quantity layer cannot convert
    # metric prefixes inside compound units (CQL-03 HISTORIAN QA-004
    # deferred family), so Python stays the desktop authority.
    "ratioCompare",
    "HighBoundary",
    "LowBoundary",
    "predecessorOf",
    "successorOf",
    "ToQuantity",
}


def _bundled_extension_filename() -> str | None:
    """D2 dual-support: pick the bundled binary for the RUNNING DuckDB.

    Extensions are ABI-locked to the DuckDB ``major.minor`` they were
    built against (a 1.5 binary will not load in 2.0 and vice versa), so
    the wheel ships one binary per supported line and this selector maps
    the running version to the right file. Any UNSUPPORTED line (1.4,
    1.6, 2.1, dev builds of unreleased lines) returns None → the caller
    falls back to Python UDFs rather than attempting an ABI-mismatched
    LOAD (FEATURE_DUCKDB2_DUAL_SUPPORT §3.2).
    """
    import re

    m = re.match(r"^(\d+)\.(\d+)", duckdb.__version__ or "")
    if not m:
        return None
    key = (int(m.group(1)), int(m.group(2)))
    return {
        (1, 5): "cql.duckdb_extension",
        (2, 0): "cql.duckdb2_extension",
    }.get(key)


def _staged_load_path(ext_path: "Path") -> "Path":
    """DuckDB 2.x enforces the `.duckdb_extension` suffix at LOAD.

    The wheel bundles the 2.0 binary as `<name>.duckdb2_extension`
    (distinct suffix so a 1.5-only environment can never LOAD the 2.0
    binary by accident, per D2). DuckDB rejects loading files with any
    other suffix, so stage the bundle into a content-addressed cache
    under the loadable name before LOAD. The cache key is the bundle's
    size+mtime, so a wheel upgrade re-stages automatically.
    """
    import hashlib
    import tempfile
    from pathlib import Path

    stat = ext_path.stat()
    key = hashlib.sha1(f"{ext_path.name}:{stat.st_size}:{int(stat.st_mtime)}".encode()).hexdigest()[:16]
    # Per-bundle cache DIRECTORY (content-keyed) with the plain loadable
    # filename inside: DuckDB derives the extension entrypoint from the
    # file name, so it must stay `<name>.duckdb_extension`, while the
    # per-bundle directory ensures distinct bundles (unit-test fakes,
    # wheel upgrades) never share a mutable slot — the single-slot design
    # let a later stage overwrite the binary mid-use and segfault the loader.
    cache_dir = Path(tempfile.gettempdir()) / "fhir4ds-ext-cache" / key
    cache_dir.mkdir(parents=True, exist_ok=True)
    staged = cache_dir / ext_path.name.replace(".duckdb2_extension", ".duckdb_extension")
    if not staged.exists() or staged.stat().st_size != stat.st_size:
        staged.write_bytes(ext_path.read_bytes())
    return staged


def _try_load_bundled_cpp_extension(con: "duckdb.DuckDBPyConnection") -> bool:
    """
    Try to load the compiled C++ CQL extension bundled inside this wheel.

    Returns True if loaded successfully, False otherwise.
    """
    # D2 dual-support: select the binary for the RUNNING DuckDB line
    # (extensions are ABI-locked to major.minor). Unsupported lines and
    # missing bundles fall back to Python UDFs; strict mode (env
    # FHIR4DS_REQUIRE_CPP=1) turns the missing-bundle case into a loud
    # error for wheel installs that need the native engine.
    _duckdb_version = duckdb.__version__
    filename = _bundled_extension_filename()
    if filename is None:
        _logger.info(
            "duckdb_cql_py: no bundled C++ extension for DuckDB %s "
            "(supported build lines: 1.5, 2.0). Falling back to Python UDFs.",
            _duckdb_version,
        )
        return False

    ext_path = Path(__file__).parent / "extensions" / filename
    if not ext_path.exists():
        msg = (
            "fhir4ds C++ extension bundle mismatch: SUPPORTED RANGE "
            "DuckDB 1.5.x / 2.0.x, DETECTED DuckDB %s — this install does "
            "not bundle the %s binary for the detected version. The Python "
            "UDF fallback will be used. To get the native engine, install "
            "a fhir4ds build matching your DuckDB version (extras: "
            "fhir4ds-v2[duckdb1] for the 1.5.x line, fhir4ds-v2[duckdb2] "
            "for the 2.0.x line on Python >= 3.11), or set "
            "FHIR4DS_REQUIRE_CPP=1 to make this mismatch fatal."
        ) % (_duckdb_version, filename)
        if os.environ.get("FHIR4DS_REQUIRE_CPP") == "1":
            raise RuntimeError(msg)
        _logger.warning("duckdb_cql_py: %s", msg)
        return False

    # duckdb 2.x Python client requires pytz for TIMESTAMPTZ rendering.
    if _duckdb_version.startswith("2."):
        try:
            import pytz  # noqa: F401
        except ImportError:
            _logger.warning(
                "duckdb_cql_py: DuckDB %s detected but pytz is not installed — "
                "TIMESTAMPTZ rendering will fail on direct timestamp "
                "columns. Fix: pip install fhir4ds-v2[duckdb2] (or pytz).",
                _duckdb_version,
            )
    # DuckDB 2.x enforces the `.duckdb_extension` suffix at LOAD: stage
    # the bundled `.duckdb2_extension` binary into the loadable name first.
    if ext_path.name.endswith(".duckdb2_extension"):
        try:
            ext_path = _staged_load_path(ext_path)
        except OSError as exc:
            _logger.warning("duckdb_py: failed to stage 2.0 bundle for load: %s", exc)
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
                ).fetchall()
                # DuckDB 2.0: parameterized results stay open after
                # fetchone(), blocking create_function (ResourceInUse).
                # Fully DRAINING the result closes it (1.5-equivalent).
                return bool(row)
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
        # Register a placeholder in_valueset UDF for the no-valueset-data case.
        # CQL-02 HISTORIAN QA-003: the native C++ in_valueset returns SQL NULL
        # when the valueset_codes table has no data for the URL (membership
        # unknown). The Python fallback previously RAISED InvalidInputException
        # through DuckDB, breaking parity and row-level resilience. Return NULL
        # with a warn-once log so standalone usage still surfaces guidance
        # without aborting the query.
        _warned: list[bool] = []

        def _in_valueset_placeholder(resource: str | None, path: str, valueset_url: str) -> bool | None:
            if not _warned:
                _warned.append(True)
                _logger.warning(
                    "in_valueset('%s', '%s') has no value set data loaded on this "
                    "connection; returning NULL (membership unknown). When using "
                    "the DQM evaluator (MeasureEvaluator), value sets are loaded "
                    "automatically. For standalone CQL queries, call "
                    "fhir4ds.cql.duckdb.valueset.register_valueset_udfs(conn, cache) "
                    "with a populated ValueSetCache before executing queries that "
                    "use value set membership tests.",
                    path,
                    valueset_url,
                )
            return None
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
