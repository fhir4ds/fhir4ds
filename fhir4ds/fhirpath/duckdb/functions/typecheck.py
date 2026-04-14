"""
FHIRPath Type Checking Functions

Provides type checking and casting functions for FHIRPath:
- is_type(value, type_name): Check if value is of FHIR type
- as_type(value, type_name): Cast to type or return empty
- get_fhir_type(value): Infer FHIR type from value structure

These functions integrate with the vendored fhirpathpy engine.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, List, Optional

if TYPE_CHECKING:
    from collections.abc import Sequence

_logger = logging.getLogger(__name__)

# Import generated FHIR types
from ..fhir_types_generated import (
    CHOICE_TYPES,
    FHIR_TYPES,
    TYPE_ALIASES,
    TYPE_HIERARCHY,
    get_choice_type_fields,
    get_type_info,
    infer_fhir_type_from_value,
    is_subclass_of,
    is_fhir_type,
    resolve_choice_type,
)


def is_type(ctx: dict, coll: List[Any], type_info: Any) -> List[bool]:
    """
    FHIRPath is() function - check if value is of a specific type.

    Usage in FHIRPath:
        Observation.value.is(Quantity)  --> true when valueQuantity exists
        @2014.is(DateTime)  --> true
        5.is(Integer)  --> true

    Args:
        ctx: Evaluation context (contains model information)
        coll: Input collection (should be singleton)
        type_info: TypeInfo object or type name string to check against

    Returns:
        List containing True if the value matches the type, False otherwise.
        Empty list if input is empty or not a singleton.
    """
    if not coll:
        return []

    if len(coll) > 1:
        raise ValueError(f"Expected singleton on left side of 'is', got {len(coll)} items")

    value = coll[0]

    # Handle TypeInfo objects from fhirpathpy
    if hasattr(type_info, 'name'):
        target_type = type_info.name
        target_namespace = getattr(type_info, 'namespace', None)
    elif isinstance(type_info, str):
        target_type = type_info
        target_namespace = None
    elif isinstance(type_info, dict):
        target_type = type_info.get('name', '')
        target_namespace = type_info.get('namespace')
    else:
        return [False]

    # Get the actual type of the value
    actual_type = _get_value_type(value, ctx)

    if actual_type is None:
        return [False]

    # Handle System namespace (FHIRPath system types)
    if target_namespace == 'System' or target_type.startswith('System.'):
        system_type = target_type.replace('System.', '')
        return [_check_system_type(value, system_type)]

    # Check type equality or inheritance
    if actual_type == target_type:
        return [True]

    # Check if actual_type is a subclass of target_type
    if is_subclass_of(actual_type, target_type):
        return [True]

    # Check if target_type is a subclass of actual_type (less common)
    if is_subclass_of(target_type, actual_type):
        return [True]

    return [False]


def as_type(ctx: dict, coll: List[Any], type_info: Any) -> List[Any]:
    """
    FHIRPath as() function - cast to type or return empty.

    Usage in FHIRPath:
        Observation.value.as(Quantity).unit  --> "mg" if valueQuantity exists
        Observation.value.as(Period).unit  --> {} (empty) if no valuePeriod

    Args:
        ctx: Evaluation context
        coll: Input collection (should be singleton)
        type_info: TypeInfo object or type name string to cast to

    Returns:
        The original collection if the type matches, empty list otherwise.
    """
    if not coll:
        return []

    if len(coll) > 1:
        raise ValueError(f"Expected singleton on left side of 'as', got {len(coll)} items")

    # Check if the type matches using is_type logic
    type_matches = is_type(ctx, coll, type_info)

    if type_matches and type_matches[0]:
        return coll

    return []


def type_fn(ctx: dict, coll: List[Any]) -> List[dict]:
    """
    FHIRPath type() function - get type information for a value.

    Usage in FHIRPath:
        @2014.type()  --> {namespace: "System", name: "DateTime"}
        Observation.value.type()  --> {namespace: "FHIR", name: "Quantity"}

    Args:
        ctx: Evaluation context
        coll: Input collection

    Returns:
        List of type info dictionaries for each value in collection.
    """
    results = []

    for value in coll:
        type_info = _get_type_info_dict(value, ctx)
        if type_info:
            results.append(type_info)

    return results


def _get_value_type(value: Any, ctx: dict) -> Optional[str]:
    """
    Get the FHIR type name for a value.

    Args:
        value: The value to type-check
        ctx: Evaluation context (may contain model)

    Returns:
        The FHIR type name, or None if unknown
    """
    # Handle ResourceNode from fhirpathpy
    if hasattr(value, 'get_type_info'):
        try:
            type_info = value.get_type_info()
            if type_info and hasattr(type_info, 'name'):
                return type_info.name
        except (ValueError, TypeError, KeyError, AttributeError) as e:
            _logger.warning("Failed to get type info from ResourceNode: %s", e)
            pass

    # Handle ResourceNode with path
    if hasattr(value, 'path') and hasattr(value, 'data'):
        path = value.path
        if path and '.' not in path:
            # Top-level path is the resource type
            return path
        # Extract type from path
        if path:
            # Path like "Observation.valueQuantity" -> "Quantity"
            parts = path.split('.')
            if len(parts) >= 2:
                last_part = parts[-1]
                # Try to match type from field name
                type_name = _extract_type_from_field_name(last_part)
                if type_name:
                    return type_name

    # Handle dict values (FHIR resources/elements)
    if isinstance(value, dict):
        if 'resourceType' in value:
            return value['resourceType']
        return infer_fhir_type_from_value(value)

    # Handle special FHIRPath types from fhirpathpy
    value_class_name = type(value).__name__

    # Map fhirpathpy internal types to FHIRPath types
    type_mappings = {
        'FP_DateTime': 'dateTime',
        'FP_Time': 'time',
        'FP_Quantity': 'Quantity',
        'FP_Type': 'Type',
        'ResourceNode': None,  # Handled above
    }

    if value_class_name in type_mappings:
        mapped = type_mappings[value_class_name]
        if mapped:
            return mapped

    # Map Python primitive types to FHIR types
    if isinstance(value, bool):
        return 'boolean'
    if isinstance(value, int):
        return 'integer'
    if isinstance(value, float):
        return 'decimal'
    if isinstance(value, str):
        # Check for date/time patterns
        import re
        if re.match(r'^\d{4}(-\d{2}(-\d{2})?)?T', value):
            return 'dateTime'
        if re.match(r'^\d{4}(-\d{2}(-\d{2})?)?$', value):
            return 'date'
        if re.match(r'^T?\d{2}(:\d{2}(:\d{2})?)?', value):
            return 'time'
        return 'string'
    if isinstance(value, list):
        return 'Collection'

    return None


def _extract_type_from_field_name(field_name: str) -> Optional[str]:
    """
    Extract the FHIR type from a choice type field name.

    Args:
        field_name: Field name like "valueQuantity", "effectiveDateTime"

    Returns:
        The type name like "Quantity", "dateTime", or None
    """
    # Common choice type suffixes and their types
    suffix_mappings = {
        'Quantity': 'Quantity',
        'CodeableConcept': 'CodeableConcept',
        'String': 'string',
        'Boolean': 'boolean',
        'Integer': 'integer',
        'Range': 'Range',
        'Ratio': 'Ratio',
        'SampledData': 'SampledData',
        'Time': 'time',
        'DateTime': 'dateTime',
        'Period': 'Period',
        'Age': 'Age',
        'Reference': 'Reference',
        'Timing': 'Timing',
        'Duration': 'Duration',
        'Instant': 'instant',
    }

    for suffix, type_name in suffix_mappings.items():
        if field_name.endswith(suffix):
            return type_name

    return None


def _check_system_type(value: Any, system_type: str) -> bool:
    """
    Check if a value matches a FHIRPath System type.

    Args:
        value: The value to check
        system_type: System type name (e.g., "DateTime", "Integer")

    Returns:
        True if the value matches the system type
    """
    value_class_name = type(value).__name__

    system_type_mappings = {
        'Boolean': (bool,),
        'Integer': (int,),
        'Decimal': (float,),
        'String': (str,),
        'DateTime': ('FP_DateTime',),
        'Time': ('FP_Time',),
        'Quantity': ('FP_Quantity',),
    }

    if system_type in system_type_mappings:
        expected = system_type_mappings[system_type]
        # Check class names for fhirpathpy types
        for exp in expected:
            if isinstance(exp, str):
                if value_class_name == exp:
                    return True
            elif isinstance(value, exp):
                # Special case: bool is subclass of int, check bool first
                if exp == int and isinstance(value, bool):
                    return system_type == 'Boolean'
                return True

    return False


def _get_type_info_dict(value: Any, ctx: dict) -> Optional[dict]:
    """
    Get type information as a dictionary for a value.

    Args:
        value: The value to get type info for
        ctx: Evaluation context

    Returns:
        Dictionary with 'namespace' and 'name' keys, or None
    """
    # Handle ResourceNode from fhirpathpy
    if hasattr(value, 'get_type_info'):
        try:
            type_info = value.get_type_info()
            if type_info:
                result = {}
                if hasattr(type_info, 'namespace'):
                    result['namespace'] = type_info.namespace
                if hasattr(type_info, 'name'):
                    result['name'] = type_info.name
                return result if result else None
        except (ValueError, TypeError, KeyError, AttributeError) as e:
            _logger.warning("Failed to get type info dict from ResourceNode: %s", e)
            pass

    # Determine namespace and name based on value type
    type_name = _get_value_type(value, ctx)

    if type_name is None:
        return None

    # Determine namespace
    # FHIRPath system types
    system_types = {'boolean', 'integer', 'decimal', 'string', 'date', 'dateTime', 'time', 'Quantity'}

    if type_name in system_types or type_name.startswith('System.'):
        namespace = 'System'
        name = type_name.replace('System.', '')
        # Capitalize system type names
        if name in ['boolean', 'integer', 'decimal', 'string', 'date', 'dateTime', 'time']:
            name = name.capitalize()
            if name == 'Datetime':
                name = 'DateTime'
        return {'namespace': namespace, 'name': name}

    # FHIR types
    if is_fhir_type(type_name):
        return {'namespace': 'FHIR', 'name': type_name}

    # Unknown type
    return {'namespace': 'FHIR', 'name': type_name}


def get_fhir_type(value: Any) -> Optional[str]:
    """
    Infer the FHIR type from a value structure.

    This is a public API wrapper around the type inference logic.

    Args:
        value: A Python value to infer type from

    Returns:
        The inferred FHIR type name, or None
    """
    return infer_fhir_type_from_value(value)


def resolve_polymorphic_field(resource_type: str, field_name: str, resource_data: dict) -> Optional[str]:
    """
    Resolve a polymorphic (choice type) field to its concrete field name.

    Args:
        resource_type: The FHIR resource type (e.g., "Observation")
        field_name: The base field name (e.g., "value")
        resource_data: The actual resource data dictionary

    Returns:
        The concrete field name that exists in the data (e.g., "valueQuantity"),
        or None if not found
    """
    return resolve_choice_type(resource_type, field_name, resource_data)


def get_polymorphic_options(resource_type: str, field_name: str) -> List[str]:
    """
    Get all possible concrete field names for a polymorphic field.

    Args:
        resource_type: The FHIR resource type
        field_name: The base field name

    Returns:
        List of concrete field names
    """
    return get_choice_type_fields(resource_type, field_name)


# Export functions for fhirpathpy integration
__all__ = [
    'is_type',
    'as_type',
    'type_fn',
    'get_fhir_type',
    'resolve_polymorphic_field',
    'get_polymorphic_options',
]
