"""Category classification for the temporal-dedup pipeline (AMUX-142 slice 1).

Static, deterministic rules per design §2e (Q5 approved): a pure function of
the resource JSON plus a vendored US Core vital-signs LOINC list. A
TerminologyEndpoint may later enrich confidence but never changes the
category — one truth.
"""

from __future__ import annotations

__all__ = ["Category", "US_CORE_VITAL_LOINC", "categorize"]


class Category:
    """Dedup category (plain str constants)."""

    VITAL = "VITAL"
    LAB = "LAB"
    OTHER = "OTHER"


#: Vendored US Core vital-signs LOINC codes (static, versioned here — no
#: runtime terminology dependency). The classic vital-signs set plus the
#: generic vital-signs panel and pediatric measurements.
US_CORE_VITAL_LOINC: frozenset[str] = frozenset({
    "85353-1",  # Vital signs, weight, height, head circumference, ...
    "8310-5",   # Body temperature
    "8480-6",   # Systolic blood pressure
    "8462-4",   # Diastolic blood pressure
    "8302-2",   # Body height
    "29463-7",  # Body weight
    "39156-5",  # Body mass index (BMI) [Ratio]
    "8867-4",   # Heart rate
    "9279-1",   # Respiratory rate
    "59408-5",  # Oxygen saturation by pulse oximetry (arterial)
    "2708-6",   # Oxygen saturation in Arterial blood
    "8287-5",   # Head Occipital-frontal circumference
    "9843-4",   # Head Occipital-frontal circumference Percentile
    "59576-9",  # Body mass index (BMI) [Percentile]
    "77606-2",  # Weight-for-length Percentile
})

_OBS_CATEGORY_SYSTEM = "http://terminology.hl7.org/CodeSystem/observation-category"


def _category_codes(resource: dict) -> list[str]:
    categories = resource.get("category")
    if not isinstance(categories, list):
        return []
    codes: list[str] = []
    for category in categories:
        if not isinstance(category, dict):
            continue
        codings = category.get("coding")
        if not isinstance(codings, list):
            continue
        for coding in codings:
            if not isinstance(coding, dict):
                continue
            system = coding.get("system")
            code = coding.get("code")
            if system in (_OBS_CATEGORY_SYSTEM,
                          "urn:oid:2.16.840.1.113883.4.642.1.1125") \
                    and isinstance(code, str):
                codes.append(code)
    return codes


def _loinc_codes(resource: dict) -> list[str]:
    code_field = resource.get("code")
    if not isinstance(code_field, dict):
        return []
    codings = code_field.get("coding")
    if not isinstance(codings, list):
        return []
    codes: list[str] = []
    for coding in codings:
        if isinstance(coding, dict) and coding.get("system") in \
                ("http://loinc.org", "urn:oid:2.16.840.1.113883.6.1") \
                and isinstance(coding.get("code"), str):
            codes.append(coding["code"])
    return codes


def categorize(resource: dict) -> str:
    """Classify a resource as VITAL, LAB, or OTHER (deterministic, static).

    - LAB: Observation with observation-category ``laboratory`` (category is
      the ONLY lab signal in v1; uncategorized Observations are not LAB).
    - VITAL: Observation with observation-category ``vital-signs``, OR an
      Observation whose LOINC code is in the vendored US Core vitals list.
    - OTHER: everything else (including social-history and imaging).
    """
    if not isinstance(resource, dict):
        return Category.OTHER
    if resource.get("resourceType") != "Observation":
        return Category.OTHER
    category_codes = _category_codes(resource)
    if "laboratory" in category_codes:
        return Category.LAB
    if "vital-signs" in category_codes:
        return Category.VITAL
    for loinc in _loinc_codes(resource):
        if loinc in US_CORE_VITAL_LOINC:
            return Category.VITAL
    return Category.OTHER
