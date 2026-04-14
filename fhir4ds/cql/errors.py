"""
Error classes for cqlpy.

Provides a hierarchy of exceptions for different stages of CQL processing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Tuple


@dataclass
class CQLError(Exception):
    """Base exception for all CQL-related errors."""

    message: str
    position: Optional[Tuple[int, int]] = None
    suggestion: Optional[str] = None

    def __post_init__(self) -> None:
        # Call Exception.__init__ with formatted message
        Exception.__init__(self, self._format_message())

    def _format_message(self) -> str:
        parts = []
        if self.position:
            parts.append(f"Line {self.position[0]}, Column {self.position[1]}: {self.message}")
        else:
            parts.append(self.message)
        if self.suggestion:
            parts.append(f"\n  Suggestion: {self.suggestion}")
        return "".join(parts)

    def __str__(self) -> str:
        return self._format_message()


@dataclass
class LexerError(CQLError):
    """Error during lexical analysis (tokenization)."""

    pass


@dataclass
class ParseError(CQLError):
    """Error during parsing (AST construction)."""

    expected: Optional[str] = None
    found: Optional[str] = None

    def _format_message(self) -> str:
        parts = []
        if self.position:
            parts.append(f"Line {self.position[0]}, Column {self.position[1]}: ")
        parts.append(self.message)
        if self.expected and self.found:
            parts.append(f"\n  Expected: {self.expected}")
            parts.append(f"\n  Found: {self.found}")
        if self.suggestion:
            parts.append(f"\n  Suggestion: {self.suggestion}")
        return "".join(parts)


@dataclass
class TranslationError(CQLError):
    """Error during CQL to FHIRPath translation."""

    pass


@dataclass
class CodeGenerationError(CQLError):
    """Error during SQL code generation."""

    pass


@dataclass
class SemanticError(CQLError):
    """Error during semantic analysis."""

    symbol: Optional[str] = None
    expected_type: Optional[str] = None
    actual_type: Optional[str] = None

    def _format_message(self) -> str:
        parts = []
        if self.position:
            parts.append(f"Line {self.position[0]}, Column {self.position[1]}: ")
        parts.append(self.message)
        if self.expected_type and self.actual_type:
            parts.append(f"\n  Expected type: {self.expected_type}")
            parts.append(f"\n  Actual type: {self.actual_type}")
        if self.symbol:
            parts.append(f"\n  Symbol: {self.symbol}")
        if self.suggestion:
            parts.append(f"\n  Suggestion: {self.suggestion}")
        return "".join(parts)


@dataclass
class UnsupportedFeatureError(CQLError):
    """Raised when a CQL feature is not yet supported."""

    feature_name: Optional[str] = None
    workaround: Optional[str] = None

    def _format_message(self) -> str:
        parts = [f"Unsupported feature: {self.feature_name or self.message}"]
        if self.position:
            parts[0] = f"Line {self.position[0]}, Column {self.position[1]}: " + parts[0]
        if self.workaround:
            parts.append(f"\n  Workaround: {self.workaround}")
        if self.suggestion and not self.workaround:
            parts.append(f"\n  Suggestion: {self.suggestion}")
        return "".join(parts)


# Factory functions


def unsupported_feature(
    feature: str,
    position: Optional[Tuple[int, int]] = None,
    workaround: Optional[str] = None,
) -> UnsupportedFeatureError:
    """
    Create an UnsupportedFeatureError with standard formatting.

    Args:
        feature: Name of the unsupported feature
        position: Optional (line, column) tuple indicating location
        workaround: Optional workaround suggestion

    Returns:
        An UnsupportedFeatureError instance
    """
    return UnsupportedFeatureError(
        message=f"Feature '{feature}' is not supported",
        feature_name=feature,
        position=position,
        workaround=workaround,
        suggestion=workaround,
    )


def type_mismatch(
    symbol: str,
    expected: str,
    actual: str,
    position: Optional[Tuple[int, int]] = None,
) -> SemanticError:
    """
    Create a SemanticError for type mismatches.

    Args:
        symbol: The symbol with the type mismatch
        expected: The expected type
        actual: The actual type found
        position: Optional (line, column) tuple indicating location

    Returns:
        A SemanticError instance
    """
    return SemanticError(
        message=f"Type mismatch for '{symbol}'",
        symbol=symbol,
        expected_type=expected,
        actual_type=actual,
        position=position,
        suggestion=f"Ensure '{symbol}' is of type '{expected}'",
    )


__all__ = [
    "CQLError",
    "LexerError",
    "ParseError",
    "TranslationError",
    "CodeGenerationError",
    "SemanticError",
    "UnsupportedFeatureError",
    "unsupported_feature",
    "type_mismatch",
]
