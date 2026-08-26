"""Shared UMLS source-mnemonic -> FHIR canonical URL map.

Canonical home for the mnemonic translation table used to expand
medterm4ds ``code.source`` values (``SNOMEDCT_US``, ``RXNORM``, ``LNC``,
...) into their FHIR canonical URLs (``http://snomed.info/sct``, ...).

Historically this map lived privately inside
:mod:`fhir4ds.cql.terminology.in_process_adapter` (``_SOURCE_MNEMONIC_TO_URL``).
Phase 4's notes-pipeline also needs it, so it was promoted here as the
shared public location to avoid private-import coupling between the two
modules. The table itself is UMLS/medterm4ds-specific terminology
knowledge (which is why it isn't part of the generic
:class:`SystemResolver`).
"""

from __future__ import annotations

#: medterm4ds source-mnemonic -> FHIR canonical URL.
#:
#: ``SystemResolver.normalize()`` is a no-op for these mnemonic strings,
#: so without translation here the resulting CodeRef.system would silently
#: fail to join against valueset_codes rows that use
#: ``http://snomed.info/sct``.
SOURCE_MNEMONIC_TO_URL: dict[str, str] = {
    "SNOMEDCT_US": "http://snomed.info/sct",
    "SNOMEDCT": "http://snomed.info/sct",
    "RXNORM": "http://www.nlm.nih.gov/research/umls/rxnorm",
    "LNC": "http://loinc.org",
    "LOINC": "http://loinc.org",
    "ICD10CM": "http://hl7.org/fhir/sid/icd-10-cm",
    "ICD10": "http://hl7.org/fhir/sid/icd-10",
    "ICD9CM": "http://hl7.org/fhir/sid/icd-9-cm",
    "ICD9": "http://hl7.org/fhir/sid/icd-9-cm",
    "CPT": "http://www.ama-assn.org/go/cpt",
    "CVX": "http://hl7.org/fhir/sid/cvx",
    "ATC": "http://www.whocc.no/atc",
    "HCPCS": "https://www.cms.gov/Medicare/Coding/HCPCSReleaseCodeSets",
    "NDC": "http://hl7.org/fhir/sid/ndc",
    "MEASURE": "http://hl7.org/fhir/measure",
}

#: Coarse category hint -> medterm4ds source mnemonics. Intentionally
#: permissive: unknown categories fall through to ``None`` ("all sources").
CATEGORY_TO_SOURCES: dict[str, tuple[str, ...]] = {
    "condition": ("SNOMEDCT_US",),
    "medication": ("RXNORM",),
    "lab": ("LNC",),
    "loinc": ("LNC",),
    "snomed": ("SNOMEDCT_US",),
    "rxnorm": ("RXNORM",),
    "icd10": ("ICD10CM",),
    "icd10cm": ("ICD10CM",),
}


def category_to_source_mnemonics(category: str) -> tuple[str, ...] | None:
    """Map a coarse category hint to medterm4ds source mnemonics.

    Returns ``None`` for unknown/empty categories — medterm4ds interprets
    that as "search all sources".
    """
    if not category:
        return None
    return CATEGORY_TO_SOURCES.get(category.lower())


def category_to_system_param(category: str) -> str | None:
    """Map a coarse category hint to a FHIR ``system`` parameter value.

    medterm4ds 0.0.2 HTTP ``$search`` reads ``system`` (canonical URL),
    not the old ``category`` hint. Returns a comma-joined canonical URL
    list, or ``None`` when the category is unknown/empty (all-systems is
    the medterm semantic in that case — omit the param entirely).
    """
    mnemonics = category_to_source_mnemonics(category)
    if not mnemonics:
        return None
    urls = [SOURCE_MNEMONIC_TO_URL[m] for m in mnemonics if m in SOURCE_MNEMONIC_TO_URL]
    return ",".join(urls) if urls else None
