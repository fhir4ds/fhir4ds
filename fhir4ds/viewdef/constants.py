"""
Constant Resolution for SQL-on-FHIR ViewDefinitions.

Handles the resolution of constants defined in ViewDefinitions into SQL values.
Constants are pre-resolved into SQL strings before query generation.

Supported constant types:
- valueCode: Simple string/code value
- valueCoding: {system, code, display} object
- valueCodeableConcept: {coding: [...], text} object

Usage:
    from .constants import ConstantResolver, resolve_constant

    # Create resolver with constants
    resolver = ConstantResolver.from_list(constants_list)

    # Resolve a path containing %ConstantName placeholders
    resolved_path = resolver.resolve_in_path("gender = %Female")
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .types import Constant

_logger = logging.getLogger(__name__)


def resolve_constant(constant: Constant) -> str:
    """
    Convert a constant value to a SQL string representation.

    The SQL string is suitable for embedding in FHIRPath expressions.
    Strings are properly escaped with single quotes.

    Args:
        constant: A Constant instance from types.py.

    Returns:
        A SQL string representation of the constant value.

    Examples:
        >>> from fhir4ds.viewdef.types import Constant
        >>> const = Constant(name="Female", value="female", value_type="code")
        >>> resolve_constant(constant)
        "'female'"

        >>> coding = {"system": "http://hl7.org/fhir/gender-identity", "code": "female"}
        >>> const = Constant(name="FemaleCoding", value=coding, value_type="Coding")
        >>> resolve_constant(constant)
        "Coding{system: 'http://hl7.org/fhir/gender-identity', code: 'female'}"
    """
    value = constant.value

    if value is None:
        return "null"

    # Determine the type of the constant
    value_type = constant.value_type

    # Handle based on type
    if value_type == "Coding" or (isinstance(value, dict) and _is_coding(value)):
        return _resolve_coding(value)
    elif value_type == "CodeableConcept" or (isinstance(value, dict) and _is_codeable_concept(value)):
        return _resolve_codeable_concept(value)
    else:
        # Simple value (code, string, integer, boolean, etc.)
        return _resolve_simple_value(value, value_type)


def _is_coding(value: dict[str, Any]) -> bool:
    """Check if a dict looks like a Coding object."""
    return "code" in value or "system" in value


def _is_codeable_concept(value: dict[str, Any]) -> bool:
    """Check if a dict looks like a CodeableConcept object."""
    return "coding" in value or "text" in value


def _resolve_simple_value(value: Any, value_type: str | None) -> str:
    """
    Convert a simple value to SQL string representation.

    Args:
        value: The simple value (string, int, float, bool).
        value_type: The type hint for the value.

    Returns:
        A SQL string representation.

    Raises:
        ValueError: If the value is a complex type (dict/list) that wasn't
            handled by the upstream Coding/CodeableConcept dispatch.
    """
    if isinstance(value, (dict, list)):
        raise ValueError(
            f"Cannot resolve complex constant value of type '{value_type}' "
            f"(Python {type(value).__name__}). Only Coding, CodeableConcept, "
            f"and simple types (string, code, integer, boolean) are supported."
        )
    if isinstance(value, bool):
        return "true" if value else "false"
    elif isinstance(value, (int, float)):
        return str(value)
    else:
        # String/code value - escape single quotes using SQL standard (double the quote)
        escaped = str(value).replace("'", "''")
        return f"'{escaped}'"


def _resolve_coding(coding: dict[str, Any]) -> str:
    """
    Convert a Coding object to SQL string representation.

    FHIR Coding format:
    {
        "system": "http://example.org/codes",
        "code": "code-value",
        "display": "Display Text"  // optional
    }

    For FHIRPath, this creates a Coding literal that can be used in comparisons.
    The format is: Coding{system: '...', code: '...', display: '...'}

    Args:
        coding: A Coding dictionary.

    Returns:
        A SQL string representation of the Coding.
    """
    system = coding.get("system", "")
    code = coding.get("code", "")
    display = coding.get("display", "")

    # Escape single quotes
    system = str(system).replace("'", "''") if system else ""
    code = str(code).replace("'", "''") if code else ""
    display = str(display).replace("'", "''") if display else ""

    # Build the Coding literal
    # In FHIRPath, Coding literals use the format: Coding{system: '...', code: '...'}
    parts = []
    if system:
        parts.append(f"system: '{system}'")
    if code:
        parts.append(f"code: '{code}'")
    if display:
        parts.append(f"display: '{display}'")

    return f"Coding{{{', '.join(parts)}}}"


def _resolve_codeable_concept(concept: dict[str, Any]) -> str:
    """
    Convert a CodeableConcept object to SQL string representation.

    FHIR CodeableConcept format:
    {
        "coding": [
            {"system": "...", "code": "...", "display": "..."},
            ...
        ],
        "text": "Text description"  // optional
    }

    For FHIRPath, this creates a CodeableConcept literal.

    Args:
        concept: A CodeableConcept dictionary.

    Returns:
        A SQL string representation of the CodeableConcept.
    """
    codings = concept.get("coding", [])
    text = concept.get("text", "")

    # Build coding list
    coding_parts = []
    for coding in codings:
        system = coding.get("system", "")
        code = coding.get("code", "")
        display = coding.get("display", "")

        # Escape single quotes
        system = str(system).replace("'", "''") if system else ""
        code = str(code).replace("'", "''") if code else ""
        display = str(display).replace("'", "''") if display else ""

        coding_literal_parts = []
        if system:
            coding_literal_parts.append(f"system: '{system}'")
        if code:
            coding_literal_parts.append(f"code: '{code}'")
        if display:
            coding_literal_parts.append(f"display: '{display}'")

        coding_parts.append(f"Coding{{{', '.join(coding_literal_parts)}}}")

    # Escape text
    text = str(text).replace("'", "''") if text else ""

    # Build the CodeableConcept literal
    parts = []
    if coding_parts:
        coding_list = ", ".join(coding_parts)
        parts.append(f"coding: [{coding_list}]")
    if text:
        parts.append(f"text: '{text}'")

    return f"CodeableConcept{{{', '.join(parts)}}}"


def resolve_constants_in_path(path: str, constants: dict[str, Constant]) -> str:
    """
    Replace %ConstantName placeholders in a FHIRPath expression.

    Constants are referenced in paths using the %Name syntax.
    This function replaces all such references with their resolved values.

    Args:
        path: A FHIRPath expression that may contain %ConstantName references.
        constants: A dictionary mapping constant names to Constant instances.

    Returns:
        The path with all constant references resolved.

    Examples:
        >>> from fhir4ds.viewdef.types import Constant
        >>> constants = {"Female": Constant(name="Female", value="female", value_type="code")}
        >>> resolve_constants_in_path("gender = %Female", constants)
        "gender = 'female'"
    """
    # Pattern to match %ConstantName
    # Constant names must start with a letter or underscore and can contain
    # letters, digits, and underscores
    pattern = r'%([a-zA-Z_][a-zA-Z0-9_]*)'

    def replace_match(match: re.Match) -> str:
        const_name = match.group(1)
        if const_name in constants:
            return resolve_constant(constants[const_name])
        # Spec-compliant FHIRPath context variables (%context, %resource, etc.)
        # should pass through unchanged — they are resolved at evaluation time.
        # However, undefined user constants should raise an error.
        _FHIRPATH_CONTEXT_VARS = {
            "context", "resource", "rootResource", "ucum",
        }
        if const_name in _FHIRPATH_CONTEXT_VARS:
            return match.group(0)
        _logger.warning(
            "Undefined constant reference '%%%s' in FHIRPath expression. "
            "This may cause evaluation errors.",
            const_name,
        )
        return match.group(0)

    return re.sub(pattern, replace_match, path)


class ConstantResolver:
    """
    Manages constant resolution for a ViewDefinition.

    This class provides a convenient interface for resolving constants
    defined in a ViewDefinition. It maintains a registry of constants
    and provides methods to resolve them in paths.

    Attributes:
        constants: Dictionary mapping constant names to Constant instances.

    Example:
        >>> from fhir4ds.viewdef.types import Constant
        >>> constants_list = [
        ...     {"name": "Female", "valueCode": "female"},
        ...     {"name": "Male", "valueCode": "male"}
        ... ]
        >>> resolver = ConstantResolver.from_list(constants_list)
        >>> resolver.resolve_in_path("gender = %Female")
        "gender = 'female'"
    """

    def __init__(self, constants: dict[str, Constant] | None = None) -> None:
        """
        Initialize the resolver with optional constants.

        Args:
            constants: Optional dictionary of constant name to Constant.
        """
        self._constants: dict[str, Constant] = constants or {}

    @classmethod
    def from_list(cls, constants_list: list[Constant] | list[dict[str, Any]]) -> ConstantResolver:
        """
        Create a ConstantResolver from a list of constant definitions.

        Args:
            constants_list: List of Constant instances or dictionaries
                           as they appear in the ViewDefinition JSON.

        Returns:
            A ConstantResolver instance with all constants registered.
        """
        from .types import Constant as ConstantType

        constants: dict[str, Constant] = {}
        for const_item in constants_list:
            if isinstance(const_item, ConstantType):
                constants[const_item.name] = const_item
            elif isinstance(const_item, dict):
                const = ConstantType.from_dict(const_item)
                constants[const.name] = const
        return cls(constants)

    @classmethod
    def from_view_definition(cls, view_definition: Any) -> ConstantResolver:
        """
        Create a ConstantResolver from a ViewDefinition.

        Args:
            view_definition: A ViewDefinition instance with constants.

        Returns:
            A ConstantResolver instance with all constants from the view.
        """
        constants_dict: dict[str, Constant] = {}
        for const in view_definition.constants:
            constants_dict[const.name] = const
        return cls(constants_dict)

    @property
    def constants(self) -> dict[str, Constant]:
        """Return the dictionary of registered constants."""
        return self._constants.copy()

    def add_constant(self, constant: Constant) -> None:
        """
        Add a constant to the resolver.

        Args:
            constant: A Constant instance to add.
        """
        self._constants[constant.name] = constant

    def add_from_dict(self, data: dict[str, Any]) -> None:
        """
        Add a constant from a dictionary definition.

        Args:
            data: Dictionary with constant definition.

        Raises:
            ValueError: If the constant definition is invalid.
        """
        from .types import Constant as ConstantType
        const = ConstantType.from_dict(data)
        self._constants[const.name] = const

    def get_constant(self, name: str) -> Constant | None:
        """
        Get a constant by name.

        Args:
            name: The constant name.

        Returns:
            The Constant instance or None if not found.
        """
        return self._constants.get(name)

    def resolve(self, name: str) -> str:
        """
        Resolve a constant by name to its SQL string value.

        Args:
            name: The constant name (without the % prefix).

        Returns:
            The SQL string representation of the constant.

        Raises:
            KeyError: If the constant is not found.
        """
        if name not in self._constants:
            raise KeyError(f"Constant '{name}' not found")
        return resolve_constant(self._constants[name])

    def resolve_in_path(self, path: str) -> str:
        """
        Resolve all constant references in a FHIRPath expression.

        Args:
            path: A FHIRPath expression with %ConstantName references.

        Returns:
            The expression with all constants resolved.
        """
        return resolve_constants_in_path(path, self._constants)

    def has_constant(self, name: str) -> bool:
        """
        Check if a constant exists.

        Args:
            name: The constant name.

        Returns:
            True if the constant exists, False otherwise.
        """
        return name in self._constants

    def __contains__(self, name: str) -> bool:
        """Check if a constant exists (supports 'in' operator)."""
        return self.has_constant(name)

    def __len__(self) -> int:
        """Return the number of registered constants."""
        return len(self._constants)

    def __repr__(self) -> str:
        """String representation."""
        return f"ConstantResolver({len(self._constants)} constants)"
