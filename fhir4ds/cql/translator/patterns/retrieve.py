"""
Retrieve expression translator for CQL to SQL.

This module provides the RetrieveTranslator class for translating
CQL Retrieve expressions to SQL queries against FHIR resources.

Key patterns:
- Basic Retrieve: [Condition] -> SELECT FROM resources WHERE resource_type = 'Condition'
- Retrieve with ValueSet: [Condition: "Diabetes"] -> adds in_valueset filter
- Retrieve with Code: [Observation: LOINC "8480-6"] -> adds code matching
- QICore Profile filtering -> adds FHIRPath profile check
"""

from __future__ import annotations

from typing import TYPE_CHECKING, List, Optional, Union

from ...parser.ast_nodes import (
    Identifier,
    Literal,
    QualifiedIdentifier,
    Retrieve,
)
from ...translator.types import (
    PRECEDENCE,
    SQLBinaryOp,
    SQLExpression,
    SQLFunctionCall,
    SQLIdentifier,
    SQLLiteral,
    SQLQualifiedIdentifier,
    SQLSelect,
    SQLSubquery,
    SQLNull,
    SQLUnaryOp,
)

from ...translator.fhirpath_builder import build_coding_exists_expr
from ...paths import get_resource_path

if TYPE_CHECKING:
    from ...translator.context import SQLTranslationContext

import json
from pathlib import Path


# Load terminology property defaults from configuration file.
def _load_terminology_property_defaults() -> dict:
    """Load resource type to terminology property mappings from config."""
    config_path = get_resource_path("terminology", "terminology_property_defaults.json")
    if config_path.exists():
        with open(config_path) as f:
            data = json.load(f)
            data.pop("_comment", None)
            data.pop("_medication_reference_alternatives", None)
            default = data.pop("_default", "code")
            data[None] = default
            return data
    return {None: "code"}

def _load_medication_reference_alternatives() -> dict:
    """Load medication[x] reference alternative config for choice type handling."""
    config_path = get_resource_path("terminology", "terminology_property_defaults.json")
    if config_path.exists():
        with open(config_path) as f:
            data = json.load(f)
            alts = data.get("_medication_reference_alternatives", {})
            alts.pop("_comment", None)
            return alts
    return {}

_TERMINOLOGY_PROPERTY_DEFAULTS = _load_terminology_property_defaults()
_MEDICATION_REFERENCE_ALTERNATIVES = _load_medication_reference_alternatives()

# Load code system URL prefixes from configuration file
def _load_codesystem_prefixes() -> dict:
    """Load code system name-to-URL mappings from config."""
    config_path = get_resource_path("terminology", "codesystem_prefixes.json")
    if config_path.exists():
        with open(config_path) as f:
            data = json.load(f)
            data.pop("_comment", None)
            return data
    # Fallback if config file is missing
    return {
        "LOINC": "http://loinc.org",
        "SNOMED-CT": "http://snomed.info/sct",
        "SNOMED": "http://snomed.info/sct",
    }

_CODESYSTEM_PREFIXES = _load_codesystem_prefixes()


# Load valueset URL prefix configuration
def _load_valueset_prefixes() -> dict:
    """Load valueset URL prefix configuration from config."""
    config_path = get_resource_path("terminology", "valueset_prefixes.json")
    if config_path.exists():
        with open(config_path) as f:
            return json.load(f)
    return {
        "prefixes": ["http://cts.nlm.nih.gov/fhir/ValueSet/"],
        "default_prefix": "http://cts.nlm.nih.gov/fhir/ValueSet/",
    }

_VALUESET_PREFIX_CONFIG = _load_valueset_prefixes()


class RetrieveTranslator:
    """
    Translates CQL Retrieve expressions to SQL.

    CQL Retrieve expressions access clinical data from FHIR resources:
    - Basic: [Condition] - all conditions
    - With terminology: [Condition: "Diabetes"] - filtered by value set
    - With code: [Observation: LOINC "8480-6"] - filtered by specific code
    - With profile: [QICoreCondition] - filtered by profile

    The translator generates SQL that queries the resources table with
    appropriate filters for resource type, terminology, and profiles.
    """

    def __init__(self, context: SQLTranslationContext):
        """
        Initialize the retrieve translator.

        Args:
            context: The translation context for symbol and library resolution.
        """
        self.context = context

    def translate_retrieve(
        self,
        retrieve: Retrieve,
        context: Optional[SQLTranslationContext] = None,
    ) -> SQLExpression:
        """
        Translate a CQL Retrieve expression to SQL.

        Args:
            retrieve: The Retrieve AST node.
            context: Optional override context (uses self.context if None).

        Returns:
            A SQL expression representing the retrieve query.
        """
        ctx = context or self.context
        # Normalize and get optional profile URL for specific QICore types
        resource_type, profile_url = self._normalize_resource_type(retrieve.type)

        # Check for negation profile (e.g., MedicationNotRequested → doNotPerform)
        negation_filter_type = self._get_negation_filter(retrieve.type)

        # Generate alias for the resource
        alias = ctx.generate_cte_name(resource_type.lower())

        # Build the base WHERE clauses
        where_conditions: List[SQLExpression] = []

        # 1. Resource type filter
        type_filter = self._build_resource_type_filter(resource_type, alias)
        where_conditions.append(type_filter)

        # 2. Patient context filter (if in Patient context)
        if ctx.is_patient_context() and resource_type != "Patient":
            patient_filter = self._build_patient_filter(alias)
            if patient_filter:
                where_conditions.append(patient_filter)

        # 3. Terminology filter (value set or code)
        if retrieve.terminology:
            term_filter = self._build_terminology_filter(
                retrieve.terminology,
                retrieve.terminology_property or _TERMINOLOGY_PROPERTY_DEFAULTS.get(resource_type, "code"),
                alias,
                ctx,
            )
            if term_filter:
                where_conditions.append(term_filter)

        # 4. Profile filter (for QICore types with specific or generic profiles)
        profile_filter = self._build_profile_filter(resource_type, alias, profile_url)
        if profile_filter:
            where_conditions.append(profile_filter)

        # 5. Negation filter (for negation profiles like MedicationNotRequested)
        if negation_filter_type:
            neg_filter = self._build_negation_filter(negation_filter_type, alias)
            if neg_filter:
                where_conditions.append(neg_filter)
        else:
            # For base types that have negation subtypes, exclude negated resources
            excl = self._build_negation_exclusion(retrieve.type, resource_type, alias)
            if excl:
                where_conditions.append(excl)

        # Combine WHERE conditions
        where_clause = self._combine_conditions(where_conditions)

        # Build the SELECT query
        select = SQLSelect(
            columns=[SQLQualifiedIdentifier(parts=[alias, "resource"])],
            from_clause=SQLIdentifier(name="resources"),
            where=where_clause,
        )

        # Return as a subquery that can be used in larger queries
        return SQLSubquery(query=select)

    def _normalize_resource_type(self, resource_type: str) -> tuple[str, Optional[str]]:
        """
        Normalize a resource type name and optionally return a specific profile URL.

        Handles QICore prefixes, US Core profiles, and other naming conventions.

        Args:
            resource_type: The raw resource type from CQL.

        Returns:
            A tuple of (normalized FHIR resource type, optional profile URL).
            The profile URL is returned when a specific profile like
            "ConditionProblemsHealthConcerns" is referenced.
        """
        # Check for specific QICore/US Core profile mappings first
        # Uses ProfileRegistry loaded from JSON config (includes QICore prefix fallback)
        registry = self.context.profile_registry
        resolved = registry.resolve_named_profile(resource_type)
        if resolved is not None:
            return resolved

        return (resource_type, None)

    def _get_negation_filter(self, cql_type: str) -> Optional[str]:
        """Check if a CQL type is a negation profile and return the filter type."""
        registry = self.context.profile_registry
        info = registry._named_profiles.get(cql_type)
        if info and "negation_filter" in info:
            return info["negation_filter"]
        return None

    def _build_negation_filter(
        self,
        negation_type: str,
        alias: str,
    ) -> Optional[SQLExpression]:
        """Build a filter for negation profiles (doNotPerform, status not-done)."""
        resource_col = SQLQualifiedIdentifier(parts=[alias, "resource"])
        if negation_type == "doNotPerform":
            return SQLFunctionCall(
                name="fhirpath_bool",
                args=[resource_col, SQLLiteral(value="doNotPerform")],
            )
        if negation_type == "status_not_done":
            return SQLBinaryOp(
                operator="=",
                left=SQLFunctionCall(
                    name="fhirpath_text",
                    args=[resource_col, SQLLiteral(value="status")],
                ),
                right=SQLLiteral(value="not-done"),
            )
        if negation_type == "status_cancelled":
            return SQLBinaryOp(
                operator="=",
                left=SQLFunctionCall(
                    name="fhirpath_text",
                    args=[resource_col, SQLLiteral(value="status")],
                ),
                right=SQLLiteral(value="cancelled"),
            )
        return None

    def _build_negation_exclusion(
        self,
        cql_type: str,
        resource_type: str,
        alias: str,
    ) -> Optional[SQLExpression]:
        """Exclude negated resources from base type retrieves.

        When retrieving MedicationRequest (not MedicationNotRequested),
        exclude resources whose meta.profile declares the negation profile URL.
        We do NOT filter on doNotPerform here because QI-Core allows
        doNotPerform=true on the base profile — it's a data property that CQL
        authors can filter on explicitly, not a classification property.
        status_not_done is kept as it's a reliable classification signal.
        """
        registry = self.context.profile_registry
        # Check if any negation profile shares this base_type
        for name, info in registry._named_profiles.items():
            neg = info.get("negation_filter")
            if neg and info.get("base_type") == resource_type and name != cql_type:
                resource_col = SQLQualifiedIdentifier(parts=[alias, "resource"])
                conditions: list[SQLExpression] = []
                if neg == "status_not_done":
                    # Exclude status='not-done'
                    conditions.append(
                        SQLBinaryOp(
                            operator="OR",
                            left=SQLBinaryOp(
                                operator="IS",
                                left=SQLFunctionCall(
                                    name="fhirpath_text",
                                    args=[resource_col, SQLLiteral(value="status")],
                                ),
                                right=SQLNull(),
                            ),
                            right=SQLBinaryOp(
                                operator="!=",
                                left=SQLFunctionCall(
                                    name="fhirpath_text",
                                    args=[resource_col, SQLLiteral(value="status")],
                                ),
                                right=SQLLiteral(value="not-done"),
                            ),
                        )
                    )

                # Also exclude resources that declare the negation profile URL
                neg_url = info.get("url")
                if neg_url:
                    _meta_profile = SQLFunctionCall(
                        name="json_extract",
                        args=[
                            resource_col,
                            SQLLiteral(value="$.meta.profile"),
                        ],
                    )
                    conditions.append(
                        SQLBinaryOp(
                            operator="OR",
                            left=SQLBinaryOp(
                                operator="IS",
                                left=_meta_profile,
                                right=SQLNull(),
                            ),
                            right=SQLUnaryOp(
                                operator="NOT",
                                operand=SQLFunctionCall(
                                    name="list_contains",
                                    args=[
                                        SQLFunctionCall(
                                            name="from_json",
                                            args=[
                                                _meta_profile,
                                                SQLLiteral(value='["VARCHAR"]'),
                                            ],
                                        ),
                                        SQLLiteral(value=neg_url),
                                    ],
                                ),
                            ),
                        )
                    )

                if not conditions:
                    return None
                result = conditions[0]
                for cond in conditions[1:]:
                    result = SQLBinaryOp(operator="AND", left=result, right=cond)
                return result
        return None

    def _build_resource_type_filter(
        self,
        resource_type: str,
        alias: str,
    ) -> SQLExpression:
        """
        Build the resource type filter condition.

        Args:
            resource_type: The FHIR resource type.
            alias: The table alias.

        Returns:
            SQL expression for resource_type = 'Type'.
        """
        return SQLBinaryOp(
            operator="=",
            left=SQLQualifiedIdentifier(parts=[alias, "resource_type"]),
            right=SQLLiteral(value=resource_type),
            precedence=PRECEDENCE["="],
        )

    def _build_patient_filter(self, alias: str) -> Optional[SQLExpression]:
        """
        Build the patient reference filter.

        In Patient context, filters resources to the current patient.

        Args:
            alias: The table alias.

        Returns:
            SQL expression for patient filtering, or None.
        """
        # Use getvariable for patient_id session variable
        return SQLBinaryOp(
            operator="=",
            left=SQLQualifiedIdentifier(parts=[alias, "patient_ref"]),
            right=SQLFunctionCall(name="getvariable", args=[SQLLiteral(value="patient_id")]),
            precedence=PRECEDENCE["="],
        )

    def _build_terminology_filter(
        self,
        terminology: any,
        terminology_property: str,
        alias: str,
        context: SQLTranslationContext,
    ) -> Optional[SQLExpression]:
        """
        Build the terminology filter (value set or code).

        Args:
            terminology: The terminology expression (value set ref, code ref, or literal).
            terminology_property: The property to filter (e.g., 'code', 'medication').
            alias: The table alias.
            context: The translation context.

        Returns:
            SQL expression for terminology filtering, or None.
        """
        resource_col = SQLQualifiedIdentifier(parts=[alias, "resource"])

        # Handle different terminology expression types
        if isinstance(terminology, Literal):
            # String literal - treat as value set URL or name
            term_value = terminology.value
            if isinstance(term_value, str):
                # Check if it's a value set name or URL
                valueset_url = self._resolve_valueset_url(term_value, context)
                return self._build_valueset_filter(resource_col, terminology_property, valueset_url)

        elif isinstance(terminology, Identifier):
            # Identifier reference - look up value set or code
            name = terminology.name

            # Check if it's a value set reference
            if name in context.valuesets:
                valueset_url = context.valuesets[name]
                return self._build_valueset_filter(resource_col, terminology_property, valueset_url)

            # Check if it's a code reference
            if name in context.codes:
                code_info = context.codes[name]
                return self._build_code_filter_from_info(resource_col, terminology_property, code_info, context)

            # Try to resolve as a value set name
            valueset_url = self._resolve_valueset_url(name, context)
            if valueset_url:
                return self._build_valueset_filter(resource_col, terminology_property, valueset_url)

        elif isinstance(terminology, QualifiedIdentifier):
            # Qualified reference (e.g., LOINC "8480-6")
            return self._build_terminology_from_qualified(terminology, resource_col, terminology_property, context)

        elif isinstance(terminology, str):
            # Direct string - treat as value set URL
            return self._build_valueset_filter(resource_col, terminology_property, terminology)

        return None

    def _resolve_valueset_url(
        self,
        name_or_url: str,
        context: SQLTranslationContext,
    ) -> Optional[str]:
        """
        Resolve a value set name or URL to its full URL.

        Args:
            name_or_url: The value set name or URL.
            context: The translation context.

        Returns:
            The value set URL, or None if not found.
        """
        # If it looks like a URL, return as-is
        if name_or_url.startswith("http://") or name_or_url.startswith("https://"):
            return name_or_url

        # Look up in context
        if name_or_url in context.valuesets:
            return context.valuesets[name_or_url]

        # Try common value set URL prefixes from configuration
        default_prefix = _VALUESET_PREFIX_CONFIG.get("default_prefix", "")
        if default_prefix:
            return f"{default_prefix}{name_or_url}"

        return None

    def _build_valueset_filter(
        self,
        resource_col: SQLExpression,
        property_path: str,
        valueset_url: str,
    ) -> SQLExpression:
        """
        Build a value set membership filter using in_valueset UDF.

        Args:
            resource_col: The resource column AST node.
            property_path: The FHIRPath to the property (e.g., 'code').
            valueset_url: The value set URL.

        Returns:
            SQL expression for in_valueset call.
        """
        return SQLFunctionCall(
            name="in_valueset",
            args=[
                resource_col,
                SQLLiteral(value=property_path),
                SQLLiteral(value=valueset_url),
            ],
        )

    def _build_code_filter_from_info(
        self,
        resource_col: SQLExpression,
        property_path: str,
        code_info: dict,
        context: SQLTranslationContext,
    ) -> SQLExpression:
        """
        Build a code filter from code info dictionary.

        Args:
            resource_col: The resource column AST node.
            property_path: The FHIRPath to the property.
            code_info: Dictionary with code, codesystem, display.
            context: The translation context.

        Returns:
            SQL expression for code matching.
        """
        code = code_info.get("code", "")
        codesystem_name = code_info.get("codesystem", "")

        # Resolve codesystem URL
        codesystem_url = context.codesystems.get(codesystem_name, codesystem_name)
        if not codesystem_url.startswith("http"):
            # Try to resolve using common code system prefixes
            codesystem_url = _CODESYSTEM_PREFIXES.get(codesystem_name, codesystem_name)

        return self._build_code_filter(resource_col, property_path, codesystem_url, code)

    def _build_code_filter(
        self,
        resource_col: SQLExpression,
        property_path: str,
        codesystem_url: str,
        code: str,
    ) -> SQLExpression:
        """
        Build a code matching filter.

        Uses fhirpath matching for code comparison.

        Args:
            resource_col: The resource column AST node.
            property_path: The FHIRPath to the property.
            codesystem_url: The code system URL.
            code: The code value.

        Returns:
            SQL expression for code matching.
        """
        # Build FHIRPath for code matching
        # Pattern: code.coding.where(system = 'url' and code = 'value').exists()
        fhirpath_expr = build_coding_exists_expr(
            property_path, system_url=codesystem_url, code_value=code
        )

        return SQLFunctionCall(
            name="fhirpath_bool",
            args=[
                resource_col,
                SQLLiteral(value=fhirpath_expr),
            ],
        )

    def _build_terminology_from_qualified(
        self,
        qi: QualifiedIdentifier,
        resource_col: SQLExpression,
        property_path: str,
        context: SQLTranslationContext,
    ) -> Optional[SQLExpression]:
        """
        Build terminology filter from a qualified identifier.

        Handles patterns like:
        - LOINC "8480-6" (codesystem name + code literal)
        - FHIRHelpers."Some ValueSet"

        Args:
            qi: The qualified identifier.
            resource_col: The resource column AST node.
            property_path: The property path.
            context: The translation context.

        Returns:
            SQL expression for the terminology filter.
        """
        parts = qi.parts

        if len(parts) >= 2:
            first = parts[0]
            second = parts[1]

            # Check if first part is a code system
            if first in context.codesystems:
                codesystem_url = context.codesystems[first]
                return self._build_code_filter(resource_col, property_path, codesystem_url, second)

            # Check common code system prefixes
            if first in _CODESYSTEM_PREFIXES:
                codesystem_url = _CODESYSTEM_PREFIXES[first]
                return self._build_code_filter(resource_col, property_path, codesystem_url, second)

        # Fallback: treat as value set reference
        if len(parts) == 1:
            valueset_url = self._resolve_valueset_url(parts[0], context)
            if valueset_url:
                return self._build_valueset_filter(resource_col, property_path, valueset_url)

        return None

    def _build_profile_filter(
        self,
        resource_type: str,
        alias: str,
        profile_url: Optional[str] = None,
    ) -> Optional[SQLExpression]:
        """
        Build a profile filter for QICore resources.

        Uses fhirpath_bool to check if the resource conforms to the profile.

        Args:
            resource_type: The FHIR base resource type.
            alias: The table alias.
            profile_url: Optional specific profile URL. If not provided,
                         uses the generic QICore profile pattern for the type.

        Returns:
            SQL expression for profile filtering, or None.
        """
        # Use provided profile URL, or fall back to generic pattern from registry
        if profile_url is None:
            registry = self.context.profile_registry
            profile_url = registry.get_generic_profile_url(resource_type)

        if not profile_url:
            return None

        resource_col = SQLQualifiedIdentifier(parts=[alias, "resource"])

        # Build FHIRPath to check profile conformance
        # Pattern: meta.profile.contains('profile-url')
        profile_path = f"meta.profile.contains('{profile_url}')"

        return SQLFunctionCall(
            name="fhirpath_bool",
            args=[
                resource_col,
                SQLLiteral(value=profile_path),
            ],
        )

    def _combine_conditions(
        self,
        conditions: List[SQLExpression],
    ) -> Optional[SQLExpression]:
        """
        Combine multiple conditions with AND.

        Args:
            conditions: List of SQL expressions to combine.

        Returns:
            Combined AND expression, or single condition, or None.
        """
        if not conditions:
            return None

        if len(conditions) == 1:
            return conditions[0]

        # Combine all with AND
        result = conditions[0]
        for condition in conditions[1:]:
            result = SQLBinaryOp(
                operator="AND",
                left=result,
                right=condition,
                precedence=PRECEDENCE["AND"],
            )

        return result


__all__ = [
    "RetrieveTranslator",
]
