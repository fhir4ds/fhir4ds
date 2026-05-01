"""
viewdef - SQL-on-FHIR v2 ViewDefinition to SQL Generator

A Python library that converts SQL-on-FHIR v2 ViewDefinitions
to DuckDB SQL queries using the fhirpath() UDF.
"""

from .errors import (
    SQLOnFHIRError,
    ParseError,
    ValidationError,
    GenerationError,
    ConstantResolutionError,
)
from .types import (
    Column,
    Select,
    Constant,
    Join,
    ViewDefinition,
    JoinType,
    ColumnType,
)
from .parser import parse_view_definition, validate_view_definition
from .generator import SQLGenerator

__version__ = "0.0.3"

__all__ = [
    # Version
    "__version__",
    # Main API
    "parse_view_definition",
    "validate_view_definition",
    "SQLGenerator",
    # Types
    "Column",
    "Select",
    "Constant",
    "Join",
    "ViewDefinition",
    "JoinType",
    "ColumnType",
    # Errors
    "SQLOnFHIRError",
    "ParseError",
    "ValidationError",
    "GenerationError",
    "ConstantResolutionError",
]
