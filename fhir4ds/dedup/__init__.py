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
from .concept_index import (
    ConceptIndex,
    Resolution,
    default_concept_index,
)
from .curation import (
    CURATION_QUEUE_FILENAME,
    DedupCodeProposer,
    PROPOSER_INTERFACE_VERSION,
    write_curation_queue,
)
from .lexical import (
    normalize_lexical_text,
    tier2_text_set,
)
from .audit import (
    DEDUP_AUDIT_DDL,
    create_dedup_audit_table,
    load_dedup_audit,
    record_dedup_audit,
)
from .linkage import (
    DEDUP_LINKAGE_DDL,
    TEMPORAL_DEDUP_EXTENSION_URL,
    build_linkage_resource,
    create_dedup_linkage_table,
    delete_linkage,
    infer_window_rule,
    load_dedup_linkage_resources,
    upsert_dedup_linkage,
)
from .medication import (
    LazyMedicationIndex,
    MedicationIndex,
    resolve_medication_reference,
)
from .pipeline import (
    POC_TROPONIN,
    VITAL_EXTENDED_WINDOW_LOINC,
    DedupRecord,
    DedupResult,
    dedup_pass,
    escalate,
    partition,
)
from .runner import DedupRunResult, run_dedup
from .encounter import (
    ENCOUNTER_MERGE_THRESHOLD,
    EncounterFeatures,
    EncounterRunResult,
    encounter_pass,
    run_encounter_dedup,
)
from .survivorship import (
    DEDUP_EXTENSION_URL,
    RICHNESS_KEYS,
    SURVIVOR_SIGNATURE_RANK,
    merge_resources,
    select_survivor,
    survivor_dedup_id,
    survivor_ranking_key,
    survivor_rule_tuple,
)
from .temporal import (
    DEFAULT_TZ,
    MIN_INSTANT,
    MAX_INSTANT,
    NormalizedDate,
    Signature,
    normalize_temporal,
    overlap_fraction,
    period_overlap,
    secondary_timestamp,
)
from .values import normalize_value

__version__ = "0.0.26"

__all__ = [
    "Category",
    "US_CORE_VITAL_LOINC",
    "POC_TROPONIN",
    "VITAL_EXTENDED_WINDOW_LOINC",
    "ConceptIndex",
    "Resolution",
    "default_concept_index",
    "CURATION_QUEUE_FILENAME",
    "DedupCodeProposer",
    "PROPOSER_INTERFACE_VERSION",
    "write_curation_queue",
    "normalize_lexical_text",
    "tier2_text_set",
    "LazyMedicationIndex",
    "MedicationIndex",
    "resolve_medication_reference",
    "DedupRecord",
    "DedupResult",
    "DedupRunResult",
    "categorize",
    "normalize_code",
    "normalize_codes",
    "normalize_value",
    "normalize_temporal",
    "secondary_timestamp",
    "dedup_pass",
    "escalate",
    "partition",
    "run_dedup",
    # encounter strategy (AMUX-150 chunk C)
    "ENCOUNTER_MERGE_THRESHOLD",
    "EncounterFeatures",
    "EncounterRunResult",
    "encounter_pass",
    "run_encounter_dedup",
    # survivorship (slice 3)
    "DEDUP_EXTENSION_URL",
    "RICHNESS_KEYS",
    "SURVIVOR_SIGNATURE_RANK",
    "merge_resources",
    "select_survivor",
    "survivor_dedup_id",
    "survivor_ranking_key",
    "survivor_rule_tuple",
    # linkage (slice 3)
    "DEDUP_LINKAGE_DDL",
    "TEMPORAL_DEDUP_EXTENSION_URL",
    "build_linkage_resource",
    "create_dedup_linkage_table",
    "delete_linkage",
    "infer_window_rule",
    "load_dedup_linkage_resources",
    "upsert_dedup_linkage",
    # audit (slice 3)
    "DEDUP_AUDIT_DDL",
    "create_dedup_audit_table",
    "load_dedup_audit",
    "record_dedup_audit",
    "NormalizedDate",
    "Signature",
    "DEFAULT_TZ",
    "MIN_INSTANT",
    "MAX_INSTANT",
    "period_overlap",
    "overlap_fraction",
    "__version__",
]
