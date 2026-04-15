"""
FHIRPath Exceptions — DuckDB adapter re-exports.

All error classes are canonically defined in fhir4ds.fhirpath.engine.errors.
This module re-exports them for backwards compatibility.
"""

from ..engine.errors import (  # noqa: F401
    FHIRPathError,
    FHIRPathSyntaxError,
    FHIRPathTypeError,
    FHIRPathNotFoundError,
    FHIRPathEvaluationError,
    FHIRPathFunctionError,
    FHIRPathResourceError,
    levenshtein_distance,
    suggest_field_name,
    format_suggestion,
)
