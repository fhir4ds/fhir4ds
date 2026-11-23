"""fhir4ds.realism — realism validation harness for patient matching +
resource dedup (AMUX-150 follow-on, Joel 2026-11-20).

Corpus-agnostic, deterministic duplicate-injection benchmark designed
around the MIMIC-IV-FHIR demo corpus:

- :mod:`fhir4ds.realism.corpus` — FHIR corpus loader (MIMIC NDJSON
  layout / Bundle files) + ``fetch_mimic_demo.sh`` data fetch helper.
- :mod:`fhir4ds.realism.corrupt` — seeded corruption profiles producing
  gold-labeled duplicate pairs (clean copies through name typos,
  nicknames, transliteration variants, DOB shifts, address moves, phone
  flips, MRN formatting variants, and stacks of the above).
- :mod:`fhir4ds.realism.benchmark` — matching P/R + per-profile recall,
  dedup cluster/curation-queue report, optional PIQI rubric scorecard;
  byte-identical JSON reports for identical inputs.

CLI::

    python3 -m fhir4ds.realism.benchmark --corpus <dir> --output-dir <dir>
"""

from __future__ import annotations

from .corpus import (
    bundle_entries,
    is_fhir_resource,
    iter_ndjson_resources,
    load_bundle_file,
    load_corpus,
    load_ndjson_dir,
)
from .corrupt import (
    DEFAULT_PROFILE_WEIGHTS,
    PROFILES,
    TRANSLITERATION_GROUPS,
    CorruptionConfig,
    GoldPair,
    InjectionResult,
    apply_profile,
    damerau_le1_typo,
    inject_duplicates,
)

__version__ = "0.0.26"

__all__ = [
    "__version__",
    # corpus
    "bundle_entries",
    "is_fhir_resource",
    "iter_ndjson_resources",
    "load_bundle_file",
    "load_corpus",
    "load_ndjson_dir",
    # corrupt
    "DEFAULT_PROFILE_WEIGHTS",
    "PROFILES",
    "TRANSLITERATION_GROUPS",
    "CorruptionConfig",
    "GoldPair",
    "InjectionResult",
    "apply_profile",
    "damerau_le1_typo",
    "inject_duplicates",
]
