"""Core FHIRPath error types.

These error classes are defined in the core engine so that both the parser
and any adapter layers (e.g., duckdb) can import from a single canonical
location without creating upward dependencies.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Sequence


class FHIRPathError(Exception):
    """Base class for all FHIRPath errors.

    Attributes:
        message: Human-readable error description.
        expression: The FHIRPath expression that caused the error (if available).
        position: Character position in expression where error occurred (if available).
    """

    def __init__(
        self,
        message: str,
        expression: str | None = None,
        position: int | None = None,
    ) -> None:
        self.message = message
        self.expression = expression
        self.position = position

        full_message = message
        if expression:
            full_message = f"{message} in expression: {expression}"
        if position is not None:
            full_message = f"{full_message} at position {position}"

        super().__init__(full_message)

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self.message!r})"


class FHIRPathSyntaxError(FHIRPathError):
    """Raised when a FHIRPath expression has invalid syntax."""

    def __init__(
        self,
        message: str,
        expression: str | None = None,
        position: int | None = None,
        token: str | None = None,
        **kwargs,
    ) -> None:
        self.token = token
        if token:
            message = f"{message}: '{token}'"
        super().__init__(message, expression, position)

    def __repr__(self) -> str:
        return f"FHIRPathSyntaxError({self.message!r}, token={self.token!r})"


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
        self.expected_type = expected_type
        self.actual_type = actual_type

        if expected_type and actual_type:
            message = f"{message}. Expected {expected_type}, got {actual_type}"

        super().__init__(message, expression)

    def __repr__(self) -> str:
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
        self.path = path
        self.resource_type = resource_type

        message = f"Path not found: {path}"
        if resource_type:
            message = f"{message} in {resource_type}"

        super().__init__(message)

    def __repr__(self) -> str:
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
            value_str = repr(self.value)
            if len(value_str) > 100:
                value_str = value_str[:97] + "..."
            msg += f"\n  Value: {value_str}"
        if self.suggestion:
            msg += f"\n  Suggestion: {self.suggestion}"
        return msg

    def __str__(self) -> str:
        return self._format_message()

    def __repr__(self) -> str:
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
        self.function_name = function_name
        full_message = f"In function {function_name}(): {message}"
        super().__init__(full_message, expression)

    def __repr__(self) -> str:
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
        self.resource_id = resource_id
        self.resource_type = resource_type

        if resource_type and resource_id:
            message = f"{message} ({resource_type}/{resource_id})"
        elif resource_type:
            message = f"{message} ({resource_type})"

        super().__init__(message)

    def __repr__(self) -> str:
        return f"FHIRPathResourceError({self.message!r})"


# Suggestion Engine for common typos
def levenshtein_distance(s1: str, s2: str) -> int:
    """Calculate the Levenshtein distance between two strings."""
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
    """Suggest similar field names for a potentially misspelled field."""
    if not field_name or not available_fields:
        return []

    candidates = []
    field_lower = field_name.lower()

    for candidate in available_fields:
        candidate_lower = candidate.lower()
        if candidate_lower == field_lower:
            continue
        distance = levenshtein_distance(field_lower, candidate_lower)
        if distance <= max_distance:
            candidates.append((candidate, distance))

    candidates.sort(key=lambda x: x[1])
    return [c[0] for c in candidates[:max_suggestions]]


def format_suggestion(field_name: str, suggestions: list[str]) -> str | None:
    """Format a suggestion message for a misspelled field."""
    if not suggestions:
        return None

    if len(suggestions) == 1:
        return f"Did you mean '{suggestions[0]}'?"
    else:
        return f"Did you mean one of: {', '.join(repr(s) for s in suggestions)}?"
