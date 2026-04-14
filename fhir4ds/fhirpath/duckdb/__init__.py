"""
DuckDB FHIRPath Extension

A DuckDB extension that enables FHIRPath queries directly in SQL,
allowing seamless querying of FHIR resources stored in DuckDB.

Example:
    import duckdb
    from .import register_fhirpath

    con = duckdb.connect()
    register_fhirpath(con)

    result = con.execute('''
        SELECT fhirpath(resource, 'Patient.name.given')
        FROM fhir_resources
        WHERE resourceType = 'Patient'
    ''').fetchall()
"""

__version__ = "0.1.0"
__author__ = "DuckDB FHIRPath Team"

from .extension import register_fhirpath, set_debug_logging, is_debug_logging
from .evaluator import FHIRPathEvaluator
from .types import Collection, Resource
from .errors import (
    FHIRPathError,
    FHIRPathTypeError,
    FHIRPathSyntaxError,
    FHIRPathEvaluationError,
    FHIRPathNotFoundError,
    FHIRPathFunctionError,
    FHIRPathResourceError,
    suggest_field_name,
    format_suggestion,
)

__all__ = [
    # Version
    "__version__",
    # Main API
    "register_fhirpath",
    # Debug logging
    "set_debug_logging",
    "is_debug_logging",
    # Core classes
    "FHIRPathEvaluator",
    "Collection",
    "Resource",
    # Exceptions
    "FHIRPathError",
    "FHIRPathTypeError",
    "FHIRPathSyntaxError",
    "FHIRPathEvaluationError",
    "FHIRPathNotFoundError",
    "FHIRPathFunctionError",
    "FHIRPathResourceError",
    # Suggestion utilities
    "suggest_field_name",
    "format_suggestion",
]
