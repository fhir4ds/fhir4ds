"""fhir4ds.dedup — temporal resource deduplication (AMUX-142).

Slice 1: normalization core. Pure, deterministic per-resource normalizers:

- temporal signature extraction (``NormalizedDate``, 6 authored-precision
  signatures, authored-local partition dates, UTC instants where the
  authored value determines them);
- code system canonicalization (SystemResolver + UMLS mnemonics);
- value partition keys with UCUM cross-unit canonicalization via the
  engine's quantity conversion surface;
- VITAL/LAB/OTHER category rules with a vendored US Core vitals LOINC list.

See fhir4ds-private/docs/architecture/plans/FEATURE_TEMPORAL_DEDUP.md.
"""

from __future__ import annotations

from .category import Category, US_CORE_VITAL_LOINC, categorize
from .codes import normalize_code, normalize_codes
from .pipeline import (
    POC_TROPONIN,
    VITAL_EXTENDED_WINDOW_LOINC,
    DedupRecord,
    DedupResult,
    dedup_pass,
    escalate,
    partition,
)
from .temporal import (
    DEFAULT_TZ,
    NormalizedDate,
    Signature,
    normalize_temporal,
    secondary_timestamp,
)
from .values import normalize_value

__version__ = "0.0.1"

__all__ = [
    "Category",
    "US_CORE_VITAL_LOINC",
    "POC_TROPONIN",
    "VITAL_EXTENDED_WINDOW_LOINC",
    "DedupRecord",
    "DedupResult",
    "categorize",
    "normalize_code",
    "normalize_codes",
    "normalize_value",
    "normalize_temporal",
    "secondary_timestamp",
    "dedup_pass",
    "escalate",
    "partition",
    "NormalizedDate",
    "Signature",
    "DEFAULT_TZ",
    "__version__",
]
