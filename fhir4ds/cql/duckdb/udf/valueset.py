"""
CQL Valueset Code Extraction UDF

Extraction-based approach: UDF extracts codes, SQL does JOIN.
This avoids O(n*m) subquery execution.

Thread-safe design: No global state, pure functions.
"""

from __future__ import annotations

import json
import logging
import re
from typing import TYPE_CHECKING, Callable, Dict, List, Set, Tuple

import orjson

from .system_resolver import SystemResolver

if TYPE_CHECKING:
    import duckdb

_logger = logging.getLogger(__name__)

# Module-level normalize helper for hot-path usage
_normalize_system = SystemResolver.normalize

_PROFILE_URL_MARKER = "/StructureDefinition/"
_PROFILE_PREFIXES = ("qicore", "uscore")

# QICore extension property -> extension URL mapping.
# Loaded as module-level constant for visibility and ease of maintenance.
# To add mappings for new profiles, extend this dict.
QICORE_EXTENSION_PROPS: dict[str, str] = {
    "notDoneReason": "http://hl7.org/fhir/us/qicore/StructureDefinition/qicore-notDoneReason",
    "doNotPerformReason": "http://hl7.org/fhir/us/qicore/StructureDefinition/qicore-doNotPerformReason",
    "reasonRefused": "http://hl7.org/fhir/us/qicore/StructureDefinition/qicore-doNotPerformReason",
}
_PROFILE_STATUS_SUFFIXES = ("notrequested", "notdone", "cancelled", "rejected")

# Canonical FHIR resource names used when deriving base resource types from
# StructureDefinition URLs. A few QI Core profiles reference resource types not
# present in the generated FHIR metadata we ship today, so they are included
# here explicitly instead of encoding profile-specific URL mappings.
_SUPPORTED_PROFILE_RESOURCE_TYPES = (
    "AllergyIntolerance",
    "Bundle",
    "CarePlan",
    "Communication",
    "CommunicationRequest",
    "Composition",
    "Condition",
    "DeviceRequest",
    "DiagnosticReport",
    "DocumentReference",
    "Encounter",
    "Immunization",
    "Location",
    "Medication",
    "MedicationAdministration",
    "MedicationRequest",
    "Observation",
    "OperationOutcome",
    "Organization",
    "Patient",
    "Practitioner",
    "Procedure",
    "ServiceRequest",
    "Specimen",
    "Task",
)

# These profile slugs identify observation-oriented or virtual profiles whose
# base resource type is not spelled out directly in the final slug token.
_PROFILE_RESOURCE_ALIASES = {
    "bmi": "Observation",
    "bloodpressure": "Observation",
    "bodyheight": "Observation",
    "bodytemperature": "Observation",
    "bodyweight": "Observation",
    "heartrate": "Observation",
    "laboratoryresultobservation": "Observation",
    "pulseoximetry": "Observation",
    "respiratoryrate": "Observation",
    "simpleobservation": "Observation",
    "smokingstatus": "Observation",
}


def _normalize_profile_token(value: str) -> str:
    """Normalize a profile slug for structural matching."""
    return re.sub(r"[^a-z0-9]", "", value.lower())


_NORMALIZED_RESOURCE_TYPES = {
    _normalize_profile_token(resource_type): resource_type
    for resource_type in _SUPPORTED_PROFILE_RESOURCE_TYPES
}


def _canonicalize_profile_url(profile_url: str) -> str:
    """Strip canonical version markers and trailing separators from a profile URL."""
    return profile_url.split("|", 1)[0].rstrip("/")


def _strip_profile_namespace(profile_slug: str) -> str:
    """Remove common profile namespace prefixes before base-type resolution."""
    for prefix in _PROFILE_PREFIXES:
        if profile_slug.startswith(prefix):
            return profile_slug[len(prefix):]
    return profile_slug


def _resolve_profile_slug(profile_slug: str) -> str | None:
    """Resolve a normalized profile slug to a FHIR base resource type."""
    resource_type = _NORMALIZED_RESOURCE_TYPES.get(profile_slug)
    if resource_type is not None:
        return resource_type

    resource_type = _PROFILE_RESOURCE_ALIASES.get(profile_slug)
    if resource_type is not None:
        return resource_type

    for suffix in _PROFILE_STATUS_SUFFIXES:
        if not profile_slug.endswith(suffix):
            continue

        stem = profile_slug[:-len(suffix)]
        if suffix == "notrequested":
            request_slug = f"{stem}request"
            resource_type = _NORMALIZED_RESOURCE_TYPES.get(request_slug)
            if resource_type is not None:
                return resource_type

        resource_type = _NORMALIZED_RESOURCE_TYPES.get(stem)
        if resource_type is not None:
            return resource_type

        resource_type = _PROFILE_RESOURCE_ALIASES.get(stem)
        if resource_type is not None:
            return resource_type

    best_match = None
    best_match_len = 0
    for normalized_name, resource_type in _NORMALIZED_RESOURCE_TYPES.items():
        if profile_slug.startswith(normalized_name) and len(normalized_name) > best_match_len:
            best_match = resource_type
            best_match_len = len(normalized_name)

    return best_match


def extractCodes(resource: str | None, path: str) -> List[Tuple[str, str]]:
    """
    Extract all (system, code) pairs from a resource at the given path.

    Returns a list of tuples: [(system, code), ...]
    Returns empty list if no codes found.

    This is used with SQL JOIN for valueset membership:
        SELECT p.id
        FROM patients p
        JOIN valueset_codes v
          ON v.system = extractCodes(p.resource, 'code.coding')[1]
         AND v.code = extractCodes(p.resource, 'code.coding')[2]
        WHERE v.valueset_url = 'http://...'
    """
    if not resource or not path:
        return []

    try:
        data = orjson.loads(resource)

        # Navigate to the code field
        codes = _extractAllCodes(data, path)
        return codes

    except (orjson.JSONDecodeError, TypeError) as e:
        _logger.warning("UDF extractCodes failed: %s", e)
        return []


def _extract_codes_from_element(element: dict) -> List[Tuple[str, str]]:
    """Extract (system, code) pairs from a CodeableConcept or Coding element."""
    codes = []
    if 'coding' in element:
        for coding in element.get('coding', []):
            if isinstance(coding, dict):
                system = coding.get('system', '')
                code = coding.get('code', '')
                if code:
                    codes.append((system, code))
    elif 'system' in element and 'code' in element:
        codes.append((element.get('system', ''), element.get('code', '')))
    return codes


def _extractAllCodes(data: dict, path: str) -> List[Tuple[str, str]]:
    """
    Extract all (system, code) pairs from a FHIR element.

    Handles:
    - CodeableConcept: { coding: [{ system, code }, ...] }
    - Coding: { system, code }
    - List of either
    - FHIR choice types: e.g. 'code' resolves to 'codeCodeableConcept', 'codeCoding'
    - QICore extension properties: e.g. 'notDoneReason' resolves to extension value
    - FHIRPath extension paths: e.g. 'extension.where(url=''...'').valueCodeableConcept'
    """
    # FHIR choice type suffixes for terminology-bearing types
    _CHOICE_SUFFIXES = ("CodeableConcept", "Coding")

    # Handle complex FHIRPath paths (e.g., "extension.where(url='...').valueCodeableConcept"
    # or "diagnosis.where(...).diagnosisCodeableConcept")
    if ".where(" in path:
        try:
            from fhir4ds.fhirpath import evaluate as fp_evaluate
            results = fp_evaluate(data, path)
            if not results:
                return []
            # Extract codes from the FHIRPath result
            codes = []
            for item in results:
                if isinstance(item, dict):
                    codes.extend(_extract_codes_from_element(item))
            return codes
        except (ImportError, ValueError, AttributeError, TypeError) as e:
            _logger.warning("_extractAllCodes FHIRPath evaluation failed: %s", e)
            return []

    # Navigate path
    current = data
    for part in path.split('.'):
        if isinstance(current, dict):
            value = current.get(part)
            if value is None:
                # Try FHIR choice type resolution (e.g., 'code' → 'codeCodeableConcept')
                for suffix in _CHOICE_SUFFIXES:
                    value = current.get(part + suffix)
                    if value is not None:
                        break
            if value is None:
                # Try QICore extension resolution
                ext_url = QICORE_EXTENSION_PROPS.get(part)
                if ext_url:
                    value = _resolve_extension_value(current, ext_url)
            current = value
        elif isinstance(current, list) and len(current) > 0:
            current = current[0].get(part) if isinstance(current[0], dict) else None
        else:
            return []

        if current is None:
            return []

    # If the value is a JSON-encoded string (e.g. from tuple fhirpath_text serialization),
    # parse it back into a dict/list so CodeableConcept extraction works.
    if isinstance(current, str):
        stripped = current.strip()
        if stripped.startswith('{') or stripped.startswith('['):
            try:
                current = orjson.loads(stripped)
            except (orjson.JSONDecodeError, ValueError) as e:
                _logger.warning("_extractAllCodes JSON parse failed: %s", e)

    codes = []

    # Handle CodeableConcept with coding array
    if isinstance(current, dict):
        if 'coding' in current:
            for coding in current.get('coding', []):
                if isinstance(coding, dict):
                    system = coding.get('system', '')
                    code = coding.get('code', '')
                    if code:
                        codes.append((system, code))
        elif 'system' in current and 'code' in current:
            # Direct Coding
            codes.append((current.get('system', ''), current.get('code', '')))

    elif isinstance(current, list):
        for item in current:
            # Parse JSON-encoded strings within lists (e.g. from tuple
            # serialization where a CodeableConcept was wrapped in a list).
            if isinstance(item, str):
                stripped = item.strip()
                if stripped.startswith('{') or stripped.startswith('['):
                    try:
                        item = orjson.loads(stripped)
                    except (orjson.JSONDecodeError, ValueError) as e:
                        _logger.warning("_extractAllCodes list item JSON parse failed: %s", e)
                        continue
            if isinstance(item, dict):
                if 'coding' in item:
                    for coding in item.get('coding', []):
                        if isinstance(coding, dict):
                            system = coding.get('system', '')
                            code = coding.get('code', '')
                            if code:
                                codes.append((system, code))
                elif 'system' in item and 'code' in item:
                    codes.append((item.get('system', ''), item.get('code', '')))

    return codes


def _resolve_extension_value(data: dict, extension_url: str):
    """
    Resolve a QICore extension property from a FHIR resource's extension array.

    Searches for an extension with the given URL and returns its value
    (trying valueCodeableConcept, valueCoding, and valueCode).
    """
    extensions = data.get('extension', [])
    if not isinstance(extensions, list):
        return None
    for ext in extensions:
        if isinstance(ext, dict) and ext.get('url') == extension_url:
            for value_key in ('valueCodeableConcept', 'valueCoding', 'valueCode'):
                val = ext.get(value_key)
                if val is not None:
                    return val
    return None


def extractFirstCode(resource: str | None, path: str) -> str | None:
    """
    Extract the first code as a JSON string for simple valueset checks.

    Returns: '{"system": "...", "code": "..."}' or NULL
    """
    codes = extractCodes(resource, path)
    if codes:
        return json.dumps({"system": codes[0][0], "code": codes[0][1]})
    return None


def extractFirstCodeSystem(resource: str | None, path: str) -> str | None:
    """Extract the first code's system from a resource at the given path."""
    codes = extractCodes(resource, path)
    if codes:
        return codes[0][0] or None
    return None


def extractFirstCodeValue(resource: str | None, path: str) -> str | None:
    """Extract the first code's value from a resource at the given path."""
    codes = extractCodes(resource, path)
    if codes:
        return codes[0][1] or None
    return None


def resolveProfileUrl(profile_url: str | None) -> str | None:
    """
    Resolve a profile URL to its FHIR base resource type.

    Args:
        profile_url: The profile URL from meta.profile

    Returns:
        The FHIR resource type name, or None if not recognized.
    """
    if not profile_url:
        return None

    canonical_url = _canonicalize_profile_url(profile_url)
    if _PROFILE_URL_MARKER not in canonical_url:
        return None

    profile_slug = _normalize_profile_token(
        canonical_url.rsplit(_PROFILE_URL_MARKER, 1)[1]
    )
    profile_slug = _strip_profile_namespace(profile_slug)
    if not profile_slug:
        return None

    return _resolve_profile_slug(profile_slug)


def createValuesetMembershipUdf(
    valueset_codes_cache: Dict[str, Set[str]]
) -> Callable[[str | None, str, str], bool]:
    """
    Create a valueset membership check function with a pre-loaded codes cache.

    This factory function creates a closure that captures the valueset codes cache,
    allowing the UDF to check membership without global state.

    Args:
        valueset_codes_cache: Dict mapping valueset URLs to sets of codes

    Returns:
        A function suitable for registration as a DuckDB UDF

    Usage:
        # After loading valuesets into the cache
        cache = {"http://example.org/ValueSet/Diabetes": {"44054006", "73211009"}}
        udf_func = createValuesetMembershipUdf(cache)
        con.create_function("fhirpath_in_valueset", udf_func)
        con.create_function("in_valueset", udf_func)  # Alias with snake_case
    """
    def fhirpath_in_valueset(resource: str | None, path: str, valueset_url: str) -> bool | None:
        """Check if a code in the resource is in the specified valueset.

        Returns None (SQL NULL) for null inputs or unknown valueset data
        per CQL three-valued logic. Returns False only when codes are
        definitively not found in a loaded valueset.
        """
        if not resource or not valueset_url:
            return None

        try:
            vs_codes = valueset_codes_cache.get(valueset_url, set())
            if not vs_codes:
                if not valueset_codes_cache:
                    _logger.warning(
                        "in_valueset called but no valueset data is loaded. "
                        "Load valuesets first with registerValuesetUdfs()."
                    )
                return None

            # Use extractCodes which handles arrays (e.g. Encounter.type)
            for system, code in extractCodes(resource, path):
                # Normalize system (OID → URL, SNOMED module → base)
                norm_system = _normalize_system(system)
                if (norm_system, code) in vs_codes:
                    return True
                # Also try the original system in case cache has unnormalized entries
                if norm_system != system and (system, code) in vs_codes:
                    return True
                # Also match on code alone when valueset entry has no system
                if ("", code) in vs_codes or (None, code) in vs_codes:
                    return True
            return False
        except (orjson.JSONDecodeError, ValueError, KeyError, TypeError, AttributeError) as e:
            _logger.warning("UDF fhirpath_in_valueset failed: %s", e)
            return None

    return fhirpath_in_valueset


# ========================================
# Registration
# ========================================

def registerValuesetUdfs(con: "duckdb.DuckDBPyConnection") -> None:
    """
    Register valueset UDFs with thread-safe design.

    No global state - all UDFs are pure functions that work
    with the valueset_codes table.

    Note: extractCodes returns List[Tuple[str, str]] which DuckDB
    cannot infer automatically. It's registered with explicit return type.

    Note: For valueset membership checking, use createValuesetMembershipUdf()
    to create a UDF with a pre-loaded codes cache, then register it separately.
    """
    # Register extractCodes with explicit return type
    # Returns a list of (system, code) tuples as VARCHAR[]
    con.create_function(
        "extractCodes",
        extractCodes,
        return_type="VARCHAR[]",
        null_handling="special"
    )
    con.create_function("extractFirstCode", extractFirstCode, null_handling="special")
    con.create_function("extractFirstCodeSystem", extractFirstCodeSystem, null_handling="special")
    con.create_function("extractFirstCodeValue", extractFirstCodeValue, null_handling="special")
    con.create_function("resolveProfileUrl", resolveProfileUrl, null_handling="special")


__all__ = [
    "extractCodes",
    "extractFirstCode",
    "extractFirstCodeSystem",
    "extractFirstCodeValue",
    "resolveProfileUrl",
    "createValuesetMembershipUdf",
    "registerValuesetUdfs",
]
