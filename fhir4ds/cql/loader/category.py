"""Resource-type → medterm4ds category mapping and text normalization.

Used by :class:`fhir4ds.cql.loader.auto_coder.AutoCoder` to translate a
FHIR resource type into one of the coarse discovery categories understood
by :meth:`TerminologyEndpoint.search_text` / ``search_batch`` (the
``category`` parameter of ``$search``).

References:
    * FDD: ``docs/architecture/plans/FEATURE_MEDTERM4DS_PHASE2_AUTOCODING.md``
      §3e (Category Mapping) and §3c step 1 (Text normalization).
    * medterm4ds Phase 1 ``TerminologyEndpoint`` Protocol
      (``fhir4ds/cql/terminology/endpoint.py``).

Zero-dependency guarantee (Phase 1 INV-1, preserved):
    This module imports ONLY stdlib (``unicodedata``, ``re``, ``string``).
    No ``httpx``, no ``medterm4ds``, no FHIRPath runtime.
"""

from __future__ import annotations

import re
import string
import unicodedata
from typing import Optional

# ── resource-type → discovery category map ────────────────────────────
#
# Verified unique-namespace by grep 2026-07-03 — the loader/resolver do
# NOT define a terminology-discovery ``category`` concept elsewhere.
# ``CQLErrorCategory`` in ``cql_server/types.py`` is a different
# namespace (error categorization) and MUST NOT be reused.
#
# v1 limitation: ``Observation.code`` can be lab, vital, or survey —
# the default is ``"lab"``; users override via
# ``AutoCoderConfig.category_overrides={"Observation": "vital"}``.
# Phase 4 NER will introduce per-resource-type LOINC-class detection.

RESOURCE_TYPE_TO_CATEGORY: dict[str, str] = {
    "Condition":           "condition",
    "Observation":         "lab",
    "MedicationRequest":   "medication",
    "MedicationStatement": "medication",
    "Medication":          "medication",
    "Procedure":           "procedure",
    "Immunization":        "vaccine",
    "BodyStructure":       "body_structure",
}


def resolve_category(
    resource_type: str,
    overrides: Optional[dict[str, str]] = None,
) -> Optional[str]:
    """Resolve the medterm4ds discovery category for a resource type.

    Args:
        resource_type: FHIR resource type name (e.g. ``"Condition"``).
        overrides: Optional dict mapping resource-type → category. Takes
            precedence over :data:`RESOURCE_TYPE_TO_CATEGORY`. Useful
            for users who want to remap ``"Observation"`` to
            ``"vital"``.

    Returns:
        The discovery category string (e.g. ``"condition"``) or
        ``None`` if the resource type is unknown. Returning ``None``
        causes :class:`AutoCoder` to skip the resource with a DEBUG
        log — it does NOT raise.
    """
    if overrides and resource_type in overrides:
        return overrides[resource_type]
    return RESOURCE_TYPE_TO_CATEGORY.get(resource_type)


# Punctuation runs → single space. Includes ASCII punctuation plus the
# extra Unicode punctuation categories we want to strip during
# normalization. Compiled once at import.
_PUNCT_OR_SPACE_RE = re.compile(
    f"[{re.escape(string.punctuation)}\\s]+"
)


def normalize_text(text: str) -> str:
    """Normalize free text before hashing / search-batching.

    Pipeline (per FDD §3c step 1):
        1. NFKC Unicode normalization (compatibility decomposition +
           canonical composition — folds fullwidth digits, ligatures,
           superscripts into their canonical forms so visually
           identical strings hash identically).
        2. Lowercase (case-insensitive hash key).
        3. Replace every run of whitespace/punctuation with a single
           space (so ``"T2DM!"`` and ``"t2dm"`` and ``"T2DM, "`` collapse
           to the same key).
        4. Strip leading/trailing whitespace.

    Idempotent: ``normalize_text(normalize_text(x)) == normalize_text(x)``.

    Args:
        text: Raw input text. Must be a string.

    Returns:
        Normalized text. Empty string if input was empty.

    Raises:
        TypeError: If ``text`` is not a string. (AutoCoder catches and
            degrades to WARNING per INV-9.)
    """
    if not isinstance(text, str):
        raise TypeError(
            f"normalize_text expected str, got {type(text).__name__}"
        )
    nfkc = unicodedata.normalize("NFKC", text)
    lowered = nfkc.lower()
    collapsed = _PUNCT_OR_SPACE_RE.sub(" ", lowered)
    return collapsed.strip()
