"""
FHIRPath Type System

Provides type definitions and mapping functions for converting between
Arrow, FHIRPath, and DuckDB type systems.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any, Union

import pyarrow as pa

if TYPE_CHECKING:
    from collections.abc import Sequence


class FHIRPathType(Enum):
    """FHIRPath primitive types."""

    BOOLEAN = "boolean"
    INTEGER = "integer"
    DECIMAL = "decimal"
    STRING = "string"
    DATE = "date"
    DATETIME = "dateTime"
    TIME = "time"
    QUANTITY = "Quantity"
    CODING = "Coding"
    CODEABLE_CONCEPT = "CodeableConcept"
    RESOURCE = "Resource"
    COLLECTION = "Collection"
    ANY = "any"


@dataclass
class TypeInfo:
    """Type information for a FHIRPath value."""

    fhirpath_type: FHIRPathType
    is_collection: bool = False
    is_optional: bool = False
    element_type: TypeInfo | None = None

    def __repr__(self) -> str:
        """String representation of type info."""
        base = self.fhirpath_type.value
        if self.is_collection:
            return f"Collection<{base}>"
        if self.is_optional:
            return f"{base}?"
        return base


from .collection import FHIRPathCollection

# Backward-compatible alias – the canonical implementation lives in collection.py.
Collection = FHIRPathCollection


@dataclass
class Resource:
    """
    FHIR Resource wrapper.

    Wraps a FHIR resource dictionary with type information.

    Attributes:
        data: The raw FHIR resource data.
        resource_type: The FHIR resource type (e.g., 'Patient', 'Observation').
    """

    data: dict[str, Any]
    resource_type: str = field(init=False)

    def __post_init__(self) -> None:
        """Extract resource type from data."""
        self.resource_type = self.data.get("resourceType", "Unknown")

    def __repr__(self) -> str:
        """String representation."""
        return f"Resource({self.resource_type})"

    def get(self, path: str, default: Any = None) -> Any:
        """
        Get a value by path.

        Args:
            path: Dot-notation path (e.g., 'name.given').
            default: Default value if path not found.

        Returns:
            The value at the path or default.
        """
        current = self.data
        for part in path.split('.'):
            if isinstance(current, dict):
                current = current.get(part)
            else:
                return default
            if current is None:
                return default
        return current

    @property
    def id(self) -> str | None:
        """Get the resource ID."""
        return self.data.get("id")

    def to_json(self) -> str:
        """Convert to JSON string."""
        import json
        return json.dumps(self.data)


# Type mapping constants
ARROW_TO_FHIRPATH: dict[pa.DataType, FHIRPathType] = {
    pa.string(): FHIRPathType.STRING,
    pa.bool_(): FHIRPathType.BOOLEAN,
    pa.int8(): FHIRPathType.INTEGER,
    pa.int16(): FHIRPathType.INTEGER,
    pa.int32(): FHIRPathType.INTEGER,
    pa.int64(): FHIRPathType.INTEGER,
    pa.float32(): FHIRPathType.DECIMAL,
    pa.float64(): FHIRPathType.DECIMAL,
    pa.date32(): FHIRPathType.DATE,
    pa.date64(): FHIRPathType.DATE,
    pa.timestamp('us'): FHIRPathType.DATETIME,
    pa.timestamp('ns'): FHIRPathType.DATETIME,
}

FHIRPATH_TO_ARROW: dict[FHIRPathType, pa.DataType] = {
    FHIRPathType.BOOLEAN: pa.bool_(),
    FHIRPathType.INTEGER: pa.int64(),
    FHIRPathType.DECIMAL: pa.float64(),
    FHIRPathType.STRING: pa.string(),
    FHIRPathType.DATE: pa.date32(),
    FHIRPathType.DATETIME: pa.timestamp('us'),
    FHIRPathType.TIME: pa.string(),  # Time stored as string
}


def arrow_to_fhirpath_type(arrow_type: pa.DataType) -> FHIRPathType:
    """
    Convert Arrow type to FHIRPath type.

    Args:
        arrow_type: A PyArrow data type.

    Returns:
        The corresponding FHIRPath type.
    """
    # Check exact match
    if arrow_type in ARROW_TO_FHIRPATH:
        return ARROW_TO_FHIRPATH[arrow_type]

    # Check for list types
    if pa.types.is_list(arrow_type):
        return FHIRPathType.COLLECTION

    # Check for struct types (complex objects)
    if pa.types.is_struct(arrow_type):
        return FHIRPathType.RESOURCE

    # Default to string
    return FHIRPathType.STRING


def fhirpath_to_arrow_type(fhirpath_type: FHIRPathType, as_list: bool = False) -> pa.DataType:
    """
    Convert FHIRPath type to Arrow type.

    Args:
        fhirpath_type: A FHIRPath type.
        as_list: Whether to return a list type.

    Returns:
        The corresponding PyArrow data type.
    """
    base_type = FHIRPATH_TO_ARROW.get(fhirpath_type, pa.string())

    if as_list:
        return pa.list_(base_type)

    return base_type


def infer_fhirpath_type(value: Any) -> FHIRPathType:
    """
    Infer FHIRPath type from a Python value.

    Args:
        value: A Python value.

    Returns:
        The inferred FHIRPath type.
    """
    from datetime import date, datetime, time
    from decimal import Decimal

    if value is None:
        return FHIRPathType.ANY
    # IMPORTANT: bool must be checked before int since bool is a subclass of int
    if isinstance(value, bool):
        return FHIRPathType.BOOLEAN
    if isinstance(value, int):
        return FHIRPathType.INTEGER
    if isinstance(value, float):
        return FHIRPathType.DECIMAL
    if isinstance(value, Decimal):
        return FHIRPathType.DECIMAL
    if isinstance(value, str):
        return FHIRPathType.STRING
    if isinstance(value, date) and not isinstance(value, datetime):
        return FHIRPathType.DATE
    if isinstance(value, datetime):
        return FHIRPathType.DATETIME
    if isinstance(value, time):
        return FHIRPathType.TIME
    if isinstance(value, list):
        return FHIRPathType.COLLECTION
    if isinstance(value, dict):
        return FHIRPathType.RESOURCE
    return FHIRPathType.ANY
