"""
CTE builder for retrieve optimization.

This module creates retrieve CTEs with precomputed columns.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional, Set, Tuple, TYPE_CHECKING

logger = logging.getLogger(__name__)

from .types import (
    SQLSelect,
    SQLIdentifier,
    SQLLiteral,
    SQLBinaryOp,
    SQLUnaryOp,
    SQLCast,
    SQLFunctionCall,
    SQLAlias,
    SQLQualifiedIdentifier,
    SQLRaw,
    SQLNull,
    SQLExists,
    SQLSubquery,
    SQLEvidenceItem,
)
from .column_registry import ColumnInfo
from .profile_registry import ProfileRegistry
from .column_generation import (
    ColumnDefinition,
    build_column_definitions,
    property_to_column_name,
    infer_fhirpath_function,
    infer_sql_type_from_function,
    is_choice_type_column,
)

if TYPE_CHECKING:
    from .context import SQLTranslationContext


def _build_column_expression(col_def: ColumnDefinition) -> SQLAlias:
    """Build SQL expression for a ColumnDefinition."""
    path_exprs = [
        SQLFunctionCall(
            name=col_def.fhirpath_function,
            args=[
                SQLQualifiedIdentifier(parts=["r", "resource"]),
                SQLLiteral(value=path)
            ],
        )
        for path in col_def.paths
    ]
    if len(path_exprs) == 1:
        expr = path_exprs[0]
    else:
        expr = SQLFunctionCall(name="COALESCE", args=path_exprs)
    return SQLAlias(expr=expr, alias=col_def.column_name)


def _resolve_profile_registry(context) -> "ProfileRegistry":
    """Resolve profile registry from context.

    The context is guaranteed to have a profile_registry after __post_init__
    (Context SSOT invariant). This helper handles the Optional[context] case
    for functions that accept context=None.
    """
    if context is not None and context.profile_registry is not None:
        return context.profile_registry
    # Only reachable when called without a context (e.g., standalone utility use).
    logger.warning(
        "CTE builder called without context.profile_registry; "
        "falling back to default. Fix the call site to pass context."
    )
    from .profile_registry import get_default_profile_registry
    return get_default_profile_registry()


def build_retrieve_cte(
    resource_type: str,
    valueset: Optional[str],
    properties: Set[str],
    context: Optional[SQLTranslationContext] = None,
    profile_url: Optional[str] = None,
    profile_urls: Optional[List[str]] = None,
    code_property: Optional[str] = None,
) -> Tuple[str, SQLSelect, Dict[str, ColumnInfo]]:
    """
    Build a retrieve CTE with precomputed columns.

    Creates SQL like:
        "Condition: Essential Hypertension" AS (
            SELECT DISTINCT
                r.patient_ref AS patient_id,
                r.resource,
                fhirpath_date(r.resource, 'onsetDateTime') AS onset_date,
                fhirpath_text(r.resource, 'verificationStatus.coding.code') AS verification_status
            FROM resources r
            WHERE r.resourceType = 'Condition'
              AND in_valueset(r.resource, 'code', 'http://...')
        )

    Multiple QICore profiles (e.g., ConditionEncounterDiagnosis vs ConditionProblemsHealthConcerns)
    that map to the same FHIR resource type and valueset are deduplicated into a single CTE.
    Profile-specific precomputed columns from all profiles are merged.

    Args:
        resource_type: FHIR resource type (e.g., "Condition")
        valueset: ValueSet URL or name (None for unfiltered retrieve)
        properties: Set of property paths to precompute
        context: Translation context for valueset resolution
        profile_url: Optional single FHIR profile URL (for backward compatibility)
        profile_urls: Optional list of all FHIR profile URLs to merge columns from

    Returns:
        Tuple of (cte_name, cte_ast, column_info_map)
    """
    # (debug removed)
    # Normalize profile_urls: merge single profile_url into the list
    all_profile_urls: List[str] = []
    if profile_urls:
        all_profile_urls = list(profile_urls)
    elif profile_url:
        all_profile_urls = [profile_url]

    # Debug logging for CTE building
    logger.debug(
        f"Building CTE for resource_type={resource_type}, valueset={valueset}, profiles={all_profile_urls}"
    )

    # Generate CTE name.
    # Negation profiles (MedicationNotRequested, ProcedureNotDone, etc.)
    # need separate CTEs since they have different WHERE clauses.
    #
    # _valueset_friendly_label holds the best human-readable label for the valueset
    # (CQL alias name > code display name > URL suffix).  Used both for the CTE
    # name and for the _audit_item "threshold" field.
    _valueset_friendly_label: "Optional[str]" = None
    if valueset:
        # Try to get friendly name from context
        valueset_name = None
        if context and hasattr(context, 'valuesets'):
            for name, url in context.valuesets.items():
                if url == valueset:
                    valueset_name = name
                    break

        if valueset_name:
            cte_name = f"{resource_type}: {valueset_name}"
            _valueset_friendly_label = valueset_name
            logger.debug(f"  Found valueset name '{valueset_name}' for URL '{valueset}'")
        elif valueset.startswith("urn:cql:code:") and context and hasattr(context, 'codes'):
            # Code-based retrieve: look up the code's display name
            code_display = None
            for code_name, code_info in context.codes.items():
                cs_name = code_info.get("codesystem", "")
                cs_url = context.codesystems.get(cs_name, cs_name) if hasattr(context, 'codesystems') else cs_name
                code_val = code_info.get("code", "")
                if valueset == f"urn:cql:code:{cs_url}|{code_val}":
                    code_display = code_name
                    break
            _valueset_friendly_label = code_display or valueset.split('|')[-1]
            cte_name = f"{resource_type}: {_valueset_friendly_label}"
        else:
            # Use resource type + truncated URL
            cte_name = f"{resource_type}: {valueset.split('/')[-1]}"
            logger.debug(f"  No valueset name found, using URL suffix")

        # Only add profile suffix for profiles that actually change the SQL output
        # (e.g., us-core-blood-pressure adds component columns).
        # Condition profiles (encounter vs problems) map to the same FHIR Condition
        # with identical SQL, so no suffix is needed.
        _profile_registry = _resolve_profile_registry(context)
        profile_suffix = _get_distinguishing_profile_suffix(all_profile_urls, profile_registry=_profile_registry)
        if not profile_suffix:
            # Check for negation profile suffix via registry
            for _url in all_profile_urls:
                if _url:
                    neg_suffix = _profile_registry.get_suffix(_url)
                    if neg_suffix:
                        profile_suffix = neg_suffix
                        break
        if profile_suffix:
            cte_name = f"{cte_name} ({profile_suffix})"
    else:
        cte_name = resource_type
        _profile_registry = _resolve_profile_registry(context)
        profile_suffix = _get_distinguishing_profile_suffix(all_profile_urls, profile_registry=_profile_registry)
        if profile_suffix:
            cte_name = f"{cte_name} ({profile_suffix})"

    logger.debug(f"  Generated CTE name: {cte_name}")

    # Build column list
    columns = [
        # Always include these base columns
        SQLAlias(
            expr=SQLQualifiedIdentifier(parts=["r", "patient_ref"]),
            alias="patient_id"
        ),
        SQLQualifiedIdentifier(parts=["r", "resource"]),
    ]

    # Track column info for registry
    column_info_map: Dict[str, ColumnInfo] = {}

    # Gap 6: Filter properties to only those valid for this resource type
    # Uses schema-driven validation (always available)
    fhir_schema = (context.fhir_schema if context else None)
    column_mappings = (context.column_mappings if context else None)
    choice_type_prefixes = (context.choice_type_prefixes if context else None)
    if fhir_schema is None:
        raise RuntimeError(
            "SQLTranslationContext.fhir_schema is required for build_retrieve_cte. "
            "Ensure the translator wires fhir_schema into the context."
        )
    filtered_properties = set()
    for prop in properties:
        col_name = property_to_column_name(
            prop, resource_type=resource_type,
            fhir_schema=fhir_schema, column_mappings=column_mappings,
        )
        if fhir_schema.is_valid_precomputed_column(resource_type, col_name):
            filtered_properties.add(prop)
    properties = filtered_properties

    # Build column definitions using schema-aware helper
    column_defs = build_column_definitions(
        resource_type, properties, fhir_schema=fhir_schema,
        column_mappings=column_mappings, choice_type_prefixes=choice_type_prefixes,
    )
    generated_paths: Set[str] = set()
    for col_name in sorted(column_defs):
        col_def = column_defs[col_name]
        col_expr = _build_column_expression(col_def)
        columns.append(col_expr)
        column_info_map[col_name] = ColumnInfo(
            column_name=col_name,
            fhirpath=", ".join(col_def.paths),
            sql_type=col_def.sql_type,
            is_choice_type=col_def.is_choice_type,
        )
        generated_paths.update(col_def.paths)

    # Fallback: ensure every requested property has a column
    for prop in sorted(properties):
        if prop in generated_paths:
            continue
        col_name = property_to_column_name(
            prop, resource_type=resource_type,
            fhir_schema=fhir_schema, column_mappings=column_mappings,
        )
        if col_name in column_info_map:
            continue
        if prop.count('.') == 1:
            col_ast = SQLFunctionCall(
                name="json_extract_string",
                args=[
                    SQLQualifiedIdentifier(parts=["r", "resource"]),
                    SQLLiteral(value=f"$.{prop}"),
                ],
            )
        else:
            fhirpath_func = infer_fhirpath_function(prop, resource_type=resource_type, fhir_schema=fhir_schema)
            col_ast = SQLFunctionCall(
                name=fhirpath_func,
                args=[
                    SQLQualifiedIdentifier(parts=["r", "resource"]),
                    SQLLiteral(value=prop),
                ],
            )
        columns.append(SQLAlias(expr=col_ast, alias=col_name))
        column_info_map[col_name] = ColumnInfo(
            column_name=col_name,
            fhirpath=prop,
            sql_type=infer_sql_type_from_function(col_ast.name),
            is_choice_type=is_choice_type_column(
                col_name, choice_type_prefixes=choice_type_prefixes,
            ),
        )

    # Gap 16: Add property chain columns for deep paths (2+ dots)
    for prop in sorted(properties):
        if "." not in prop:
            continue
        col_name = property_to_column_name(
            prop, resource_type=resource_type,
            fhir_schema=fhir_schema, column_mappings=column_mappings,
        )
        if col_name in column_info_map:
            continue
        if prop.count(".") == 1:
            chain_ast = SQLFunctionCall(
                name="json_extract_string",
                args=[
                    SQLQualifiedIdentifier(parts=["r", "resource"]),
                    SQLLiteral(value=f"$.{prop}"),
                ],
            )
        else:
            fhirpath_func = infer_fhirpath_function(prop, resource_type=resource_type, fhir_schema=fhir_schema)
            chain_ast = SQLFunctionCall(
                name=fhirpath_func,
                args=[
                    SQLQualifiedIdentifier(parts=["r", "resource"]),
                    SQLLiteral(value=prop),
                ],
            )
        columns.append(SQLAlias(expr=chain_ast, alias=col_name))
        column_info_map[col_name] = ColumnInfo(
            column_name=col_name,
            fhirpath=prop,
            sql_type=infer_sql_type_from_function(chain_ast.name),
            is_choice_type=is_choice_type_column(col_name),
        )

    # Build WHERE clause
    where_conditions = [
        # Filter by resource type
        SQLBinaryOp(
            operator="=",
            left=SQLQualifiedIdentifier(parts=["r", "resourceType"]),
            right=SQLLiteral(resource_type)
        )
    ]

    # Add valueset filter if present
    if valueset:
        if valueset.startswith("urn:cql:code:"):
            # Direct code reference: urn:cql:code:<system>|<code>
            parts = valueset[len("urn:cql:code:"):].split("|", 1)
            system_url = parts[0] if len(parts) > 0 else ""
            code_val = parts[1] if len(parts) > 1 else ""
            from ..translator.patterns.retrieve import _TERMINOLOGY_PROPERTY_DEFAULTS
            effective_code_property = code_property or _TERMINOLOGY_PROPERTY_DEFAULTS.get(resource_type, "code")
            fhirpath_expr = f"{effective_code_property}.coding.where(system='{system_url}' and code='{code_val}').exists()"
            where_conditions.append(
                SQLFunctionCall(
                    name="fhirpath_bool",
                    args=[
                        SQLQualifiedIdentifier(parts=["r", "resource"]),
                        SQLLiteral(fhirpath_expr),
                    ]
                )
            )
        else:
            # Use resource-type-specific code property path
            from ..translator.patterns.retrieve import _TERMINOLOGY_PROPERTY_DEFAULTS, _MEDICATION_REFERENCE_ALTERNATIVES
            effective_code_property = code_property or _TERMINOLOGY_PROPERTY_DEFAULTS.get(resource_type, "code")
            primary_check = SQLFunctionCall(
                name="in_valueset",
                args=[
                    SQLQualifiedIdentifier(parts=["r", "resource"]),
                    SQLLiteral(effective_code_property),
                    SQLLiteral(valueset)
                ]
            )
            # For medication[x] choice types, also check medicationReference
            med_ref_alt = _MEDICATION_REFERENCE_ALTERNATIVES.get(resource_type)
            if med_ref_alt and not code_property:
                ref_prop = med_ref_alt["reference_property"]
                target_type = med_ref_alt["target_type"]
                target_code = med_ref_alt["target_code_property"]
                # Match: fhirpath_text(r.resource, 'medicationReference.reference') ends with Medication.id
                # Use: LIST_EXTRACT(STR_SPLIT(ref, '/'), -1) = fhirpath_text(m.resource, 'id')
                ref_id_expr = SQLFunctionCall(
                    name="LIST_EXTRACT",
                    args=[
                        SQLFunctionCall(
                            name="STR_SPLIT",
                            args=[
                                SQLFunctionCall(
                                    name="fhirpath_text",
                                    args=[
                                        SQLQualifiedIdentifier(parts=["r", "resource"]),
                                        SQLLiteral(f"{ref_prop}.reference"),
                                    ]
                                ),
                                SQLLiteral("/"),
                            ]
                        ),
                        SQLRaw("-1"),
                    ]
                )
                ref_check = SQLExists(
                    subquery=SQLSubquery(
                        query=SQLSelect(
                            columns=[SQLLiteral("1")],
                            from_clause=SQLAlias(
                                expr=SQLIdentifier(name="resources"),
                                alias="m"
                            ),
                            where=SQLBinaryOp(
                                operator="AND",
                                left=SQLBinaryOp(
                                    operator="AND",
                                    left=SQLBinaryOp(
                                        operator="=",
                                        left=SQLQualifiedIdentifier(parts=["m", "resourceType"]),
                                        right=SQLLiteral(target_type)
                                    ),
                                    right=SQLBinaryOp(
                                        operator="=",
                                        left=ref_id_expr,
                                        right=SQLFunctionCall(
                                            name="fhirpath_text",
                                            args=[
                                                SQLQualifiedIdentifier(parts=["m", "resource"]),
                                                SQLLiteral("id"),
                                            ]
                                        )
                                    )
                                ),
                                right=SQLFunctionCall(
                                    name="in_valueset",
                                    args=[
                                        SQLQualifiedIdentifier(parts=["m", "resource"]),
                                        SQLLiteral(target_code),
                                        SQLLiteral(valueset)
                                    ]
                                )
                            )
                        )
                    )
                )
                where_conditions.append(
                    SQLBinaryOp(
                        operator="OR",
                        left=primary_check,
                        right=ref_check,
                    )
                )
            else:
                where_conditions.append(primary_check)

    # Add negation filter for negation profiles (e.g., MedicationNotRequested)
    _registry = _resolve_profile_registry(context)
    _negation_filter = None
    _is_negation = False
    for _np_name, _np_info in _registry._named_profiles.items():
        if _np_info.get("url") in all_profile_urls and "negation_filter" in _np_info:
            _negation_filter = _np_info["negation_filter"]
            _is_negation = True
            break

    if _negation_filter == "doNotPerform":
        where_conditions.append(
            SQLFunctionCall(
                name="fhirpath_bool",
                args=[
                    SQLQualifiedIdentifier(parts=["r", "resource"]),
                    SQLLiteral("doNotPerform"),
                ]
            )
        )
    elif _negation_filter == "status_not_done":
        where_conditions.append(
            SQLBinaryOp(
                operator="=",
                left=SQLFunctionCall(
                    name="fhirpath_text",
                    args=[
                        SQLQualifiedIdentifier(parts=["r", "resource"]),
                        SQLLiteral("status"),
                    ],
                ),
                right=SQLLiteral("not-done"),
            )
        )
    elif _negation_filter == "status_cancelled":
        where_conditions.append(
            SQLBinaryOp(
                operator="=",
                left=SQLFunctionCall(
                    name="fhirpath_text",
                    args=[
                        SQLQualifiedIdentifier(parts=["r", "resource"]),
                        SQLLiteral("status"),
                    ],
                ),
                right=SQLLiteral("cancelled"),
            )
        )
    elif not _is_negation:
        # For base type retrieves, exclude negated resources if a negation subtype exists.
        # We use the profile URL as the canonical discriminator: if a resource declares
        # the negation profile (e.g. qicore-servicenotrequested), exclude it.
        # We do NOT filter on doNotPerform here because QI-Core allows
        # doNotPerform=true on the base profile (e.g. qicore-servicerequest) — it's
        # a data property that CQL authors can filter on explicitly, not a
        # classification property for retrieve semantics.
        for _np_name, _np_info in _registry._named_profiles.items():
            if _np_info.get("base_type") == resource_type and "negation_filter" in _np_info:
                neg_type = _np_info["negation_filter"]
                if neg_type == "status_not_done":
                    # status=not-done is a reliable classification signal even without
                    # profile metadata, so keep it as an exclusion filter.
                    where_conditions.append(
                        SQLBinaryOp(
                            operator="OR",
                            left=SQLBinaryOp(
                                operator="IS",
                                left=SQLFunctionCall(
                                    name="fhirpath_text",
                                    args=[SQLQualifiedIdentifier(parts=["r", "resource"]), SQLLiteral("status")],
                                ),
                                right=SQLNull(),
                            ),
                            right=SQLBinaryOp(
                                operator="!=",
                                left=SQLFunctionCall(
                                    name="fhirpath_text",
                                    args=[SQLQualifiedIdentifier(parts=["r", "resource"]), SQLLiteral("status")],
                                ),
                                right=SQLLiteral(value="not-done"),
                            ),
                        )
                    )

                # Exclude resources that declare the negation profile URL
                neg_profile_url = _np_info.get("url")
                if neg_profile_url:
                    _meta_profile = SQLFunctionCall(
                        name="json_extract",
                        args=[
                            SQLQualifiedIdentifier(parts=["r", "resource"]),
                            SQLLiteral("$.meta.profile"),
                        ],
                    )
                    where_conditions.append(
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
                                                SQLLiteral('["VARCHAR"]'),
                                            ],
                                        ),
                                        SQLLiteral(neg_profile_url),
                                    ],
                                ),
                            ),
                        )
                    )
                break

    # Add meta.profile filter for non-base profiles.
    # Profile-constrained retrieves (e.g., [ConditionEncounterDiagnosis])
    # must only return resources that claim conformance to the specific profile
    # URL in their meta.profile array.  The generic/base profile for the
    # resource type (e.g., qicore-condition) does NOT get filtered — it
    # matches all resources of that type.
    if profile_url and _registry.needs_profile_filter(resource_type, profile_url):
        where_conditions.append(
            SQLFunctionCall(
                name="list_contains",
                args=[
                    SQLFunctionCall(
                        name="from_json",
                        args=[
                            SQLFunctionCall(
                                name="json_extract",
                                args=[
                                    SQLQualifiedIdentifier(parts=["r", "resource"]),
                                    SQLLiteral("$.meta.profile"),
                                ],
                            ),
                            SQLLiteral('["VARCHAR"]'),
                        ],
                    ),
                    SQLLiteral(profile_url),
                ],
            )
        )

    # Add audit evidence item column when audit_mode is enabled
    if context and context.audit_mode:
        # Build CQL retrieve syntax: [TypeAlias: "ValueSetName"]
        # Resolve profile URL → CQL type alias (e.g., ConditionEncounterDiagnosis)
        _type_alias = resource_type
        _registry = _resolve_profile_registry(context)
        if _registry and all_profile_urls:
            for _purl in all_profile_urls:
                _alias = _registry.get_type_alias(_purl) if _purl else None
                if _alias:
                    _type_alias = _alias
                    break
        if _valueset_friendly_label:
            right_label = f'[{_type_alias}: "{_valueset_friendly_label}"]'
        else:
            right_label = f'[{_type_alias}]'

        # Store the retrieve syntax on the context so that definition-level
        # evidence (Strategy 2) can display the CQL retrieve syntax in
        # the 'right' field instead of the raw definition CTE name.
        if not hasattr(context, '_retrieve_right_labels'):
            context._retrieve_right_labels = {}
        context._retrieve_right_labels[cte_name] = right_label
        audit_item = SQLEvidenceItem(
            target=SQLBinaryOp(
                operator="||",
                left=SQLBinaryOp(
                    operator="||",
                    left=SQLQualifiedIdentifier(parts=["r", "resourceType"]),
                    right=SQLLiteral("/"),
                ),
                right=SQLFunctionCall(
                    name="fhirpath_text",
                    args=[
                        SQLQualifiedIdentifier(parts=["r", "resource"]),
                        SQLLiteral("id"),
                    ],
                ),
            ),
            attribute=SQLLiteral(code_property) if code_property else SQLNull(),
            value=SQLNull(),
            operator_str="exists",
            threshold=SQLLiteral(right_label),
        )
        columns.append(SQLAlias(expr=audit_item, alias="_audit_item"))

    # Combine WHERE conditions with AND
    where_clause = where_conditions[0]
    for condition in where_conditions[1:]:
        where_clause = SQLBinaryOp(
            operator="AND",
            left=where_clause,
            right=condition
        )

    # Build SELECT
    cte_ast = SQLSelect(
        columns=columns,
        from_clause=SQLAlias(expr=SQLIdentifier(name="resources"), alias="r", implicit_alias=True),
        where=where_clause,
        distinct=True  # Avoid duplicates
    )

    return cte_name, cte_ast, column_info_map


# Profiles that require distinguishing suffixes because they add unique precomputed columns
# to retrieve CTEs. Most QICore profiles (like ConditionEncounterDiagnosis vs ConditionProblemsHealthConcerns)
# map to the same FHIR resource with identical SQL, so no suffix is needed.
# Only profiles that change the SQL output (like us-core-blood-pressure with BP component columns)
# should get a suffix.
# Profile suffix resolution delegated to ProfileRegistry.get_suffix() (B-6 migration complete).


def _get_distinguishing_profile_suffix(
    profile_urls: List[str],
    profile_registry=None,
) -> Optional[str]:
    """
    Get a distinguishing suffix for profiles that change SQL output.

    Most QICore profiles for the same FHIR resource type (e.g., ConditionEncounterDiagnosis
    vs ConditionProblemsHealthConcerns) produce identical SQL queries. Only profiles that
    add unique precomputed columns need a distinguishing suffix.

    Args:
        profile_urls: List of profile URLs to check
        profile_registry: ProfileRegistry to use; falls back to default if None.

    Returns:
        Suffix string (e.g., "us-core-blood-pressure") or None if no suffix needed

    Example:
        >>> _get_distinguishing_profile_suffix(["http://hl7.org/fhir/us/core/StructureDefinition/us-core-blood-pressure"])
        'us-core-blood-pressure'
        >>> _get_distinguishing_profile_suffix(["http://hl7.org/fhir/us/qicore/StructureDefinition/qicore-condition-encounter-diagnosis"])
        None  # No suffix - same SQL as other Condition profiles
    """
    if not profile_urls:
        return None

    registry = profile_registry or _resolve_profile_registry(None)
    for url in profile_urls:
        suffix = registry.get_suffix(url)
        if suffix is not None:
            return suffix

    return None


def build_patient_demographics_cte() -> Tuple[str, SQLSelect, Dict[str, ColumnInfo]]:
    """
    Build a patient demographics CTE with precomputed birthDate.

    This CTE is used for birthday-aware age calculations when AgeInYearsAt
    or similar functions are used in population mode. Instead of creating
    a correlated subquery for each row, we pre-compute birthDate once per
    patient.

    Creates SQL like:
        _patient_demographics AS (
            SELECT
                r.patient_ref AS patient_id,
                r.resource,
                fhirpath_date(r.resource, 'birthDate') AS birth_date
            FROM resources r
            WHERE r.resourceType = 'Patient'
        )

    Returns:
        Tuple of (cte_name, cte_ast, column_info_map)

    Note:
        The CTE is named with underscore prefix to avoid collision with
        user-defined CTEs. The birth_date column is pre-computed using
        fhirpath_date for efficient age calculations.
    """
    cte_name = "_patient_demographics"

    # Build column list
    columns = [
        SQLAlias(
            expr=SQLQualifiedIdentifier(parts=["r", "patient_ref"]),
            alias="patient_id"
        ),
        SQLQualifiedIdentifier(parts=["r", "resource"]),
        SQLAlias(
            expr=SQLFunctionCall(
                    name="fhirpath_date",
                    args=[
                        SQLQualifiedIdentifier(parts=["r", "resource"]),
                        SQLLiteral("birthDate")
                    ]
                ),
            alias="birth_date"
        ),
    ]

    # Column info for registry
    column_info_map: Dict[str, ColumnInfo] = {
        "birth_date": ColumnInfo(
            column_name="birth_date",
            fhirpath="birthDate",
            sql_type="VARCHAR",
            is_choice_type=False,
        ),
    }

    # WHERE clause: only Patient resources
    where_clause = SQLBinaryOp(
        operator="=",
        left=SQLQualifiedIdentifier(parts=["r", "resourceType"]),
        right=SQLLiteral("Patient")
    )

    # Build SELECT
    cte_ast = SQLSelect(
        columns=columns,
        from_clause=SQLAlias(expr=SQLIdentifier(name="resources"), alias="r", implicit_alias=True),
        where=where_clause,
        distinct=True
    )

    return cte_name, cte_ast, column_info_map
