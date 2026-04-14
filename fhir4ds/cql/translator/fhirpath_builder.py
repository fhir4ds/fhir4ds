"""
FHIRPath Expression Builder.

Provides a fluent API for building FHIRPath expressions safely,
replacing f-string concatenation throughout the codebase.
"""

from __future__ import annotations

from typing import List, Optional


class FHIRPathBuilder:
    """
    Fluent builder for FHIRPath expressions.

    This class provides a type-safe way to construct FHIRPath expressions
    without resorting to f-string concatenation, which is error-prone
    and hard to validate.

    Example:
        >>> builder = FHIRPathBuilder("code")
        >>> expr = str(builder.coding().where("system='http://loinc.org'").exists())
        >>> print(expr)
        code.coding.where(system='http://loinc.org').exists()
    """

    def __init__(self, base_path: str = ""):
        """
        Initialize the builder with an optional base path.

        Args:
            base_path: The starting FHIRPath expression.
        """
        self._path: str = base_path
        self._segments: List[str] = []

    @property
    def path(self) -> str:
        """Get the current path."""
        return self._path

    def coding(self) -> FHIRPathBuilder:
        """
        Append .coding to the path.

        Returns:
            New builder with .coding appended.
        """
        return self._append(".coding")

    def code(self) -> FHIRPathBuilder:
        """
        Append .code to the path.

        Returns:
            New builder with .code appended.
        """
        return self._append(".code")

    def system(self) -> FHIRPathBuilder:
        """
        Append .system to the path.

        Returns:
            New builder with .system appended.
        """
        return self._append(".system")

    def value(self) -> FHIRPathBuilder:
        """
        Append .value to the path.

        Returns:
            New builder with .value appended.
        """
        return self._append(".value")

    def display(self) -> FHIRPathBuilder:
        """
        Append .display to the path.

        Returns:
            New builder with .display appended.
        """
        return self._append(".display")

    def reference(self) -> FHIRPathBuilder:
        """
        Append .reference to the path.

        Returns:
            New builder with .reference appended.
        """
        return self._append(".reference")

    def status(self) -> FHIRPathBuilder:
        """
        Append .status to the path.

        Returns:
            New builder with .status appended.
        """
        return self._append(".status")

    def where(self, condition: str) -> FHIRPathBuilder:
        """
        Append .where(condition) to the path.

        Args:
            condition: The where clause condition.

        Returns:
            New builder with .where() appended.
        """
        return self._append(f".where({condition})")

    def where_system(self, system_url: str) -> FHIRPathBuilder:
        """
        Append .where(system='url') to the path.

        Args:
            system_url: The system URL to filter by.

        Returns:
            New builder with .where(system='...') appended.
        """
        escaped = self._escape_string(system_url)
        return self.where(f"system='{escaped}'")

    def where_code(self, code_value: str) -> FHIRPathBuilder:
        """
        Append .where(code='value') to the path.

        Args:
            code_value: The code value to filter by.

        Returns:
            New builder with .where(code='...') appended.
        """
        escaped = self._escape_string(code_value)
        return self.where(f"code='{escaped}'")

    def where_system_and_code(self, system_url: str, code_value: str) -> FHIRPathBuilder:
        """
        Append .where(system='url' and code='value') to the path.

        Args:
            system_url: The system URL to filter by.
            code_value: The code value to filter by.

        Returns:
            New builder with combined where clause appended.
        """
        escaped_system = self._escape_string(system_url)
        escaped_code = self._escape_string(code_value)
        return self.where(f"system='{escaped_system}' and code='{escaped_code}'")

    def exists(self) -> FHIRPathBuilder:
        """
        Append .exists() to the path.

        Returns:
            New builder with .exists() appended.
        """
        return self._append(".exists()")

    def not_null(self) -> FHIRPathBuilder:
        """
        Append a not null check pattern.

        Returns:
            New builder with .exists() appended (equivalent to not null).
        """
        return self.exists()

    def first(self) -> FHIRPathBuilder:
        """
        Append .first() to the path.

        Returns:
            New builder with .first() appended.
        """
        return self._append(".first()")

    def as_string(self, property_name: str) -> FHIRPathBuilder:
        """
        Navigate to a property.

        Args:
            property_name: The property name to navigate to.

        Returns:
            New builder with property appended.
        """
        return self._append(f".{property_name}")

    def of_type(self, type_name: str) -> FHIRPathBuilder:
        """
        Append ofType() to the path.

        Args:
            type_name: The type name to filter by.

        Returns:
            New builder with ofType() appended.
        """
        return self._append(f".ofType({type_name})")

    def _append(self, segment: str) -> FHIRPathBuilder:
        """
        Append a segment to the path.

        Args:
            segment: The segment to append.

        Returns:
            New builder with the segment appended.
        """
        if self._path:
            return FHIRPathBuilder(f"{self._path}{segment}")
        else:
            # Handle empty base path
            return FHIRPathBuilder(segment.lstrip("."))

    @staticmethod
    def _escape_fhirpath_string(value: str) -> str:
        """
        Escape a string for use in FHIRPath (static version).

        Args:
            value: The string value to escape.

        Returns:
            Escaped string safe for FHIRPath.
        """
        # Escape single quotes by doubling them
        return value.replace("'", "''")

    @staticmethod
    def _build_system_code_condition(system: str, code: str) -> str:
        """Build a parenthesized system+code condition with proper escaping."""
        escaped_system = FHIRPathBuilder._escape_fhirpath_string(system)
        escaped_code = FHIRPathBuilder._escape_fhirpath_string(code)
        return "(system='{}' and code='{}')".format(escaped_system, escaped_code)

    @staticmethod
    def build_display_condition(display: str) -> str:
        """Build a code.coding.display condition with proper escaping."""
        escaped = FHIRPathBuilder._escape_fhirpath_string(display)
        return "code.coding.display = '{}'".format(escaped)

    @staticmethod
    def build_code_condition(code: str) -> str:
        """Build a code.coding.code condition with proper escaping."""
        escaped = FHIRPathBuilder._escape_fhirpath_string(code)
        return "code.coding.code = '{}'".format(escaped)

    def _escape_string(self, value: str) -> str:
        """
        Escape a string for use in FHIRPath.

        Args:
            value: The string value to escape.

        Returns:
            Escaped string safe for FHIRPath.
        """
        return self._escape_fhirpath_string(value)

    def __str__(self) -> str:
        """Convert builder to FHIRPath string."""
        return self._path

    def __repr__(self) -> str:
        """Representation of the builder."""
        return f"FHIRPathBuilder('{self._path}')"

    def build(self) -> str:
        """
        Build the final FHIRPath expression.

        Returns:
            The FHIRPath expression string.
        """
        return self._path

    @classmethod
    def from_path(cls, path: str) -> FHIRPathBuilder:
        """
        Create a builder from an existing path.

        Args:
            path: The existing FHIRPath expression.

        Returns:
            New FHIRPathBuilder instance.
        """
        return cls(path)

    @classmethod
    def property(cls, name: str) -> FHIRPathBuilder:
        """
        Create a builder starting with a property name.

        Args:
            name: The property name.

        Returns:
            New FHIRPathBuilder instance.
        """
        return cls(name)


def build_coding_exists_expr(
    base_path: str,
    system_url: Optional[str] = None,
    code_value: Optional[str] = None,
    is_coding_type: bool = False,
) -> str:
    """
    Build a FHIRPath expression for checking if a coding exists.

    Args:
        base_path: The base property path (e.g., "code").
        system_url: Optional system URL to filter by.
        code_value: Optional code value to filter by.
        is_coding_type: If True, the property is already a Coding (not
            CodeableConcept), so skip the ``.coding`` navigation step.

    Returns:
        FHIRPath expression string.
    """
    builder = FHIRPathBuilder(base_path)
    if not is_coding_type:
        builder = builder.coding()

    if system_url and code_value:
        builder = builder.where_system_and_code(system_url, code_value)
    elif system_url:
        builder = builder.where_system(system_url)
    elif code_value:
        builder = builder.where_code(code_value)

    return str(builder.exists())


def build_reference_expr(base_path: str = "") -> FHIRPathBuilder:
    """
    Build a FHIRPath expression for reference navigation.

    Args:
        base_path: Optional base path before reference.

    Returns:
        FHIRPathBuilder for reference navigation.
    """
    if base_path:
        return FHIRPathBuilder(base_path).reference()
    return FHIRPathBuilder("reference")


def build_multi_coding_exists_expr(
    base_path: str,
    codes: list,
) -> str:
    """
    Build a FHIRPath expression for checking if any of multiple codes match.

    Used for concept equivalence with OR'd system+code pairs.

    Args:
        base_path: The base property path (e.g., "code").
        codes: List of dicts with 'system' and 'code' keys.

    Returns:
        FHIRPath expression string.
    """
    conditions = []
    for code_info in codes:
        condition = FHIRPathBuilder._build_system_code_condition(
            code_info.get("system", ""), code_info.get("code", "")
        )
        conditions.append(condition)
    or_conditions = " or ".join(conditions)
    return str(
        FHIRPathBuilder(base_path).coding().where(or_conditions).exists()
    )


def build_where_return_expr(
    base_path: str,
    where_clause: str,
    return_path: str,
) -> str:
    """
    Build a FHIRPath expression: base_path.where(clause).return_path.

    Used for component filtering patterns like:
        component.where(code.display = 'Systolic').valueQuantity.value

    Args:
        base_path: The base property path (e.g., "component").
        where_clause: The where condition string.
        return_path: The dotted return path (e.g., "valueQuantity.value").

    Returns:
        FHIRPath expression string.
    """
    builder = FHIRPathBuilder(base_path).where(where_clause)
    # Append each segment of the return path
    for segment in return_path.split("."):
        builder = builder.as_string(segment)
    return builder.build()
