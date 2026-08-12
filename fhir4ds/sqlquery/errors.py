"""Typed error hierarchy for ``fhir4ds.sqlquery``.

All errors inherit from :class:`SQLError` (which itself inherits from
``ValueError`` for backward compatibility with callers that catch the
broader parent). Profile validation, parsing, materialization, and
execution each have a typed subclass so callers can dispatch precisely.
"""


class SQLError(ValueError):
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
