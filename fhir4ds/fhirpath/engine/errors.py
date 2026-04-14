"""Core FHIRPath error types.

These error classes are defined in the core engine so that both the parser
and any adapter layers (e.g., duckdb) can import from a single canonical
location without creating upward dependencies.
"""


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
