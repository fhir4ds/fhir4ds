"""
FHIR Model for fhirpathpy Engine

Provides the model structure expected by fhirpathpy for:
- Choice type resolution (Observation.value -> valueQuantity)
- Type hierarchy (is Type, as Type)
- Path-to-type mapping

This model is passed to fhirpathpy.evaluate() to enable proper
polymorphic field navigation.
"""

from __future__ import annotations

import threading
from typing import Any, Dict, List, Optional

# Import generated type data
from .fhir_types_generated import (
    CHOICE_TYPES,
    FHIR_TYPES,
    TYPE_HIERARCHY,
)


def build_fhir_model() -> Dict[str, Any]:
    """
    Build the FHIR model structure expected by fhirpathpy.

    The model contains:
    - choiceTypePaths: Maps polymorphic paths to their concrete type options
      Format: {"Observation.value": ["Quantity", "CodeableConcept", ...]}
    - path2Type: Maps paths to FHIR type names
      Format: {"Observation.valueQuantity": "Quantity", ...}
    - pathsDefinedElsewhere: Path aliases (for BackboneElement paths)
      Format: {"Observation.component": "Observation.component"}
    - type2Parent: Type inheritance hierarchy
      Format: {"Quantity": "Element", "Age": "Quantity", ...}

    Returns:
        The model dict for fhirpathpy
    """
    model: Dict[str, Any] = {
        "choiceTypePaths": {},
        "path2Type": {},
        "pathsDefinedElsewhere": {},
        "type2Parent": {},
    }

    # Build choiceTypePaths - maps base path to list of type names
    # The fhirpathpy engine expects the TYPE names, not the field names
    # e.g., "Observation.value" -> ["Quantity", "CodeableConcept", ...]
    # IMPORTANT: Only include actual choice types (with multiple type options)
    # Single-reference fields like "subject" -> ["subjectReference"] are NOT choice types
    for path, field_names in CHOICE_TYPES.items():
        # Skip non-choice types (fields with only one option that's just fieldName + Type)
        # A real choice type has multiple options like valueQuantity, valueString, etc.
        if len(field_names) <= 1:
            continue

        # Extract type names from field names
        # valueQuantity -> Quantity, valueCodeableConcept -> CodeableConcept
        type_names = []
        for field_name in field_names:
            type_name = _extract_type_from_choice_field(field_name)
            if type_name:
                type_names.append(type_name)

        if type_names:
            model["choiceTypePaths"][path] = type_names

    # Build path2Type - maps concrete field paths to their types
    # e.g., "Observation.valueQuantity" -> "Quantity"
    for path, field_names in CHOICE_TYPES.items():
        resource_prefix = path.split(".")[0]  # e.g., "Observation"
        base_field = path.split(".")[1] if "." in path else ""  # e.g., "value"

        for field_name in field_names:
            type_name = _extract_type_from_choice_field(field_name)
            if type_name:
                # Map the full path to the type
                full_path = f"{resource_prefix}.{field_name}"
                model["path2Type"][full_path] = type_name

    # Add common FHIR path-to-type mappings
    model["path2Type"].update(_get_common_path_to_type_mappings())

    # Build type2Parent from TYPE_HIERARCHY
    model["type2Parent"] = dict(TYPE_HIERARCHY)

    # Build pathsDefinedElsewhere for BackboneElement paths
    model["pathsDefinedElsewhere"] = _get_backbone_element_paths()

    return model


def _extract_type_from_choice_field(field_name: str) -> Optional[str]:
    """
    Extract the FHIR type name from a choice type field name.

    Args:
        field_name: Field name like "valueQuantity", "effectiveDateTime"

    Returns:
        Type name like "Quantity", "dateTime", or None if not found
    """
    # Common type suffixes and their FHIR type names
    # The key is the suffix to look for, value is the FHIR type
    type_suffixes = {
        # Primitive types
        "Boolean": "boolean",
        "Integer": "integer",
        "String": "string",
        "Decimal": "decimal",
        "Date": "date",
        "DateTime": "dateTime",
        "Time": "time",
        "Instant": "instant",
        "Uri": "uri",
        "Url": "url",
        "Canonical": "canonical",
        "Oid": "oid",
        "Uuid": "uuid",
        # Complex types
        "Quantity": "Quantity",
        "CodeableConcept": "CodeableConcept",
        "Coding": "Coding",
        "Code": "code",
        "Range": "Range",
        "Ratio": "Ratio",
        "Period": "Period",
        "Reference": "Reference",
        "SampledData": "SampledData",
        "Timing": "Timing",
        "Attachment": "Attachment",
        "Identifier": "Identifier",
        "HumanName": "HumanName",
        "Address": "Address",
        "ContactPoint": "ContactPoint",
        "Annotation": "Annotation",
        "Age": "Age",
        "Distance": "Distance",
        "Duration": "Duration",
        "Count": "Count",
        "Money": "Money",
        "Signature": "Signature",
        "Extension": "Extension",
        # Special
        "Resource": "Resource",
        "Base64Binary": "base64Binary",
        "Markdown": "markdown",
        "PositiveInt": "positiveInt",
        "UnsignedInt": "unsignedInt",
        "Id": "id",
    }

    # Try to match from longest suffix first (CodeableConcept before Coding)
    sorted_suffixes = sorted(type_suffixes.keys(), key=len, reverse=True)

    for suffix in sorted_suffixes:
        if field_name.endswith(suffix):
            return type_suffixes[suffix]

    return None


def _get_common_path_to_type_mappings() -> Dict[str, str]:
    """
    Get common FHIR path-to-type mappings.

    Returns:
        Dict mapping paths to FHIR type names
    """
    return {
        # Patient fields
        "Patient.name": "HumanName",
        "Patient.identifier": "Identifier",
        "Patient.telecom": "ContactPoint",
        "Patient.address": "Address",
        "Patient.photo": "Attachment",
        "Patient.contact": "Patient.contact",
        "Patient.communication": "Patient.communication",
        "Patient.link": "Patient.link",
        "Patient.maritalStatus": "CodeableConcept",
        "Patient.gender": "code",
        "Patient.birthDate": "date",
        "Patient.deceasedBoolean": "boolean",
        "Patient.deceasedDateTime": "dateTime",
        "Patient.multipleBirthBoolean": "boolean",
        "Patient.multipleBirthInteger": "integer",
        "Patient.active": "boolean",

        # Observation fields
        "Observation.identifier": "Identifier",
        "Observation.basedOn": "Reference",
        "Observation.partOf": "Reference",
        "Observation.status": "code",
        "Observation.category": "CodeableConcept",
        "Observation.code": "CodeableConcept",
        "Observation.subject": "Reference",
        "Observation.focus": "Reference",
        "Observation.encounter": "Reference",
        "Observation.effectiveDateTime": "dateTime",
        "Observation.effectivePeriod": "Period",
        "Observation.effectiveTiming": "Timing",
        "Observation.effectiveInstant": "instant",
        "Observation.issued": "instant",
        "Observation.performer": "Reference",
        "Observation.valueQuantity": "Quantity",
        "Observation.valueCodeableConcept": "CodeableConcept",
        "Observation.valueString": "string",
        "Observation.valueBoolean": "boolean",
        "Observation.valueInteger": "integer",
        "Observation.valueRange": "Range",
        "Observation.valueRatio": "Ratio",
        "Observation.valueSampledData": "SampledData",
        "Observation.valueTime": "time",
        "Observation.valueDateTime": "dateTime",
        "Observation.valuePeriod": "Period",
        "Observation.dataAbsentReason": "CodeableConcept",
        "Observation.interpretation": "CodeableConcept",
        "Observation.note": "Annotation",
        "Observation.bodySite": "CodeableConcept",
        "Observation.method": "CodeableConcept",
        "Observation.specimen": "Reference",
        "Observation.device": "Reference",
        "Observation.referenceRange": "Observation.referenceRange",
        "Observation.hasMember": "Reference",
        "Observation.derivedFrom": "Reference",
        "Observation.component": "Observation.component",

        # Extension fields
        "Extension.url": "uri",
        "Extension.valueBoolean": "boolean",
        "Extension.valueInteger": "integer",
        "Extension.valueString": "string",
        "Extension.valueDecimal": "decimal",
        "Extension.valueUri": "uri",
        "Extension.valueUrl": "url",
        "Extension.valueDateTime": "dateTime",
        "Extension.valueDate": "date",
        "Extension.valueTime": "time",
        "Extension.valueQuantity": "Quantity",
        "Extension.valueCodeableConcept": "CodeableConcept",
        "Extension.valueReference": "Reference",
        "Extension.valueAge": "Age",
        "Extension.valuePeriod": "Period",
        "Extension.valueRange": "Range",
        "Extension.valueRatio": "Ratio",
        "Extension.valueAttachment": "Attachment",
        "Extension.valueIdentifier": "Identifier",
        "Extension.valueHumanName": "HumanName",
        "Extension.valueAddress": "Address",
        "Extension.valueContactPoint": "ContactPoint",
        "Extension.valueAnnotation": "Annotation",

        # Common element types
        ".id": "id",
        ".meta": "Meta",
        ".implicitRules": "uri",
        ".language": "code",
        ".extension": "Extension",
        ".modifierExtension": "Extension",
        ".status": "code",
        ".system": "uri",
        ".value": "string",
        ".code": "code",
        ".display": "string",
        ".url": "uri",
        ".version": "string",
        ".name": "string",
        ".title": "string",
        ".description": "string",
        ".unit": "string",
    }


def _get_backbone_element_paths() -> Dict[str, str]:
    """
    Get path aliases for BackboneElement types.

    In FHIR, some nested structures are defined as BackboneElements.
    These need path aliases so fhirpathpy knows they're defined elsewhere.

    Returns:
        Dict mapping paths to their alias paths
    """
    return {
        # Observation backbone elements
        "Observation.referenceRange": "Observation.referenceRange",
        "Observation.referenceRange.low": "Quantity",
        "Observation.referenceRange.high": "Quantity",
        "Observation.referenceRange.type": "CodeableConcept",
        "Observation.referenceRange.appliesTo": "CodeableConcept",
        "Observation.referenceRange.age": "Range",
        "Observation.component": "Observation.component",
        "Observation.component.valueQuantity": "Quantity",
        "Observation.component.valueCodeableConcept": "CodeableConcept",
        "Observation.component.valueString": "string",
        "Observation.component.valueBoolean": "boolean",
        "Observation.component.valueInteger": "integer",
        "Observation.component.valueRange": "Range",
        "Observation.component.valueRatio": "Ratio",
        "Observation.component.valueSampledData": "SampledData",
        "Observation.component.valueTime": "time",
        "Observation.component.valueDateTime": "dateTime",
        "Observation.component.valuePeriod": "Period",
        "Observation.component.dataAbsentReason": "CodeableConcept",
        "Observation.component.interpretation": "CodeableConcept",
        "Observation.component.referenceRange": "Observation.referenceRange",

        # Patient backbone elements
        "Patient.contact": "Patient.contact",
        "Patient.contact.relationship": "CodeableConcept",
        "Patient.contact.name": "HumanName",
        "Patient.contact.telecom": "ContactPoint",
        "Patient.contact.address": "Address",
        "Patient.communication": "Patient.communication",
        "Patient.communication.language": "CodeableConcept",
        "Patient.link": "Patient.link",
        "Patient.link.type": "code",

        # Timing backbone elements
        "Timing.repeat": "Timing.repeat",
        "Timing.repeat.boundsDuration": "Duration",
        "Timing.repeat.boundsRange": "Range",
        "Timing.repeat.boundsPeriod": "Period",
    }


# Singleton model instance
_fhir_model: Optional[Dict[str, Any]] = None
_fhir_model_lock = threading.Lock()


def get_fhir_model() -> Dict[str, Any]:
    """
    Get the FHIR model for fhirpathpy.

    Returns a cached model instance, building it on first call.
    Thread-safe via double-checked locking.

    Returns:
        The FHIR model dict for fhirpathpy
    """
    global _fhir_model

    if _fhir_model is None:
        with _fhir_model_lock:
            if _fhir_model is None:
                _fhir_model = build_fhir_model()

    return _fhir_model


def reset_model_cache() -> None:
    """Reset the cached model (useful for testing)."""
    global _fhir_model
    with _fhir_model_lock:
        _fhir_model = None


__all__ = [
    "build_fhir_model",
    "get_fhir_model",
    "reset_model_cache",
]
