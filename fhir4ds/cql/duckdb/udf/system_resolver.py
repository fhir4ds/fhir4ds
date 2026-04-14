"""
Terminology System Resolver

Provides bidirectional OID ↔ Canonical URL normalization for FHIR code systems.
Used by in_valueset and other terminology functions to match codes across
different system identifier formats (OIDs vs URLs).
"""

from __future__ import annotations

import re
from typing import Optional


class SystemResolver:
    """Normalizes code system identifiers to canonical URLs.

    Handles three normalization cases:
    1. OID → URL: ``urn:oid:2.16.840.1.113883.6.96`` → ``http://snomed.info/sct``
    2. SNOMED module URLs: ``http://snomed.info/sct/731000124108`` → ``http://snomed.info/sct``
    3. Passthrough: already-canonical URLs are returned unchanged.
    """

    _OID_TO_URL: dict[str, str] = {
        # SNOMED CT
        "urn:oid:2.16.840.1.113883.6.96": "http://snomed.info/sct",
        # LOINC
        "urn:oid:2.16.840.1.113883.6.1": "http://loinc.org",
        # RxNorm
        "urn:oid:2.16.840.1.113883.6.88": "http://www.nlm.nih.gov/research/umls/rxnorm",
        # ICD-10-CM
        "urn:oid:2.16.840.1.113883.6.90": "http://hl7.org/fhir/sid/icd-10-cm",
        # ICD-10
        "urn:oid:2.16.840.1.113883.6.3": "http://hl7.org/fhir/sid/icd-10",
        # ICD-9-CM
        "urn:oid:2.16.840.1.113883.6.103": "http://hl7.org/fhir/sid/icd-9-cm",
        # CPT
        "urn:oid:2.16.840.1.113883.6.12": "http://www.ama-assn.org/go/cpt",
        # HCPCS
        "urn:oid:2.16.840.1.113883.6.285": "https://www.cms.gov/Medicare/Coding/HCPCSReleaseCodeSets",
        "urn:oid:2.16.840.1.113883.6.14": "http://terminology.hl7.org/CodeSystem/HCPCS",
        # CVX (vaccines)
        "urn:oid:2.16.840.1.113883.12.292": "http://hl7.org/fhir/sid/cvx",
        # NDC
        "urn:oid:2.16.840.1.113883.6.69": "http://hl7.org/fhir/sid/ndc",
        # AdministrativeGender
        "urn:oid:2.16.840.1.113883.4.642.3.1": "http://hl7.org/fhir/administrative-gender",
        # ActCode
        "urn:oid:2.16.840.1.113883.5.4": "http://terminology.hl7.org/CodeSystem/v3-ActCode",
        # Observation Category
        "urn:oid:2.16.840.1.113883.4.642.1.1125": "http://terminology.hl7.org/CodeSystem/observation-category",
        # Condition Clinical Status
        "urn:oid:2.16.840.1.113883.4.642.1.1074": "http://terminology.hl7.org/CodeSystem/condition-clinical",
        # Condition Verification Status
        "urn:oid:2.16.840.1.113883.4.642.1.1075": "http://terminology.hl7.org/CodeSystem/condition-ver-status",
    }

    # Reverse mapping for URL → OID lookups
    _URL_TO_OID: dict[str, str] = {v: k for k, v in _OID_TO_URL.items()}

    # SNOMED URIs with module/version suffixes
    _SNOMED_PATTERN = re.compile(r"^(http://snomed\.info/sct)(/.*)?$")

    @classmethod
    def normalize(cls, system: Optional[str]) -> Optional[str]:
        """Normalize a code system identifier to its canonical URL.

        Args:
            system: A code system identifier (OID, URL, or None).

        Returns:
            Canonical URL for the system, or the input unchanged if unknown.
        """
        if system is None:
            return None

        # OID → URL
        url = cls._OID_TO_URL.get(system)
        if url is not None:
            return url

        # SNOMED module-specific URL → base URL
        m = cls._SNOMED_PATTERN.match(system)
        if m and m.group(2):
            return m.group(1)

        return system

    @classmethod
    def to_oid(cls, system: Optional[str]) -> Optional[str]:
        """Convert a canonical URL back to an OID if known.

        Args:
            system: A canonical URL or OID.

        Returns:
            OID string if a mapping exists, otherwise the input unchanged.
        """
        if system is None:
            return None
        normalized = cls.normalize(system)
        return cls._URL_TO_OID.get(normalized, system)
