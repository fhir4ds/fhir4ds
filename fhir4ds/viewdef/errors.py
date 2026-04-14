"""
Error classes for SQL-on-FHIR v2 processing.

This module defines a hierarchy of exceptions for handling
errors during ViewDefinition parsing, validation, and SQL generation.
"""

from typing import Any, Dict, List, Optional


class SQLOnFHIRError(Exception):
    """Base exception for all SQL-on-FHIR errors.

    All custom exceptions in sqlonfhirpy inherit from this class,
    allowing callers to catch all package-specific errors with
    a single except clause.

    Attributes:
        message: Human-readable error description.
        details: Optional dictionary with additional error context.
    """

    def __init__(
        self,
        message: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.message = message
        self.details = details or {}
        super().__init__(self.message)

    def __str__(self) -> str:
        if self.details:
            detail_str = ", ".join(f"{k}={v!r}" for k, v in self.details.items())
            return f"{self.message} ({detail_str})"
        return self.message


class ParseError(SQLOnFHIRError):
    """Raised when ViewDefinition JSON cannot be parsed.

    This error indicates that the input JSON is malformed or
    does not conform to the expected ViewDefinition structure.

    Examples:
        - Invalid JSON syntax
        - Missing required fields
        - Unexpected field types
    """

    def __init__(
        self,
        message: str,
        path: Optional[str] = None,
        value: Optional[Any] = None,
    ) -> None:
        details = {}
        if path is not None:
            details["path"] = path
        if value is not None:
            details["value"] = value
        super().__init__(message, details)


class ValidationError(SQLOnFHIRError):
    """Raised when ViewDefinition fails validation.

    This error indicates that the ViewDefinition is structurally
    valid but violates SQL-on-FHIR specification rules.

    The validation is performed in permissive mode by default,
    meaning warnings are collected rather than raising errors
    immediately. This exception is raised when critical validation
    failures occur.

    Attributes:
        warnings: List of non-critical validation warnings.
    """

    def __init__(
        self,
        message: str,
        warnings: Optional[List[str]] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.warnings = warnings or []
        super().__init__(message, details)

    def __str__(self) -> str:
        base = super().__str__()
        if self.warnings:
            warnings_str = "; ".join(self.warnings[:5])
            if len(self.warnings) > 5:
                warnings_str += f" (and {len(self.warnings) - 5} more)"
            return f"{base}\nWarnings: {warnings_str}"
        return base


class GenerationError(SQLOnFHIRError):
    """Raised when SQL generation fails.

    This error indicates that the ViewDefinition could not be
    converted to valid SQL. This typically happens when:

    - Unsupported features are used
    - Circular references are detected
    - Resource types cannot be resolved

    Attributes:
        phase: The generation phase where the error occurred.
    """

    def __init__(
        self,
        message: str,
        phase: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        details = details or {}
        if phase is not None:
            details["phase"] = phase
        super().__init__(message, details)


class ConstantResolutionError(SQLOnFHIRError):
    """Raised when a constant cannot be resolved.

    This error occurs when a ViewDefinition references a constant
    that is not defined or cannot be converted to a SQL value.

    Attributes:
        constant_name: The name of the unresolved constant.
        constant_type: The expected type of the constant.
    """

    def __init__(
        self,
        message: str,
        constant_name: Optional[str] = None,
        constant_type: Optional[str] = None,
    ) -> None:
        details = {}
        if constant_name is not None:
            details["constant_name"] = constant_name
        if constant_type is not None:
            details["constant_type"] = constant_type
        super().__init__(message, details)


class UnsupportedFeatureError(SQLOnFHIRError):
    """Raised when an unsupported SQL-on-FHIR feature is used.

    This error indicates that a feature defined in the ViewDefinition
    is not yet implemented in this version of sqlonfhirpy.

    Attributes:
        feature: The name of the unsupported feature.
    """

    def __init__(
        self,
        message: str,
        feature: Optional[str] = None,
    ) -> None:
        details = {}
        if feature is not None:
            details["feature"] = feature
        super().__init__(message, details)
