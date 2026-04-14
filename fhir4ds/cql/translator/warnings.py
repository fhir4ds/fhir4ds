"""Translation warnings for CQL to SQL translation."""

from dataclasses import dataclass
from typing import List, Optional
from enum import Enum


class WarningCategory(Enum):
    """Categories of translation warnings.

    Attributes:
        PERFORMANCE: Issues that may impact query performance or scalability.
        SEMANTICS: Differences between CQL semantics and SQL behavior.
        DEPRECATED: Usage of deprecated features or patterns.
        COMPATIBILITY: Issues with backward or forward compatibility.
    """
    PERFORMANCE = "PERFORMANCE"
    SEMANTICS = "SEMANTICS"
    DEPRECATED = "DEPRECATED"
    COMPATIBILITY = "COMPATIBILITY"


@dataclass
class TranslationWarning:
    """A single translation warning.

    Represents a warning that occurred during CQL to SQL translation,
    categorized by type and associated with a specific definition location.

    Attributes:
        category: The category of the warning (PERFORMANCE, SEMANTICS, etc.).
        message: Human-readable description of the warning.
        definition: Name of the CQL definition where the warning occurred.
        suggestion: Optional suggestion for resolving the warning.
        line: Line number in the source CQL (if available).
        column: Column number in the source CQL (if available).
    """
    category: WarningCategory
    message: str
    definition: Optional[str] = None
    suggestion: Optional[str] = None
    line: Optional[int] = None
    column: Optional[int] = None

    def __str__(self) -> str:
        parts = [f"[{self.category.value}]"]
        if self.definition:
            parts.append(f"({self.definition})")
        parts.append(self.message)
        if self.line:
            parts.append(f"at line {self.line}")
        result = " ".join(parts)
        if self.suggestion:
            result += f"\n  Suggestion: {self.suggestion}"
        return result


class TranslationWarnings:
    """Collection of translation warnings.

    Manages a collection of TranslationWarning objects with methods for
    adding, filtering, and reporting warnings during CQL to SQL translation.

    Example:
        warnings = TranslationWarnings()
        warnings.add_performance(
            message="Potential performance issue with correlated subquery",
            definition="DiabetesPrevalence",
            suggestion="Consider using LEFT JOIN instead"
        )
    """

    def __init__(self):
        self.warnings: List[TranslationWarning] = []

    def add(
        self,
        category: WarningCategory,
        message: str,
        definition: Optional[str] = None,
        suggestion: Optional[str] = None,
        line: Optional[int] = None,
        column: Optional[int] = None,
    ) -> None:
        """Add a translation warning to the collection.

        Args:
            category: The category of the warning.
            message: Human-readable description of the warning.
            definition: Name of the CQL definition where the warning occurred.
            suggestion: Optional suggestion for resolving the warning.
            line: Line number in the source CQL (if available).
            column: Column number in the source CQL (if available).
        """
        self.warnings.append(TranslationWarning(
            category=category,
            message=message,
            definition=definition,
            suggestion=suggestion,
            line=line,
            column=column,
        ))

    def add_performance(
        self,
        message: str,
        definition: Optional[str] = None,
        suggestion: Optional[str] = None
    ) -> None:
        """Add a performance-related warning.

        Args:
            message: Description of the performance issue.
            definition: Name of the CQL definition where the issue occurs.
            suggestion: Optional suggestion for improvement.
        """
        self.add(WarningCategory.PERFORMANCE, message, definition, suggestion)

    def add_semantics(
        self,
        message: str,
        definition: Optional[str] = None,
        suggestion: Optional[str] = None
    ) -> None:
        """Add a semantics-related warning.

        Args:
            message: Description of the semantic issue.
            definition: Name of the CQL definition where the issue occurs.
            suggestion: Optional suggestion for improvement.
        """
        self.add(WarningCategory.SEMANTICS, message, definition, suggestion)

    def has_warnings(self) -> bool:
        """Check if there are any warnings in the collection.

        Returns:
            True if there are warnings, False otherwise.
        """
        return len(self.warnings) > 0

    def count(self) -> int:
        """Get the total number of warnings.

        Returns:
            The count of warnings in the collection.
        """
        return len(self.warnings)

    def filter_by_category(self, category: WarningCategory) -> List[TranslationWarning]:
        """Get warnings of a specific category.

        Args:
            category: The warning category to filter by.

        Returns:
            List of warnings matching the specified category.
        """
        return [w for w in self.warnings if w.category == category]

    def report(self) -> str:
        """Generate a human-readable report of all warnings.

        Returns:
            A formatted string listing all warnings, or empty string if none.
        """
        if not self.warnings:
            return ""

        lines = [f"Translation Warnings ({len(self.warnings)}):"]
        for w in self.warnings:
            lines.append(f"  {w}")
        return "\n".join(lines)

    def clear(self) -> None:
        """Clear all warnings from the collection."""
        self.warnings.clear()
