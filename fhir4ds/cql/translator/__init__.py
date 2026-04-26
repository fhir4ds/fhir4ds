"""
CQL to SQL Translator.

This module provides a clean implementation of CQL to SQL translation
using DuckDB FHIRPath UDFs. The translator uses a population-first approach
where all queries return one row per patient.

Main Entry Points:
    - CQLToSQLTranslator: Full-featured translator class
    - translate_cql(): Convenience function for quick translation
    - translate_library(): Translate a parsed library
    - translate_library_to_sql(): Generate complete SQL with CTEs

Architecture:
    The translator generates SQL that:
    1. Creates a 'patients' CTE with all distinct patient IDs
    2. Creates CTEs for each CQL definition that include patient_id
    3. Produces a final SELECT with LEFT JOINs for boolean definitions

Example:
    # High-level usage
    from ..translator import translate_cql

    cql = '''
    library Example version '1.0'
    define "Active": [Patient] P where P.active = true
    '''
    results = translate_cql(cql)
    for name, expr in results.items():
        print(f"{name}: {expr.to_sql()}")

    # Low-level usage
    from ..parser import parse_cql
    from ..translator import CQLToSQLTranslator

    library = parse_cql(cql)
    translator = CQLToSQLTranslator()
    sql = translator.translate_library_to_population_sql(
        library,
        output_columns={"active": "Active"}
    )
"""

from ..translator.context import (
    LibraryInfo,
    ParameterInfo,
    SQLTranslationContext,
    Scope,
    SymbolInfo,
)
from ..translator.library_resolver import (
    LibraryResolver,
    ResolvedFunction,
    ResolvedExpressionDef,
    LibraryInfo as ResolverLibraryInfo,
)
from ..translator.expressions import (
    BINARY_OPERATOR_MAP,
    ExpressionTranslator,
    UNARY_OPERATOR_MAP,
)
from ..translator.translator import (
    CQLToSQLTranslator,
    FunctionInfo,
    MeasurementPeriod,
    ParameterBinding,
    PatientContext,
)
from ..translator.function_inliner import (
    FunctionDef,
    FunctionInliner,
    ParameterPlaceholder,
    TranslationError,
)
from ..translator.types import (
    CTEDefinition,
    PRECEDENCE,
    SQLArray,
    SQLBinaryOp,
    SQLCase,
    SQLCast,
    SQLExists,
    SQLExpression,
    SQLExpressionType,
    SQLFragment,
    SQLFunctionCall,
    SQLIdentifier,
    SQLInterval,
    SQLLiteral,
    SQLNull,
    SQLParameterRef,
    SQLQualifiedIdentifier,
    SQLSelect,
    SQLSubquery,
    SQLUnaryOp,
)
from ..translator.operators import OperatorTranslator
from ..translator.functions import FunctionTranslator
from ..translator.queries import QueryTranslator
from ..translator.terminology import TerminologyTranslator, CodeLiteral
from ..translator.fluent_functions import (
    FluentFunctionTranslator,
    FluentFunctionRegistry,
    FunctionDefinition,
    FunctionParameter,
    RawSQLExpression,
)

# Backward compatibility aliases
CQLTranslator = CQLToSQLTranslator
TranslationContext = SQLTranslationContext

# TranslationResult is a simple dataclass for backward compatibility
from dataclasses import dataclass
from typing import Any, Dict, Optional, Set, TYPE_CHECKING

if TYPE_CHECKING:
    from ..parser.ast_nodes import Library


@dataclass
class TranslationResult:
    """Backward compatibility class for V1 translator results."""
    fhirpath: str
    resource_type: Optional[str] = None
    terminology: Optional[Any] = None
    is_singular: bool = False
    dependencies: Set[str] = None

    def __post_init__(self):
        if self.dependencies is None:
            self.dependencies = set()


# Convenience functions for common use cases

def translate_cql(cql_text: str, connection: Optional[Any] = None) -> Dict[str, "SQLExpression"]:
    """
    Translate CQL text to SQL expressions.

    This is a convenience function that parses CQL text and translates
    all definitions to SQL expressions.

    Args:
        cql_text: The CQL library text to translate.
        connection: Optional DuckDB connection for direct execution.

    Returns:
        Dictionary mapping definition names to SQL expressions.

    Example:
        from ..translator import translate_cql

        cql = '''
        library Example version '1.0'
        define "Active Patients": [Patient] P where P.active = true
        '''
        results = translate_cql(cql)
        print(results["Active Patients"].to_sql())
    """
    if not isinstance(cql_text, str) or not cql_text.strip():
        raise ValueError("cql_text must be a non-empty string")

    from ..parser import parse_cql

    library = parse_cql(cql_text)
    translator = CQLToSQLTranslator(connection=connection)
    return translator.translate_library(library)


def translate_library(library: "Library", connection: Optional[Any] = None) -> Dict[str, "SQLExpression"]:
    """
    Translate a parsed CQL library to SQL expressions.

    This is a convenience function that takes an already-parsed library
    and translates all definitions to SQL expressions.

    Args:
        library: The parsed CQL library AST from parse_cql().
        connection: Optional DuckDB connection for direct execution.

    Returns:
        Dictionary mapping definition names to SQL expressions.

    Example:
        from ..parser import parse_cql
        from ..translator import translate_library

        library = parse_cql(cql_text)
        results = translate_library(library)
    """
    translator = CQLToSQLTranslator(connection=connection)
    return translator.translate_library(library)


def translate_library_to_sql(
    library: "Library",
    final_definition: Optional[str] = None,
    connection: Optional[Any] = None
) -> str:
    """
    Translate a parsed CQL library to a complete SQL statement.

    This is a convenience function that generates a complete SQL query
    with CTEs for all definitions.

    Args:
        library: The parsed CQL library AST from parse_cql().
        final_definition: Optional name of the final definition to SELECT from.
                         If None, uses "Initial Population" or the last definition.
        connection: Optional DuckDB connection for direct execution.

    Returns:
        Complete SQL string with WITH clause and CTEs.

    Example:
        from ..parser import parse_cql
        from ..translator import translate_library_to_sql

        library = parse_cql(cql_text)
        sql = translate_library_to_sql(library, final_definition="Numerator")
        print(sql)
    """
    translator = CQLToSQLTranslator(connection=connection)
    return translator.translate_library_to_sql(library, final_definition)


__all__ = [
    # Main translator
    "CQLToSQLTranslator",
    # Convenience functions
    "translate_cql",
    "translate_library",
    "translate_library_to_sql",
    # Backward compatibility
    "CQLTranslator",
    "TranslationContext",
    "TranslationResult",
    # Context
    "SQLTranslationContext",
    "SymbolInfo",
    "Scope",
    "ParameterInfo",
    "LibraryInfo",
    "FunctionInfo",
    "PatientContext",
    "MeasurementPeriod",
    "ParameterBinding",
    # Operators
    "OperatorTranslator",
    # Functions
    "FunctionTranslator",
    # Queries
    "QueryTranslator",
    # Terminology
    "TerminologyTranslator",
    "CodeLiteral",
    # Function inlining
    "FunctionInliner",
    "FunctionDef",
    "ParameterPlaceholder",
    "TranslationError",
    # Fluent functions
    "FluentFunctionTranslator",
    "FluentFunctionRegistry",
    "FunctionDefinition",
    "FunctionParameter",
    "RawSQLExpression",
    # Library resolver
    "LibraryResolver",
    "ResolvedFunction",
    "ResolvedExpressionDef",
    "ResolverLibraryInfo",
    # Types
    "PRECEDENCE",
    "SQLExpression",
    "SQLLiteral",
    "SQLIdentifier",
    "SQLQualifiedIdentifier",
    "SQLNull",
    "SQLParameterRef",
    "SQLBinaryOp",
    "SQLUnaryOp",
    "SQLFunctionCall",
    "SQLCase",
    "SQLArray",
    "SQLInterval",
    "SQLCast",
    "SQLSelect",
    "SQLSubquery",
    "SQLExists",
    "CTEDefinition",
    "SQLFragment",
    "SQLExpressionType",
]
