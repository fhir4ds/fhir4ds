"""
Helpers for mapping FHIRPath properties to precomputed column metadata.

This module centralizes the logic that was previously split across
`cte_builder.py` and the hardcoded `CHOICE_TYPE_COLUMNS` dictionary.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Dict, List, Optional, Set

from ..translator.fhir_schema import FHIRSchemaRegistry

if TYPE_CHECKING:
    from ..translator.profile_registry import ProfileRegistry

# -------------------------------------------------------------------
# Column mapping utilities
# -------------------------------------------------------------------

def property_to_column_name(
    property_path: str,
    resource_type: Optional[str] = None,
    fhir_schema: Optional[FHIRSchemaRegistry] = None,
    column_mappings: Optional[Dict[str, str]] = None,
) -> str:
    """
    Convert a FHIRPath property to the precomputed column name.

    Prioritizes the JSON mapping first, then falls back to schema-driven heuristics.
    """
    mappings = column_mappings or (fhir_schema.column_mappings if fhir_schema else {})
    if property_path in mappings:
        return mappings[property_path]

    last_segment = property_path.split(".")[-1]
    if fhir_schema and resource_type:
        element_type = fhir_schema.get_element_type(resource_type, property_path)
        if element_type in {"dateTime", "date", "instant", "Period"}:
            base = last_segment
            if base.endswith("DateTime"):
                base = base[:-8]
            return camel_to_snake(base) + "_date"

    return camel_to_snake(last_segment)


def camel_to_snake(name: str) -> str:
    """Convert CamelCase to snake_case.

    Kept here to avoid circular imports (types -> column_generation -> ast_utils -> types).
    """
    import re
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()


# -------------------------------------------------------------------
# Component.where (BP) helpers - loaded from configuration
# -------------------------------------------------------------------

def _load_component_codes() -> dict:
    """Load component LOINC code mappings from config."""
    config_path = (
        Path(__file__).parent.parent
        / "resources" / "terminology" / "component_codes.json"
    )
    if config_path.exists():
        with open(config_path) as f:
            data = json.load(f)
            data.pop("_comment", None)
            return data
    return {}

_COMPONENT_CODES = _load_component_codes()

# FHIRPath strings and column names for component.where patterns, loaded from config
BP_COMPONENT_PROPERTY_PATHS = {
    entry["fhirpath"]
    for entry in _COMPONENT_CODES.values()
    if "fhirpath" in entry
}

_COMPONENT_FHIRPATH_TO_COLUMN: Dict[str, str] = {
    entry["fhirpath"]: entry["column"]
    for entry in _COMPONENT_CODES.values()
    if "fhirpath" in entry and "column" in entry
}

def is_component_where_pattern(property_path: str) -> bool:
    return "component.where(" in property_path

def resolve_component_column_name(property_path: str) -> Optional[str]:
    return _COMPONENT_FHIRPATH_TO_COLUMN.get(property_path)

# -------------------------------------------------------------------
# Column definition helpers
# -------------------------------------------------------------------

def is_choice_type_column(
    column_name: str,
    choice_type_prefixes: Optional[Set[str]] = None,
    fhir_schema: Optional[FHIRSchemaRegistry] = None,
) -> bool:
    prefixes = (
        choice_type_prefixes
        or (fhir_schema.choice_type_prefixes if fhir_schema else None)
        or {"value", "onset", "effective", "performed"}
    )
    lower = column_name.lower()
    return any(lower.startswith(prefix) or lower == prefix for prefix in prefixes)

def infer_sql_type_from_function(name: str) -> str:
    lower = name.lower()
    if "date" in lower:
        # CQL temporal values are now VARCHAR ISO 8601 strings to preserve
        # precision.  Using DATE here would cause type mismatches in COALESCE
        # and comparisons with VARCHAR CQL datetime literals.
        return "VARCHAR"
    if "bool" in lower:
        return "BOOLEAN"
    if "quantity" in lower or "number" in lower:
        return "DECIMAL"
    return "VARCHAR"

def infer_fhirpath_function(
    property_path: str,
    resource_type: Optional[str] = None,
    fhir_schema: Optional[FHIRSchemaRegistry] = None,
) -> str:
    """
    Infer the fhirpath_* function name for a property.

    Falls back to `fhirpath_text`.
    """
    if fhir_schema and resource_type:
        udf = fhir_schema.get_udf_for_element(resource_type, property_path)
        if udf:
            return udf
    return "fhirpath_text"

@dataclass
class ColumnDefinition:
    column_name: str
    paths: List[str]
    fhirpath_function: str
    sql_type: str
    is_choice_type: bool

def build_column_definitions(
    resource_type: str,
    property_paths: Set[str],
    fhir_schema: Optional[FHIRSchemaRegistry] = None,
    column_mappings: Optional[Dict[str, str]] = None,
    choice_type_prefixes: Optional[Set[str]] = None,
) -> Dict[str, ColumnDefinition]:
    """
    Build column metadata for the given properties.
    """
    if fhir_schema is None:
        raise ValueError(
            "build_column_definitions requires fhir_schema. "
            "Ensure translator initializes FHIRSchemaRegistry via ModelConfig."
        )

    grouped: Dict[str, List[str]] = {}
    for prop in sorted(property_paths):
        col_name = resolve_component_column_name(prop)
        if col_name is None:
            col_name = property_to_column_name(
                prop, resource_type=resource_type,
                fhir_schema=fhir_schema, column_mappings=column_mappings,
            )
            if not fhir_schema.is_valid_precomputed_column(resource_type, col_name):
                continue
        grouped.setdefault(col_name, []).append(prop)

    result: Dict[str, ColumnDefinition] = {}
    for col_name, paths in grouped.items():
        fhirpath_function = infer_fhirpath_function(paths[0], resource_type=resource_type, fhir_schema=fhir_schema)
        if any(is_component_where_pattern(p) for p in paths):
            fhirpath_function = "fhirpath_number"
        sql_type = infer_sql_type_from_function(fhirpath_function)
        result[col_name] = ColumnDefinition(
            column_name=col_name,
            paths=paths,
            fhirpath_function=fhirpath_function,
            sql_type=sql_type,
            is_choice_type=is_choice_type_column(
                col_name,
                choice_type_prefixes=choice_type_prefixes,
                fhir_schema=fhir_schema,
            ),
        )
    return result

def get_default_property_paths(
    resource_type: str,
    profile_url: Optional[str] = None,
    fhir_schema: Optional[FHIRSchemaRegistry] = None,
    profile_registry: Optional["ProfileRegistry"] = None,
) -> Set[str]:
    """
    Default property paths to precompute for translator-managed CTEs.
    """
    column_mappings = fhir_schema.column_mappings if fhir_schema else {}
    paths = set(column_mappings.keys())
    if profile_url and resource_type == "Observation" and profile_registry:
        keywords = profile_registry.component_profile_keywords
        if any(kw in profile_url for kw in keywords):
            paths |= BP_COMPONENT_PROPERTY_PATHS
    return paths
