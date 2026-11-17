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


_CODE_RESOURCE_TYPES = ("Observation", "Condition", "Immunization", "Procedure")


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
    code_field = resource.get("code")
    if not isinstance(code_field, dict):
        return frozenset()
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
