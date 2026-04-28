"""
cql - CQL to SQL translator for DuckDB.

This package provides tools for translating Clinical Quality Language (CQL)
queries into SQL that can be executed in DuckDB using FHIRPath UDFs.

Main entry points:
    - register_udfs(): Register FHIRPath + CQL UDFs (C++ extensions preferred)
    - evaluate_measure(): High-level API for population-first measure evaluation
    - CQLToSQLTranslator: Low-level translator for fine-grained control

Example:
    import duckdb
    from .import register_udfs, evaluate_measure

    conn = duckdb.connect(config={'allow_unsigned_extensions': 'true'})
    register_udfs(conn)  # loads C++ extensions if built, else Python UDFs

    result = evaluate_measure(
        library_path="./measures/CMS165.cql",
        conn=conn,
        output_columns={
            "initial_population": "Initial Population",
            "denominator": "Denominator",
            "numerator": "Numerator",
        },
        parameters={
            "Measurement Period": (datetime(2026, 1, 1), datetime(2026, 12, 31))
        },
    )
"""

from __future__ import annotations

import duckdb as _duckdb_mod
import logging
from datetime import date, datetime, time
from pathlib import Path
from typing import Any, Dict, List, Optional, Union, TYPE_CHECKING

from .paths import get_resource_path

_logger = logging.getLogger(__name__)

__version__ = "0.0.2"


def parse_cql(cql_text: str):
    """Parse CQL text into a library AST.

    Args:
        cql_text: CQL source code string.

    Returns:
        Parsed CQL library object.
    """
    from .parser import parse_cql as _parse_cql
    return _parse_cql(cql_text)


def register_udfs(
    conn,
    use_cpp_extensions=True,
):
    """
    Register FHIRPath and CQL UDFs on a DuckDB connection.

    Attempts to load high-performance C++ extensions (fhirpath + cql) first,
    falling back to Python UDFs if binaries are not found or load fails.

    Args:
        conn: DuckDB connection (``duckdb.DuckDBPyConnection``).
        use_cpp_extensions: When ``True`` (default), prefer C++ extensions.

    Returns:
        ``True`` if CQL C++ extension was loaded, ``False`` if Python UDFs were
        used instead.
    """
    # Check if CQL UDFs are already registered (not just fhirpath).
    try:
        conn.execute("SELECT AgeInYears(NULL)").fetchone()
        return None  # CQL UDFs already registered
    except _duckdb_mod.Error:
        pass

    if use_cpp_extensions:
        from fhir4ds.core import register_cql
        try:
            return register_cql(conn)
        except (ImportError, OSError, _duckdb_mod.Error) as e:
            _logger.warning("Failed to load C++ extensions via register_cql: %s", e)

    # Fallback to pure-Python UDFs (registers both fhirpath + CQL)
    from fhir4ds.cql.duckdb import register as _register_cql
    _register_cql(conn)
    return False

# Dependency resolution
from .dependency import (
    DependencyResolver,
    ResolutionError,
    DependencyCache,
    DependencyType,
    ResolvedLibrary,
    ResolvedValueSet,
    ResolvedCodeSystem,
    ResolvedMeasure,
    ResolutionContext,
)

# FHIR data loading
from .loader import FHIRDataLoader

# Evaluation contexts
from .evaluator import EvaluationContext, PatientContext, PopulationContext


def _validate_parameters(library, parameters: Dict[str, Any]) -> None:
    """Validate runtime parameter values against CQL parameter declarations.

    Raises TypeError for clear type mismatches (e.g., a string where an
    Interval is expected).
    """
    from .parser.ast_nodes import ParameterDefinition

    param_defs: Dict[str, "ParameterDefinition"] = {}
    for stmt in getattr(library, "parameters", []):
        if isinstance(stmt, ParameterDefinition):
            param_defs[stmt.name] = stmt

    for name, value in parameters.items():
        pdef = param_defs.get(name)
        if pdef is None:
            continue
        type_spec = pdef.type
        if type_spec is None or value is None:
            continue
        type_name = getattr(type_spec, "name", None) or ""
        type_str = str(type_spec).lower()

        if "interval" in type_str:
            if isinstance(value, str):
                raise TypeError(
                    f"Parameter '{name}' is declared as {type_spec} but received "
                    f"a plain string '{value}'. Interval parameters must be passed "
                    f"as a dict {{'start': ..., 'end': ...}} or a tuple (start, end)."
                )
            if isinstance(value, dict):
                if "start" not in value or "end" not in value:
                    raise TypeError(
                        f"Parameter '{name}' is declared as {type_spec}. "
                        f"Dict must contain both 'start' and 'end' keys, "
                        f"got: {sorted(value.keys())}"
                    )
        elif type_name.lower() in ("integer", "int"):
            if not isinstance(value, (int, bool)):
                raise TypeError(
                    f"Parameter '{name}' is declared as {type_spec} but received "
                    f"{type(value).__name__}: {value!r}"
                )
        elif type_name.lower() == "decimal":
            if not isinstance(value, (int, float)):
                raise TypeError(
                    f"Parameter '{name}' is declared as {type_spec} but received "
                    f"{type(value).__name__}: {value!r}"
                )


def _build_parameterized_query(
    sql_template: str,
    parameters: Dict[str, Any]
) -> tuple[str, List[Any]]:
    """
    Build a parameterized query with positional placeholders.

    Converts named parameters ($param_name or :param_name) to positional
    placeholders ($1, $2, etc.) for DuckDB's native parameter binding.

    Args:
        sql_template: SQL template with named parameters.
        parameters: Dictionary of parameter name to value.

    Returns:
        Tuple of (sql_with_placeholders, parameter_values).
    """
    import re

    param_values: List[Any] = []
    param_counter = [1]  # Use list for mutable closure

    def replace_param(match: re.Match) -> str:
        param_name = match.group(1)
        if param_name in parameters:
            param_values.append(parameters[param_name])
            placeholder = f"${param_counter[0]}"
            param_counter[0] += 1
            return placeholder
        return match.group(0)

    # Replace $param_name or :param_name with $1, $2, etc.
    sql_with_placeholders = re.sub(r'[$:]([a-zA-Z_][a-zA-Z0-9_]*)', replace_param, sql_template)

    return sql_with_placeholders, param_values


def _python_value_to_sql(value: Any) -> Any:
    """
    Convert a Python value to a SQL-compatible value for DuckDB.

    DuckDB natively handles:
    - None -> NULL
    - bool -> BOOLEAN
    - int -> INTEGER
    - float -> DOUBLE
    - str -> VARCHAR
    - datetime.datetime -> TIMESTAMP
    - datetime.date -> DATE
    - datetime.time -> TIME
    - list -> LIST
    - dict -> STRUCT/JSON

    Args:
        value: Python value to convert.

    Returns:
        Value suitable for DuckDB parameter binding.
    """
    if value is None:
        return None
    elif isinstance(value, (bool, int, float, str)):
        return value
    elif isinstance(value, datetime):
        return value
    elif isinstance(value, date):
        return value
    elif isinstance(value, time):
        return value
    elif isinstance(value, (list, tuple)):
        return [_python_value_to_sql(v) for v in value]
    elif isinstance(value, dict):
        return {k: _python_value_to_sql(v) for k, v in value.items()}
    else:
        # For other types, convert to string
        return str(value)


def evaluate_measure(
    library_path: str,
    conn: "duckdb.DuckDBPyConnection",
    output_columns: Optional[Dict[str, str]] = None,
    parameters: Optional[Dict[str, Any]] = None,
    patient_ids: Optional[List[str]] = None,
    verbose: bool = False,
    include_paths: Optional[List[str]] = None,
    audit_mode: str = "none",
) -> Any:
    """
    Evaluate a CQL measure against all patients in a single query.

    This is the main entry point for population-first measure evaluation.
    It generates a single SQL query that returns one row per patient with
    the specified output columns.

    Args:
        library_path: Path to the CQL library file (.cql).
        conn: DuckDB connection with FHIR data loaded in 'resources' table.
        output_columns: Mapping of column name to CQL definition name.
                       {"column_name": "CQL definition name"}
                       If None, includes all definitions.
                       If empty dict {}, returns patient_id only.
        parameters: Runtime parameter values as {"param_name": python_value}.
                   These override default values from CQL parameter definitions.
        patient_ids: Optional list of patient IDs to filter.
                    If None, derives from resources table.
                    If empty list [], returns empty result.
        verbose: If True, print generated SQL.
        include_paths: Optional list of paths to directories containing included CQL libraries.
                      Used to resolve include statements in the main library.
        audit_mode: Controls audit granularity: "none" (default), "population",
                   or "full". Currently accepted for API compatibility; audit
                   functionality is handled by the DQM layer.

    Returns:
        DuckDB relation with one row per patient and columns per output_columns.

    Raises:
        ValueError: If a required parameter is missing and has no default.
        FileNotFoundError: If library_path does not exist.

    Edge Cases:
        - patient_ids=None: Derive all patients from resources.patient_ref
        - patient_ids=[]: Return empty result (no patients)
        - output_columns=None: Include all CQL definitions as output columns
        - output_columns={}: Return only patient_id column
        - parameters=None: Use default values from CQL parameter definitions

    Example:
        import duckdb
        from .import evaluate_measure

        conn = duckdb.connect()
        # Load FHIR data into resources table...

        result = evaluate_measure(
            library_path="./measures/CMS165.cql",
            conn=conn,
            output_columns={
                "initial_population": "Initial Population",
                "denominator": "Denominator",
                "numerator": "Numerator",
            },
            parameters={
                "Measurement Period": (datetime(2026, 1, 1), datetime(2026, 12, 31))
            },
            patient_ids=["patient-1", "patient-2"],
        )
        df = result.df()  # Convert to pandas DataFrame
    """
    import duckdb

    # Import parser and translator
    from .parser import parse_cql
    from .translator import CQLToSQLTranslator

    # Validate connection
    if conn is None:
        raise TypeError(
            "Expected a DuckDB connection for 'conn', got None"
        )
    try:
        conn.execute("SELECT 1").fetchone()
    except _duckdb_mod.ConnectionException:
        raise _duckdb_mod.ConnectionException(
            "Cannot evaluate measure: DuckDB connection is closed"
        ) from None
    except _duckdb_mod.Error:
        pass  # connection is alive, other DuckDB errors are expected

    # Validate library_path
    if not library_path:
        raise ValueError("library_path must be a non-empty path to a CQL library file")

    # Handle empty patient_ids early
    if patient_ids is not None and len(patient_ids) == 0:
        # Return empty result with correct schema
        # This is a placeholder that returns no rows
        return conn.execute("SELECT NULL AS patient_id WHERE FALSE").fetchdf()

    # Load and parse CQL library
    lib_path = Path(library_path)
    if not lib_path.exists():
        raise FileNotFoundError(f"CQL library not found: {library_path}")
    if not lib_path.is_file():
        raise ValueError(f"library_path must be a file, not a directory: {library_path}")

    cql_text = lib_path.read_text()
    library = parse_cql(cql_text)

    # Validate runtime parameter types against CQL declarations
    if parameters:
        _validate_parameters(library, parameters)

    # Create translator — translate_library_to_population_sql() handles the full
    # three-phase optimization pipeline internally.  Do NOT call translate_library()
    # first: it pollutes mutable translator state (column registries, component-code
    # maps) that causes Phase 2 of the population SQL builder to emit retrieve CTEs
    # without the precomputed property columns that property-filter WHERE clauses need.
    translator = CQLToSQLTranslator(connection=conn)

    # Set up library loader if include_paths provided
    if include_paths:
        def library_loader(alias: str):
            """Load an included library by alias from include_paths."""
            for path in include_paths:
                # Try to find the library file
                lib_file = Path(path) / f"{alias}.cql"
                if lib_file.exists():
                    try:
                        lib_text = lib_file.read_text()
                        return parse_cql(lib_text)
                    except (OSError, ValueError, SyntaxError) as e:
                        _logger.warning("Failed to parse library file '%s': %s", lib_file, e)
            return None

        translator.set_library_loader(library_loader)

    # Build population SQL — this method handles empty-definition and
    # output_columns logic internally, so no pre-translation is needed.
    # Pass output_columns as-is: None → include all definitions, {} → patient_id only.
    sql = translator.translate_library_to_population_sql(
        library=library,
        output_columns=output_columns,
        parameters=parameters or {},
        patient_ids=patient_ids,
    )

    if verbose:
        print(f"-- Generated SQL --\n{sql}\n-- End SQL --")

    # Execute with parameters if any
    try:
        if parameters:
            sql, param_values = _build_parameterized_query(sql, parameters)
            result = conn.execute(sql, param_values)
        else:
            result = conn.execute(sql)
        return result.fetchdf()
    except _duckdb_mod.CatalogException as exc:
        if "resources" in str(exc).lower():
            raise ValueError(
                "No FHIR data loaded. The generated SQL references the 'resources' "
                "table which does not exist. Load data first with "
                "FHIRDataLoader(conn).load_resource() or load_directory()."
            ) from exc
        raise


def evaluate_measure_legacy(
    cql_source: Union[str, Path],
    data_paths: List[Path],
    dependencies: Optional[List[Path]] = None,
    connection=None,
    verbose: bool = False,
) -> "pandas.DataFrame":
    """
    Legacy high-level API: Evaluate a CQL measure against FHIR data.

    DEPRECATED: This function uses the legacy translator and is no longer
    recommended. Use evaluate_measure() which provides population-first
    evaluation with better performance.

    Args:
        cql_source: CQL library text or path to .cql file.
        data_paths: Paths to FHIR data (JSON, NDJSON, bundles).
        dependencies: Paths to dependent CQL libraries and ValueSet resources.
        connection: Optional existing DuckDB connection.
        verbose: If True, print generated SQL.

    Returns:
        DataFrame with one row per patient, one column per define.

    Example:
        df = evaluate_measure_legacy(
            cql_source="./measures/DiabetesCare.cql",
            data_paths=["./fhir-data"],
            dependencies=["./cql-libraries", "./valuesets"],
        )
    """
    import warnings
    warnings.warn(
        "evaluate_measure_legacy is deprecated. Use evaluate_measure() instead.",
        DeprecationWarning,
        stacklevel=2
    )

    # Import here to avoid circular imports
    from .parser import parse_cql
    from .translator import CQLToSQLTranslator

    # Create connection if not provided
    if connection is None:
        connection = _duckdb_mod.connect(":memory:")

    # Auto-register CQL UDFs (prefer C++ extensions, fall back to Python)
    register_udfs(connection)

    # Set up resolver
    resolver = DependencyResolver(paths=dependencies) if dependencies else None

    # Load CQL
    if isinstance(cql_source, Path) or (isinstance(cql_source, str) and cql_source.endswith(".cql")):
        cql_text = Path(cql_source).read_text()
        library_path = Path(cql_source)
    else:
        cql_text = cql_source
        library_path = None

    # Parse CQL
    library = parse_cql(cql_text)

    # Load data
    loader = FHIRDataLoader(connection)
    for path in data_paths:
        p = Path(path)
        if p.is_file():
            if p.suffix == ".ndjson":
                loader.load_ndjson(p)
            else:
                loader.load_file(p)
        elif p.is_dir():
            loader.load_directory(p)

    # Load valuesets into database
    if resolver:
        context = resolver.build_context(
            library.identifier if hasattr(library, 'identifier') else cql_text.split('\n')[0]
        )
        valuesets = list(context.valuesets.values())
        if valuesets:
            loader.load_valuesets(valuesets)

    # Translate using the new translator
    translator = CQLToSQLTranslator(connection=connection)
    sql = translator.translate_library_to_population_sql(
        library=library,
        output_columns=None,  # Include all definitions
        parameters={},
        patient_ids=None,
    )

    if verbose:
        print(f"-- Generated SQL --\n{sql}\n-- End SQL --")

    return connection.execute(sql).df()


def load_resources_from_directory(
    conn: "duckdb.DuckDBPyConnection",
    directory: Union[str, Path],
    recursive: bool = True,
    table_name: str = "resources",
) -> int:
    """
    Load FHIR resources from a directory into DuckDB.

    This is a convenience function that creates a FHIRDataLoader and
    loads all supported files (JSON, NDJSON) from a directory.

    Args:
        conn: DuckDB connection.
        directory: Path to directory containing FHIR data files.
        recursive: If True, search subdirectories recursively.
        table_name: Name of the table to create/populate (default: "resources").

    Returns:
        Total number of resources loaded.

    Example:
        import duckdb
        from .import load_resources_from_directory

        conn = duckdb.connect()
        count = load_resources_from_directory(conn, "./fhir-data")
        print(f"Loaded {count} resources")
    """
    loader = FHIRDataLoader(conn, table_name=table_name, create_table=True)
    return loader.load_directory(Path(directory), recursive=recursive)


def load_resources_from_ndjson(
    conn: "duckdb.DuckDBPyConnection",
    ndjson_path: Union[str, Path],
    table_name: str = "resources",
) -> int:
    """
    Load FHIR resources from an NDJSON file into DuckDB.

    This is a convenience function that creates a FHIRDataLoader and
    loads resources from a newline-delimited JSON file.

    Args:
        conn: DuckDB connection.
        ndjson_path: Path to the NDJSON file.
        table_name: Name of the table to create/populate (default: "resources").

    Returns:
        Number of resources loaded.

    Example:
        import duckdb
        from .import load_resources_from_ndjson

        conn = duckdb.connect()
        count = load_resources_from_ndjson(conn, "./patients.ndjson")
        print(f"Loaded {count} resources")
    """
    loader = FHIRDataLoader(conn, table_name=table_name, create_table=True)
    return loader.load_ndjson(Path(ndjson_path))


# Translator API (main entry point for CQL translation)
from .translator import (
    CQLToSQLTranslator,
    translate_cql,
    translate_library,
    translate_library_to_sql,
)

__all__ = [
    "__version__",
    # UDF registration
    "register_udfs",
    # Parser API
    "parse_cql",
    # Translator API (main public API)
    "CQLToSQLTranslator",
    "translate_cql",
    "translate_library",
    "translate_library_to_sql",
    # High-level evaluation API
    "evaluate_measure",
    "evaluate_measure_legacy",
    # FHIR data loading
    "FHIRDataLoader",
    "load_resources_from_directory",
    "load_resources_from_ndjson",
    # Dependency resolution
    "DependencyResolver",
    "ResolutionError",
    "DependencyCache",
    "DependencyType",
    "ResolvedLibrary",
    "ResolvedValueSet",
    "ResolvedCodeSystem",
    "ResolvedMeasure",
    "ResolutionContext",
    # SQL generation
    "SQLGenerator",
    "FHIRPathResult",
    "LibraryResult",
    "CTEBuilder",
    "PopulationSQLBuilder",
    "PopulationSQLConfig",
    # Evaluation contexts
    "EvaluationContext",
    "PatientContext",
    "PopulationContext",
]
