"""PIQI Code System Identifier registry [HB pp.13-15].

The HB p.15 ``codeSystems`` JSON structure lets an evaluation profile
pass a code-system MNEMONIC and have ANY valid identifier alias for that
system validate. This module builds that registry **on top of the
FHIR4-24 standard-system registry**
(:data:`fhir4ds.cql.terminology.system_mappings.STANDARD_CODE_SYSTEM_URLS`)
so the two cannot drift: every system PIQI recognizes is a system the
rest of fhir4ds already treats as terminologically asserted.

Registry entries (deterministic, sorted by mnemonic):

``{"mnemonic", "name", "identifier", "aliases": [...],
   "terminologyServerStatus": "active"|"deprecated"}``

Lookup (:func:`resolve_code_system`) accepts the identifier, the
mnemonic, any alias, or an OID spelling (``urn:oid:...``) and returns
the registry entry — mirroring the HB's LOINC example where ``LOINC``,
``LNC``, ``http://loinc.org`` and the OID all resolve to one system.
"""

from __future__ import annotations

import functools
import typing as _t

from ..cql.terminology.system_mappings import (
    SOURCE_MNEMONIC_TO_URL,
    STANDARD_CODE_SYSTEM_URLS,
)

#: Deprecated systems (terminologyServerStatus "deprecated", HB p.15
#: example pins ICD-9-CM). Everything else in the registry is "active".
_DEPRECATED_SYSTEMS = frozenset({
    "http://hl7.org/fhir/sid/icd-9-cm",
    "http://hl7.org/fhir/sid/icd-9",
})

#: Human-readable names for the canonical systems (HB p.15 spellings
#: where the guide gives them; FHIR/offical names otherwise).
_SYSTEM_NAMES: dict[str, str] = {
    "http://loinc.org": "Logical Observation Identifiers Names and Codes",
    "http://snomed.info/sct": "SNOMED Clinical Terms",
    "http://www.nlm.nih.gov/research/umls/rxnorm": "RxNorm",
    "http://hl7.org/fhir/sid/icd-10-cm": (
        "International Classification of Diseases, Tenth Revision, "
        "Clinical Modification"),
    "http://hl7.org/fhir/sid/icd-10": (
        "International Classification of Diseases, Tenth Revision"),
    "http://hl7.org/fhir/sid/icd-9-cm": (
        "International Classification of Diseases, Ninth Revision, "
        "Clinical Modification"),
    "http://hl7.org/fhir/sid/icd-9": (
        "International Classification of Diseases, Ninth Revision"),
    "http://www.ama-assn.org/go/cpt": (
        "Current Procedural Terminology"),
    "http://hl7.org/fhir/sid/cvx": "Vaccine Administered Code Set (CVX)",
    "http://www.whocc.no/atc": "Anatomical Therapeutic Chemical (ATC)",
    "https://www.cms.gov/Medicare/Coding/HCPCSReleaseCodeSets": (
        "Healthcare Common Procedure Coding System (HCPCS)"),
    "http://hl7.org/fhir/sid/ndc": "National Drug Codes (NDC)",
    "http://terminology.hl7.org/CodeSystem/HCPCS": (
        "Healthcare Common Procedure Coding System (HCPCS)"),
    "http://hl7.org/fhir/measure": "FHIR Measure",
    "http://hl7.org/fhir/administrative-gender": "Administrative Gender",
    "http://terminology.hl7.org/CodeSystem/v3-ActCode": "v3 Act Code",
    "http://terminology.hl7.org/CodeSystem/observation-category": (
        "Observation Category"),
    "http://terminology.hl7.org/CodeSystem/condition-clinical": (
        "Condition Clinical Status Codes"),
    "http://terminology.hl7.org/CodeSystem/condition-ver-status": (
        "Condition Verification Status Codes"),
    "http://unitsofmeasure.org": "Unified Code for Units of Measure (UCUM)",
}

#: Extra alias spellings per canonical URL beyond the FHIR4-24 mnemonic
#: map (guide-attested variants, HB p.13 LOINC example).
_EXTRA_ALIASES: dict[str, tuple[str, ...]] = {
    "http://loinc.org": ("LOINC Code", "LN", "2.16.840.1.113883.6.1",
                         "urn:oid:2.16.840.1.113883.6.1"),
    "http://snomed.info/sct": ("SNOMED CT", "sct", "SNOMED",
                               "SCT", "2.16.840.1.113883.6.96",
                               "urn:oid:2.16.840.1.113883.6.96"),
    "http://hl7.org/fhir/sid/icd-10-cm": ("ICD-10-CM", "I10",
                                          "2.16.840.1.113883.6.90",
                                          "urn:oid:2.16.840.1.113883.6.90"),
    "http://hl7.org/fhir/sid/icd-9-cm": ("ICD-9-CM", "I9",
                                         "2.16.840.1.113883.6.103",
                                         "urn:oid:2.16.840.1.113883.6.103"),
    "http://www.nlm.nih.gov/research/umls/rxnorm": (
        "RxNorm", "RXNORM", "2.16.840.1.113883.6.88",
        "urn:oid:2.16.840.1.113883.6.88"),
    "http://unitsofmeasure.org": ("UCUM", "ucum"),
}


def _mnemonic_for(url: str) -> str:
    """Primary mnemonic for a canonical URL (the SOURCE_MNEMONIC_TO_URL
    key family, preferring the guide-attested spelling)."""
    preferred = {
        "http://loinc.org": "LOINC",
        "http://snomed.info/sct": "SNOMEDCT",
        "http://www.nlm.nih.gov/research/umls/rxnorm": "RXNORM",
        "http://hl7.org/fhir/sid/icd-10-cm": "ICD10CM",
        "http://hl7.org/fhir/sid/icd-10": "ICD10",
        "http://hl7.org/fhir/sid/icd-9-cm": "ICD9CM",
        "http://hl7.org/fhir/sid/icd-9": "ICD9",
        "http://www.ama-assn.org/go/cpt": "CPT",
        "http://hl7.org/fhir/sid/cvx": "CVX",
        "http://www.whocc.no/atc": "ATC",
        "https://www.cms.gov/Medicare/Coding/HCPCSReleaseCodeSets": "HCPCS",
        "http://terminology.hl7.org/CodeSystem/HCPCS": "HCPCS2",
        "http://hl7.org/fhir/sid/ndc": "NDC",
        "http://hl7.org/fhir/measure": "MEASURE",
        "http://hl7.org/fhir/administrative-gender": "ADMINGENDER",
        "http://terminology.hl7.org/CodeSystem/v3-ActCode": "V3ACTCODE",
        "http://terminology.hl7.org/CodeSystem/observation-category": (
            "OBSCATEGORY"),
        "http://terminology.hl7.org/CodeSystem/condition-clinical": (
            "CONDCLINICAL"),
        "http://terminology.hl7.org/CodeSystem/condition-ver-status": (
            "CONDVERSTATUS"),
        "http://unitsofmeasure.org": "UCUM",
    }
    if url in preferred:
        return preferred[url]
    for mnemonic, mapped in SOURCE_MNEMONIC_TO_URL.items():
        if mapped == url:
            return mnemonic
    return url.rsplit("/", 1)[-1].upper()


@functools.lru_cache(maxsize=1)
def code_system_registry() -> tuple[dict, ...]:
    """The HB p.15 ``codeSystems`` entries, sorted by mnemonic.

    Built from the FHIR4-24 standard-system registry; adding a system
    there automatically reflects here (HB: "If at some point in the
    future another valid code system identifier is defined ... it can
    easily be added to this mechanism").
    """
    entries: list[dict] = []
    for url in sorted(STANDARD_CODE_SYSTEM_URLS):
        mnemonic = _mnemonic_for(url)
        aliases: set[str] = {mnemonic, url}
        for m, mapped in SOURCE_MNEMONIC_TO_URL.items():
            if mapped == url:
                aliases.add(m)
        aliases.update(_EXTRA_ALIASES.get(url, ()))
        entries.append({
            "mnemonic": mnemonic,
            "name": _SYSTEM_NAMES.get(url, mnemonic),
            "identifier": url,
            "aliases": sorted(aliases),
            "terminologyServerStatus": (
                "deprecated" if url in _DEPRECATED_SYSTEMS else "active"),
        })
    return tuple(sorted(entries, key=lambda e: e["mnemonic"]))


@functools.lru_cache(maxsize=1)
def _lookup_index() -> dict[str, dict]:
    """identifier/mnemonic/alias (and bare-OID) spellings -> entry."""
    index: dict[str, dict] = {}
    for entry in code_system_registry():
        for spelling in (entry["mnemonic"], entry["identifier"],
                         *entry["aliases"]):
            index.setdefault(spelling, entry)
            index.setdefault(spelling.upper(), entry)
        # bare OID spellings (SystemResolver normalize maps urn:oid:...)
        for alias in entry["aliases"]:
            if alias.startswith("urn:oid:"):
                index.setdefault(alias[len("urn:oid:"):], entry)
    return index


def resolve_code_system(value: object) -> _t.Optional[dict]:
    """Resolve any valid identifier spelling to the registry entry.

    Returns ``None`` for unrecognized/non-string/empty values. Lookup
    is exact first, then upper-cased, then OID-normalized via the
    shared :class:`SystemResolver` (module-level cache; stdlib-only).
    """
    if not isinstance(value, str) or not value:
        return None
    index = _lookup_index()
    if value in index:
        return index[value]
    if value.upper() in index:
        return index[value.upper()]
    try:
        from ..cql.duckdb.udf.system_resolver import SystemResolver
    except Exception:  # pragma: no cover - defensive
        return None
    normalized = SystemResolver.normalize(value)
    if isinstance(normalized, str):
        if normalized in index:
            return index[normalized]
        if normalized.upper() in index:
            return index[normalized.upper()]
    return None


def is_recognized_code_system(value: object) -> bool:
    """True iff ``value`` resolves through the registry [HB p.15]."""
    return resolve_code_system(value) is not None


def recognized_system_strings() -> tuple[str, ...]:
    """Every identifier/alias/mnemonic spelling the registry recognizes
    (deterministic, sorted). This closure is what the
    ``Concept_HasRecognizedCodeSystem`` SQL embeds — a coding whose
    ``system`` equals ANY of these strings is recognized."""
    return tuple(sorted(_lookup_index().keys()))


def registry_document() -> dict:
    """The packaged ``codeSystems`` JSON document [HB p.15]."""
    return {"codeSystems": [dict(e) for e in code_system_registry()]}


__all__ = [
    "code_system_registry",
    "resolve_code_system",
    "is_recognized_code_system",
    "recognized_system_strings",
    "registry_document",
]
