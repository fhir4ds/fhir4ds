"""
FHIR Schema Registry for dynamic type information.

This module provides the FHIRSchemaRegistry class that loads FHIR R4
StructureDefinition JSON files and provides APIs to query:
- Choice types (e.g., value[x] -> valueQuantity, valueCodeableConcept, etc.)
- Element types (e.g., status -> code, subject -> Reference(Patient))
- Valid elements for a resource type
- Search parameter paths

This replaces hardcoded FHIR knowledge dictionaries throughout the codebase
with dynamic schema queries against the official FHIR StructureDefinitions.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from dataclasses import dataclass, field

_logger = logging.getLogger(__name__)
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from ..paths import get_resource_path

# Module-level cache: (base_path, fhir_version) → loaded resources dict
_DEFAULT_RESOURCES_CACHE: Dict[Tuple[str, str], Dict[str, "FHIRResource"]] = {}
_SCHEMA_CACHE_LOCK = threading.Lock()

# Default resources loaded when load_default_resources() is called.
# Extend this list if your CQL libraries reference additional resource types.
DEFAULT_RESOURCE_TYPES = [
    "Patient", "Observation", "Condition", "Encounter",
    "Procedure", "MedicationRequest", "DiagnosticReport",
    "ServiceRequest", "Immunization", "AllergyIntolerance",
    "Task", "Coverage",
]


@dataclass
class FHIRElement:
    """
    Represents a FHIR element from a StructureDefinition.
    
    Attributes:
        path: Full path (e.g., "Observation.value[x]")
        name: Element name (e.g., "value[x]")
        types: List of allowed types (e.g., ["Quantity", "CodeableConcept"])
        cardinality: Min..max cardinality (e.g., "0..1", "1..*")
        is_choice: Whether this is a choice type element (contains [x])
    """
    path: str
    name: str
    types: List[str] = field(default_factory=list)
    cardinality: str = "0..1"
    is_choice: bool = False


@dataclass
class FHIRResource:
    """
    Represents a FHIR resource type from a StructureDefinition.
    
    Attributes:
        name: Resource type name (e.g., "Observation")
        elements: Dictionary of element paths to FHIRElement
        choice_elements: Set of choice element names (e.g., {"value", "effective"})
    """
    name: str
    elements: Dict[str, FHIRElement] = field(default_factory=dict)
    choice_elements: Set[str] = field(default_factory=set)


class FHIRSchemaRegistry:
    """
    Registry of FHIR R4 StructureDefinitions providing dynamic type information.
    
    This class loads FHIR StructureDefinition JSON files and provides APIs to
    query type information, replacing hardcoded FHIR knowledge dictionaries.
    
    Usage:
        from ..translator.model_config import DEFAULT_MODEL_CONFIG
        registry = FHIRSchemaRegistry(model_config=DEFAULT_MODEL_CONFIG)
        registry.load_resource("Observation")
        
        # Query choice types
        types = registry.get_choice_types("Observation", "value")
        # Returns: ["Quantity", "CodeableConcept", "string", ...]
        
        # Check if element is valid
        valid = registry.is_valid_element("Observation", "status")
        # Returns: True
    """
    
    def __init__(self, fhir_version: str = "R4", model_config: Optional["ModelConfig"] = None):
        """
        Initialize the registry.
        
        Args:
            fhir_version: FHIR version (default: "R4")
            model_config: Optional ModelConfig for versioned schema resolution.
        """
        self.fhir_version = fhir_version
        self.resources: Dict[str, FHIRResource] = {}
        self._model_config = model_config
        
        legacy = get_resource_path("fhir", fhir_version.lower())
        
        if model_config is not None:
            versioned = model_config.fhir_r4_dir
            if versioned.exists():
                self._base_path = versioned
            else:
                import warnings
                warnings.warn(
                    f"Versioned schema not found at {versioned}; using legacy fhir/r4/. "
                    f"Run scripts/download_fhir_packages.py to populate versioned schema.",
                    DeprecationWarning,
                    stacklevel=2,
                )
                self._base_path = legacy
        else:
            self._base_path = legacy

        # Instance-level type config (replaces former module-level globals)
        self._type_config: dict = {}
        self._type_to_udf: Dict[str, str] = {}
        self._type_to_sql: Dict[str, str] = {}
        self._column_mappings: Optional[Dict[str, str]] = None
        self._choice_type_prefixes: Optional[Set[str]] = None
        self._load_type_config()

    def _load_type_config(self) -> None:
        """Load FHIR type→UDF and type→SQL mappings from versioned path."""
        config_path = self._base_path / "fhir_type_mappings.json"
        if not config_path.exists():
            # Fallback to legacy path
            config_path = get_resource_path("fhir", "r4", "fhir_type_mappings.json")
        if config_path.exists():
            with open(config_path) as f:
                self._type_config = json.load(f)
            mappings = self._type_config.get("type_mappings", {})
            self._type_to_udf = {k: v["udf"] for k, v in mappings.items()}
            self._type_to_sql = {k: v["sql_type"] for k, v in mappings.items()}

    @property
    def column_mappings(self) -> Dict[str, str]:
        """FHIRPath expression → precomputed column name mappings."""
        if self._column_mappings is None:
            path = self._base_path / "column_mappings.json"
            if not path.exists():
                path = get_resource_path("fhir", "r4", "column_mappings.json")
            with open(path) as f:
                raw = json.load(f)
            self._column_mappings = {k: v for k, v in raw.items() if not k.startswith("_")}
        return self._column_mappings

    @property
    def choice_type_prefixes(self) -> Set[str]:
        """Column name prefixes that indicate choice type elements."""
        if self._choice_type_prefixes is None:
            path = self._base_path / "choice_type_prefixes.json"
            if not path.exists():
                path = get_resource_path("fhir", "r4", "choice_type_prefixes.json")
            if path.exists():
                with open(path) as f:
                    data = json.load(f)
                self._choice_type_prefixes = set(data.get("prefixes", []))
            else:
                self._choice_type_prefixes = {"value", "onset", "effective", "performed"}
        return self._choice_type_prefixes

    def load_resource(self, resource_type: str) -> None:
        """
        Load a StructureDefinition JSON file for the given resource type.
        
        Args:
            resource_type: FHIR resource type (e.g., "Observation")
        """
        json_path = self._base_path / f"{resource_type}.json"
        
        if not json_path.exists():
            # Resource not found - skip silently (allow partial schema)
            return
            
        with open(json_path, 'r') as f:
            structure_def = json.load(f)
            
        resource = FHIRResource(name=resource_type)
        
        # Parse snapshot elements
        if 'snapshot' in structure_def and 'element' in structure_def['snapshot']:
            for elem_def in structure_def['snapshot']['element']:
                path = elem_def.get('path', '')
                element_id = elem_def.get('id', path)
                
                # Extract element name from path (e.g., "Observation.value[x]" -> "value[x]")
                parts = path.split('.')
                name = parts[-1] if len(parts) > 1 else path
                
                # Determine if this is a choice type
                is_choice = '[x]' in name
                
                # Extract types
                types = []
                if 'type' in elem_def:
                    for type_def in elem_def['type']:
                        type_code = type_def.get('code', '')
                        if type_code:
                            types.append(type_code)
                
                # Extract cardinality
                min_card = elem_def.get('min', 0)
                max_card = elem_def.get('max', '1')
                cardinality = f"{min_card}..{max_card}"
                
                # Create element
                element = FHIRElement(
                    path=path,
                    name=name,
                    types=types,
                    cardinality=cardinality,
                    is_choice=is_choice
                )
                
                resource.elements[path] = element
                
                # Track choice elements (without [x] suffix)
                if is_choice:
                    choice_name = name.replace('[x]', '')
                    resource.choice_elements.add(choice_name)
        
        self.resources[resource_type] = resource
        
    def load_default_resources(self) -> None:
        """
        Load commonly used FHIR resource types.
        
        Uses a module-level cache to avoid re-parsing JSON files on repeated
        instantiation (e.g., multiple evaluate_measure() calls).
        
        Loads: Patient, Observation, Condition, Encounter, Procedure,
        MedicationRequest, and other clinical resources.
        
        Raises:
            RuntimeError: If any default resource schema fails to load.
                This indicates a broken installation or missing schema files.
        """
        cache_key = (str(self._base_path), self.fhir_version)
        # Fast path: check cache without holding lock
        cached = _DEFAULT_RESOURCES_CACHE.get(cache_key)
        if cached is not None:
            self.resources.update(cached)
            return

        # Slow path: load under lock with double-checked locking
        default_resources = DEFAULT_RESOURCE_TYPES
        
        errors: list[str] = []
        for resource_type in default_resources:
            try:
                self.load_resource(resource_type)
            except Exception as e:
                errors.append(f"{resource_type}: {e}")
        
        if errors:
            raise RuntimeError(
                f"Failed to load FHIR resource schemas (broken installation?): "
                + "; ".join(errors)
            )

        with _SCHEMA_CACHE_LOCK:
            # Double-check: another thread may have populated while we loaded
            if cache_key not in _DEFAULT_RESOURCES_CACHE:
                _DEFAULT_RESOURCES_CACHE[cache_key] = dict(self.resources)
                
    def get_choice_types(self, resource_type: str, element_name: str) -> List[str]:
        """
        Get the list of possible types for a choice element.
        
        Args:
            resource_type: FHIR resource type (e.g., "Observation")
            element_name: Choice element name without [x] suffix (e.g., "value")
            
        Returns:
            List of type codes (e.g., ["Quantity", "CodeableConcept", "string"])
            Returns empty list if element is not a choice type or resource not loaded.
            
        Example:
            types = registry.get_choice_types("Observation", "value")
            # Returns: ["Quantity", "CodeableConcept", "string", ...]
        """
        resource = self.resources.get(resource_type)
        if not resource:
            return []
            
        # Look for element with [x] suffix
        choice_path = f"{resource_type}.{element_name}[x]"
        element = resource.elements.get(choice_path)
        
        if not element or not element.is_choice:
            return []
            
        return element.types
        
    def get_element_type(self, resource_type: str, element_path: str) -> Optional[str]:
        """
        Get the type of an element.

        Args:
            resource_type: FHIR resource type
            element_path: Dot-separated element path (e.g., "status" or "subject.reference")

        Returns:
            Type code (e.g., "code", "Reference", "string") or None if not found
        """
        resource = self.resources.get(resource_type)
        if not resource:
            return None

        # Try full path first
        full_path = f"{resource_type}.{element_path}"
        element = resource.elements.get(full_path)

        if element and element.types:
            return element.types[0]  # Return first type

        # Task B5: Handle choice type lookups like "effectiveDateTime" → "effective[x]"
        # If element_path looks like a concrete choice type (e.g., "effectiveDateTime"),
        # check if the choice element exists (e.g., "effective[x]")
        for choice_name in resource.choice_elements:
            # Check if element_path starts with the choice name followed by a type suffix
            if element_path.startswith(choice_name) and len(element_path) > len(choice_name):
                # Extract the type suffix (e.g., "DateTime" from "effectiveDateTime")
                type_suffix = element_path[len(choice_name):]
                # Map common type suffixes to FHIR types
                type_suffix_map = {
                    "DateTime": "dateTime",
                    "Date": "date",
                    "Period": "Period",
                    "Quantity": "Quantity",
                    "String": "string",
                    "Boolean": "boolean",
                    "Integer": "integer",
                    "Decimal": "decimal",
                    "CodeableConcept": "CodeableConcept",
                    "Reference": "Reference",
                    "Timing": "Timing",
                    "Instant": "instant",
                }
                if type_suffix in type_suffix_map:
                    return type_suffix_map[type_suffix]
                # Also try the full choice element path
                choice_path = f"{resource_type}.{choice_name}[x]"
                choice_element = resource.elements.get(choice_path)
                if choice_element and choice_element.types:
                    # Check if the type suffix matches any of the allowed types
                    for t in choice_element.types:
                        if t.lower() == type_suffix.lower():
                            return t

        return None
        
    def is_valid_element(self, resource_type: str, element_name: str) -> bool:
        """
        Check if an element name is valid for a resource type.
        
        Args:
            resource_type: FHIR resource type
            element_name: Element name (may include [x] for choice types)
            
        Returns:
            True if element exists in the resource definition
        """
        resource = self.resources.get(resource_type)
        if not resource:
            return False
            
        # Check if any element path ends with this name
        search_suffix = f".{element_name}"
        for path in resource.elements.keys():
            if path.endswith(search_suffix) or path == f"{resource_type}.{element_name}":
                return True
                
        return False
        
    def is_choice_element(self, resource_type: str, element_name: str) -> bool:
        """
        Check if an element is a choice type (has [x] suffix in definition).
        
        Args:
            resource_type: FHIR resource type
            element_name: Element name without [x] (e.g., "value", "effective")
            
        Returns:
            True if this is a choice type element
        """
        resource = self.resources.get(resource_type)
        if not resource:
            return False
            
        return element_name in resource.choice_elements
        
    def get_all_choice_elements(self, resource_type: str) -> Set[str]:
        """
        Get all choice element names for a resource type.

        Args:
            resource_type: FHIR resource type

        Returns:
            Set of choice element names (without [x] suffix)
        """
        resource = self.resources.get(resource_type)
        if not resource:
            return set()

        return resource.choice_elements.copy()

    def is_valid_precomputed_column(self, resource_type: str, column_name: str) -> bool:
        """
        Check if a column name corresponds to a valid FHIR element for the resource type.

        Maps common column names back to FHIR element paths and validates them.
        This replaces the former hardcoded valid-columns dict.

        Args:
            resource_type: FHIR resource type (e.g., "Observation")
            column_name: SQL column name (e.g., "effective_date", "status")

        Returns:
            True if the column maps to a valid FHIR element
        """
        # Column name → possible FHIR element paths (loaded from config)
        column_to_fhir_paths = self._type_config.get("column_to_fhir_paths", {})

        fhir_paths = column_to_fhir_paths.get(column_name)
        if not fhir_paths:
            return False

        for path in fhir_paths:
            if self.is_valid_element(resource_type, path):
                return True
        return False

    def get_udf_for_element(self, resource_type: str, element_path: str) -> str:
        """
        Get the appropriate fhirpath_* UDF for a resource element.

        Uses FHIR StructureDefinition to determine the element's type,
        then maps to the appropriate UDF.

        Args:
            resource_type: FHIR resource type (e.g., "Observation")
            element_path: Element path (e.g., "status", "effectiveDateTime")

        Returns:
            UDF function name (e.g., "fhirpath_date", "fhirpath_text")
            Defaults to "fhirpath_text" for unknown types.
        """
        element_type = self.get_element_type(resource_type, element_path)
        if element_type:
            return self._type_to_udf.get(element_type, "fhirpath_text")
        return "fhirpath_text"

    def get_sql_type_for_element(self, resource_type: str, element_path: str) -> str:
        """
        Get the SQL column type for a resource element.

        Args:
            resource_type: FHIR resource type
            element_path: Element path

        Returns:
            SQL type string (e.g., "DATE", "VARCHAR")
            Defaults to "VARCHAR" for unknown types.
        """
        element_type = self.get_element_type(resource_type, element_path)
        if element_type:
            return self._type_to_sql.get(element_type, "VARCHAR")
        return "VARCHAR"
