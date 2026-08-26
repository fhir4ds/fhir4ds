"""
sqlquery - SQL-on-FHIR v2 Analytics Layer (SQLQuery / SQLView)

Implementation of the spec's Library profiles that wrap raw DuckDB SQL
around materialized ViewDefinition tables. Per the spec's Analytics
Layer, a SQLQuery resource carries:

  * ``content[].data`` — base64-encoded raw SQL the author wrote
  * ``relatedArtifact[]`` — references to ViewDefinitions (and other
    SQLViews) that the runner materializes as DuckDB views, with the
    relatedArtifact ``label`` serving as the table alias used inside the
    raw SQL
  * ``parameter[]`` — named parameters bound via DuckDB prepared
    statements with FHIR-type-to-SQL-type coercion (SQLView forbids
    parameters)

Threat model: the raw SQL body is author-controlled (injection-by-author
is not a threat model the runner defends against); the parameter values
are caller-controlled and are bound exclusively through DuckDB prepared
statements — no string interpolation.

Identifiers (relatedArtifact labels, parameter names) are validated
against the SQL-on-FHIR ``sql-name`` invariant and quoted via
:func:`fhir4ds.viewdef.utils.quote_identifier` before being used as
DuckDB identifiers.
"""

from .errors import (
    SQLError,
    SQLQueryParseError,
    SQLQueryValidationError,
    SQLQueryCycleError,
    SQLQueryMaterializationError,
    SQLQueryTypeError,
    UnsupportedDialectError,
)
from .types import (
    SQLQuery,
    SQLView,
    SQLContent,
    SQLParameter,
    SQLRelatedArtifact,
    SQLQUERY_PROFILE_CANONICAL,
    SQLVIEW_PROFILE_CANONICAL,
    SQLQUERY_PROFILE_CANONICALS,
    SQLVIEW_PROFILE_CANONICALS,
    SQLQUERY_LIBRARY_TYPE_CODE,
    SQLVIEW_LIBRARY_TYPE_CODE,
    SUPPORTED_CONTENT_TYPES,
)
from .parser import parse_library, parse_sqlquery, parse_sqlview
from .validator import validate_sql_library, select_best_content
from .runner import SQLQueryRunner, DependencyResolver

__version__ = "0.0.13"

__all__ = [
    # Version
    "__version__",
    # Parse / validate / execute
    "parse_library",
    "parse_sqlquery",
    "parse_sqlview",
    "validate_sql_library",
    "select_best_content",
    "SQLQueryRunner",
    "DependencyResolver",
    # Types
    "SQLQuery",
    "SQLView",
    "SQLContent",
    "SQLParameter",
    "SQLRelatedArtifact",
    "SQLQUERY_PROFILE_CANONICAL",
    "SQLVIEW_PROFILE_CANONICAL",
    "SQLQUERY_PROFILE_CANONICALS",
    "SQLVIEW_PROFILE_CANONICALS",
    "SQLQUERY_LIBRARY_TYPE_CODE",
    "SQLVIEW_LIBRARY_TYPE_CODE",
    "SUPPORTED_CONTENT_TYPES",
    # Errors
    "SQLError",
    "SQLQueryParseError",
    "SQLQueryValidationError",
    "SQLQueryCycleError",
    "SQLQueryMaterializationError",
    "SQLQueryTypeError",
    "UnsupportedDialectError",
]
