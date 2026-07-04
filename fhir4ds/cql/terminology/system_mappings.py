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
