"""
FHIRPath Exceptions

Defines exception classes for FHIRPath parsing and evaluation errors.

The base classes (FHIRPathError, FHIRPathSyntaxError) are defined in the
core engine to avoid upward dependencies from parser -> duckdb. This
module re-exports them and adds adapter-specific subclasses.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Sequence

# Re-export canonical base classes from core
from ..engine.errors import FHIRPathError, FHIRPathSyntaxError  # noqa: F401


class FHIRPathTypeError(FHIRPathError):
    """
    Exception raised for FHIRPath type errors.

    Raised when there's a type mismatch during evaluation, such as
    applying an operation to an incompatible type.

    Example:
        >>> raise FHIRPathTypeError("Cannot add string to integer")
    """

    def __init__(
        self,
        message: str,
        expected_type: str | None = None,
        actual_type: str | None = None,
        expression: str | None = None,
    ) -> None:
        """
        Initialize a type error.

        Args:
            message: Error description.
            expected_type: The expected FHIRPath type.
            actual_type: The actual type received.
            expression: The expression causing the error.
        """
        self.expected_type = expected_type
        self.actual_type = actual_type

        if expected_type and actual_type:
            message = f"{message}. Expected {expected_type}, got {actual_type}"

        super().__init__(message, expression)

    def __repr__(self) -> str:
        """String representation."""
        return (
            f"FHIRPathTypeError({self.message!r}, "
            f"expected={self.expected_type!r}, actual={self.actual_type!r})"
        )


class FHIRPathNotFoundError(FHIRPathError):
    """
    Exception raised when a path is not found.

    This is typically not raised during normal evaluation (paths not
    found return empty collections), but may be raised in strict mode
    or when a required path is missing.

    Example:
        >>> raise FHIRPathNotFoundError("Path not found: Patient.unknownField")
    """

    def __init__(
        self,
        path: str,
        resource_type: str | None = None,
    ) -> None:
        """
        Initialize a not found error.

        Args:
            path: The path that was not found.
            resource_type: The resource type being queried.
        """
        self.path = path
        self.resource_type = resource_type

        message = f"Path not found: {path}"
        if resource_type:
            message = f"{message} in {resource_type}"

        super().__init__(message)

    def __repr__(self) -> str:
        """String representation."""
        return f"FHIRPathNotFoundError({self.path!r})"


class FHIRPathEvaluationError(FHIRPathError):
    """
    Exception raised for evaluation errors.

    Raised when an error occurs during expression evaluation that is
    not a syntax or type error, such as division by zero or invalid
    function arguments.

    Example:
        >>> raise FHIRPathEvaluationError("Division by zero")
    """

    def __init__(
        self,
        message: str,
        expression: str | None = None,
        context: dict | None = None,
        path: str | None = None,
        value: Any | None = None,
        suggestion: str | None = None,
    ) -> None:
        """
        Initialize an evaluation error.

        Args:
            message: Error description.
            expression: The expression being evaluated.
            context: Additional context about the error.
            path: The FHIRPath where the error occurred.
            value: The value that caused the error.
            suggestion: A helpful suggestion for fixing the error.
        """
        self.context = context or {}
        self.path = path
        self.value = value
        self.suggestion = suggestion
        super().__init__(message, expression)

    def _format_message(self) -> str:
        """Format a detailed error message with context."""
        msg = f"FHIRPath evaluation error: {self.message}"
        if self.expression:
            msg += f"\n  Expression: {self.expression}"
        if self.path:
            msg += f"\n  At path: {self.path}"
        if self.value is not None:
            # Truncate long values
            value_str = repr(self.value)
            if len(value_str) > 100:
                value_str = value_str[:97] + "..."
            msg += f"\n  Value: {value_str}"
        if self.suggestion:
            msg += f"\n  Suggestion: {self.suggestion}"
        return msg

    def __str__(self) -> str:
        """String representation of the error."""
        return self._format_message()

    def __repr__(self) -> str:
        """String representation."""
        return f"FHIRPathEvaluationError({self.message!r})"


class FHIRPathFunctionError(FHIRPathError):
    """
    Exception raised for function-related errors.

    Raised when a FHIRPath function is called incorrectly or with
    invalid arguments.

    Example:
        >>> raise FHIRPathFunctionError("substring() requires start index")
    """

    def __init__(
        self,
        function_name: str,
        message: str,
        expression: str | None = None,
    ) -> None:
        """
        Initialize a function error.

        Args:
            function_name: Name of the function.
            message: Error description.
            expression: The expression being evaluated.
        """
        self.function_name = function_name
        full_message = f"In function {function_name}(): {message}"
        super().__init__(full_message, expression)

    def __repr__(self) -> str:
        """String representation."""
        return f"FHIRPathFunctionError({self.function_name!r}, {self.message!r})"


class FHIRPathResourceError(FHIRPathError):
    """
    Exception raised for resource-related errors.

    Raised when there's an issue with the FHIR resource being queried,
    such as invalid JSON or missing required fields.

    Example:
        >>> raise FHIRPathResourceError("Invalid FHIR resource: missing resourceType")
    """

    def __init__(
        self,
        message: str,
        resource_id: str | None = None,
        resource_type: str | None = None,
    ) -> None:
        """
        Initialize a resource error.

        Args:
            message: Error description.
            resource_id: ID of the problematic resource.
            resource_type: Type of the resource.
        """
        self.resource_id = resource_id
        self.resource_type = resource_type

        if resource_type and resource_id:
            message = f"{message} ({resource_type}/{resource_id})"
        elif resource_type:
            message = f"{message} ({resource_type})"

        super().__init__(message)

    def __repr__(self) -> str:
        """String representation."""
        return f"FHIRPathResourceError({self.message!r})"


# Suggestion Engine for common typos
def levenshtein_distance(s1: str, s2: str) -> int:
    """
    Calculate the Levenshtein distance between two strings.

    Args:
        s1: First string.
        s2: Second string.

    Returns:
        The minimum number of edits to transform s1 into s2.
    """
    if len(s1) < len(s2):
        return levenshtein_distance(s2, s1)

    if len(s2) == 0:
        return len(s1)

    previous_row = range(len(s2) + 1)
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row

    return previous_row[-1]


def suggest_field_name(
    field_name: str,
    available_fields: list[str],
    max_suggestions: int = 3,
    max_distance: int = 3,
) -> list[str]:
    """
    Suggest similar field names for a potentially misspelled field.

    Args:
        field_name: The field name that wasn't found.
        available_fields: List of valid field names to search.
        max_suggestions: Maximum number of suggestions to return.
        max_distance: Maximum edit distance for suggestions.

    Returns:
        List of suggested field names, sorted by similarity.
    """
    if not field_name or not available_fields:
        return []

    # Calculate distances to all available fields
    candidates = []
    field_lower = field_name.lower()

    for candidate in available_fields:
        candidate_lower = candidate.lower()

        # Exact match (case-insensitive) - shouldn't happen but just in case
        if candidate_lower == field_lower:
            continue

        # Calculate edit distance
        distance = levenshtein_distance(field_lower, candidate_lower)

        # Only consider if within threshold
        if distance <= max_distance:
            candidates.append((candidate, distance))

    # Sort by distance and return top suggestions
    candidates.sort(key=lambda x: x[1])
    return [c[0] for c in candidates[:max_suggestions]]


def format_suggestion(field_name: str, suggestions: list[str]) -> str | None:
    """
    Format a suggestion message for a misspelled field.

    Args:
        field_name: The field name that wasn't found.
        suggestions: List of suggested field names.

    Returns:
        Formatted suggestion string, or None if no suggestions.
    """
    if not suggestions:
        return None

    if len(suggestions) == 1:
        return f"Did you mean '{suggestions[0]}'?"
    else:
        return f"Did you mean one of: {', '.join(repr(s) for s in suggestions)}?"
