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

__all__ = ["normalize_code"]


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


def normalize_code(resource: dict) -> Optional[tuple[str, str]]:
    """Normalize the resource's primary code to ``(canonical_system, code)``.

    v1 covers the Coding-based primary code of Observation, Condition,
    Immunization, and Procedure (Procedure.code is a CodeableConcept too).
    Uses the first coding that carries both a system and a code. Returns
    None when the resource has no usable code.
    """
    if not isinstance(resource, dict):
        return None
    rtype = resource.get("resourceType")
    if rtype not in ("Observation", "Condition", "Immunization", "Procedure"):
        return None
    code_field = resource.get("code")
    if not isinstance(code_field, dict):
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
