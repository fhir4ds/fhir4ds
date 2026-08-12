"""Typed error hierarchy for ``fhir4ds.sqlquery``.

All errors inherit from :class:`SQLError`. Per BUGFIX-001, `SQLError`
inherits from :class:`fhir4ds.viewdef.errors.SQLOnFHIRError` so consumers
catching the existing SQL-on-FHIR root also catch SQLQuery errors.
`SQLOnFHIRError` already inherits from `ValueError`, so the broader
`except ValueError:` form still works transitively.
"""

from ..viewdef.errors import SQLOnFHIRError


class SQLError(SQLOnFHIRError):
    """Base class for all ``fhir4ds.sqlquery`` typed errors."""


class SQLQueryParseError(SQLError):
    """Raised when a FHIR Library JSON cannot be parsed into a SQLQuery/SQLView."""


class SQLQueryValidationError(SQLError):
    """Raised when a parsed SQLQuery/SQLView violates the profile invariants."""


class UnsupportedDialectError(SQLError):
    """Raised when no ``content[].contentType`` matches a supported DuckDB dialect.

    Supported dialects: ``application/sql`` and ``application/sql;dialect=duckdb``.
    """


class SQLQueryCycleError(SQLError):
    """Raised when ``relatedArtifact`` dependency resolution detects a cycle."""


class SQLQueryMaterializationError(SQLError):
    """Raised when a ``relatedArtifact`` ViewDefinition/SQLView cannot be resolved."""


class SQLQueryTypeError(SQLError):
    """Raised when a parameter value cannot be coerced to its declared FHIR type."""
