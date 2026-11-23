"""Code normalization for the temporal-dedup pipeline (AMUX-142 slice 1).

System canonicalization only (design §1.1 recommendation, Q4 approved):
OID → canonical URL, SNOMED module-URL folding, UMLS mnemonic → canonical
URL. The code itself passes through unchanged. ``(system', code)`` is the
Stage-1 partition key component.
"""

from __future__ import annotations

from typing import Optional

from fhir4ds.cql.duckdb.udf.system_resolver import SystemResolver
from fhir4ds.cql.terminology.system_mappings import SOURCE_MNEMONIC_TO_URL

__all__ = ["normalize_code", "normalize_codes"]


def _normalize_system(system: Optional[str]) -> Optional[str]:
    if not isinstance(system, str) or not system:
        return None
    # Mnemonic systems first: SystemResolver.normalize is a passthrough for
    # them, so without this step 'LNC' would never join 'http://loinc.org'.
    canonical = SOURCE_MNEMONIC_TO_URL.get(system)
    if canonical is not None:
        return canonical
    resolved = SystemResolver.normalize(system)
    return resolved if isinstance(resolved, str) else None


_CODE_RESOURCE_TYPES = ("Observation", "Condition", "Immunization", "Procedure",
                        # AMUX-150 chunk A (FEATURE_NON_CODED_DEDUP §2.1):
                        "MedicationRequest", "MedicationDispense",
                        "MedicationAdministration", "DiagnosticReport")

#: FHIR element carrying the primary code per resource type. Every type in
#: scope except Immunization uses ``code``; Immunization carries its vaccine
#: code on ``vaccineCode`` (FHIR R4) — without this mapping an Immunization's
#: canonical code set is always empty, and empty sets never union (design
#: §10), so no Immunization could ever dedup despite being approved v1 scope
#: (design §1.2 / §9 Q3). The three medication types carry their coded
#: medication[x] choice on ``medicationCodeableConcept`` (the reference arm
#: is resolved separately by the AMUX-150 bounded resolver).
_CODE_FIELD_BY_TYPE: dict[str, str] = {
    "Observation": "code",
    "Condition": "code",
    "Procedure": "code",
    "Immunization": "vaccineCode",
    "MedicationRequest": "medicationCodeableConcept",
    "MedicationDispense": "medicationCodeableConcept",
    "MedicationAdministration": "medicationCodeableConcept",
    "DiagnosticReport": "code",
}


def _code_field(resource: dict) -> Optional[dict]:
    rtype = resource.get("resourceType")
    field_name = _CODE_FIELD_BY_TYPE.get(rtype) if isinstance(rtype, str) else None
    if field_name is None:
        return None
    code_field = resource.get(field_name)
    return code_field if isinstance(code_field, dict) else None


def _normalize_concept(code_field: dict) -> frozenset[tuple[str, str]]:
    """Normalize ALL codings of one CodeableConcept to the canonical
    ``(canonical_system, code)`` set (shared by resource-level extraction
    and the AMUX-150 medication-reference resolver)."""
    codings = code_field.get("coding")
    if not isinstance(codings, list):
        return frozenset()
    keys: set[tuple[str, str]] = set()
    for coding in codings:
        if not isinstance(coding, dict):
            continue
        code = coding.get("code")
        system = coding.get("system")
        if not isinstance(code, str) or not code:
            continue
        canonical_system = _normalize_system(system)
        if canonical_system is None:
            continue
        keys.add((canonical_system, code))
    return frozenset(keys)


def normalize_codes(resource: dict) -> frozenset[tuple[str, str]]:
    """Normalize ALL codings of the resource's primary code to a canonical
    ``(canonical_system, code)`` SET (AMUX-142 addendum: code-key semantics
    are canonical code SETS with any-intersection matching, so a
    LOINC-primary resource carrying a SNOMED translation coding still
    partitions with its SNOMED-primary duplicate).

    Every coding passes its system through SystemResolver.normalize() (+ UMLS
    mnemonics); the code itself passes through unchanged. Codings without a
    usable system are skipped. Returns an empty set when the resource has no
    usable codings — empty sets never intersect (each such record stays its
    own candidate group).
    """
    if not isinstance(resource, dict):
        return frozenset()
    rtype = resource.get("resourceType")
    if rtype not in _CODE_RESOURCE_TYPES:
        return frozenset()
    code_field = _code_field(resource)
    if code_field is None:
        return frozenset()
    return _normalize_concept(code_field)


def medication_code_keys(medication: dict) -> frozenset[tuple[str, str]]:
    """Canonical code set of a (referenced) Medication resource's ``code``
    element — the AMUX-150 bounded resolver's coding source. Medication is
    deliberately NOT a dedup resource type (it is a reference target, not a
    clinical event), so this helper reads the ``code`` field directly."""
    if not isinstance(medication, dict):
        return frozenset()
    if medication.get("resourceType") != "Medication":
        return frozenset()
    code_field = medication.get("code")
    if not isinstance(code_field, dict):
        return frozenset()
    return _normalize_concept(code_field)


def normalize_code(resource: dict) -> Optional[tuple[str, str]]:
    """Compat shim preserving slice-1 semantics: the FIRST coding (in
    authored order) that carries both a canonicalizable system and a code,
    or None. The Stage-1 partition uses the full :func:`normalize_codes`
    set instead."""
    if not isinstance(resource, dict):
        return None
    rtype = resource.get("resourceType")
    if rtype not in _CODE_RESOURCE_TYPES:
        return None
    code_field = _code_field(resource)
    if code_field is None:
        return None
    codings = code_field.get("coding")
    if not isinstance(codings, list):
        return None
    for coding in codings:
        if not isinstance(coding, dict):
            continue
        code = coding.get("code")
        system = coding.get("system")
        if not isinstance(code, str) or not code:
            continue
        canonical_system = _normalize_system(system)
        if canonical_system is None:
            continue
        return canonical_system, code
    return None
