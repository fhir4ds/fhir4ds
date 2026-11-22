"""fhir4ds.patient-matching — deterministic patient matching (AMUX-134).

Slice 1: CMS A-D normalizers (pure Python), field_values DuckDB index,
Category-1 rule table, exact-rule engine.
Slice 2: upstream P-value pinning (Table-3 u-probability products),
Damerau-Levenshtein <=1 / nickname fuzzy names, DOB +/-1 day, fuzzy rule
evaluation in the engine.
Slice 3: FHIR R4 Linkage writer (canonical pair keys, deterministic — no
timestamps), match-decision audit table (caller-supplied run_id), and the
flag-gated ingest hook. See
fhir4ds-private/docs/architecture/plans/FEATURE_PATIENT_MATCHING.md.
Slice 4: corpus pass (every indexed patient vs the full corpus), connected
components -> patient_membership / individual-context views, and
hard-contradiction surfacing (v1: never auto-splits).
"""

from __future__ import annotations

import duckdb

from .audit import create_audit_tables, record_match_audit
from .corpus import (
    CorpusReport,
    build_membership,
    find_contradictions,
    individual_context_patients,
    individual_patients_view,
    match_corpus,
)
from .engine import MatchResult, match_patient
from .entity_extractors import (
    extract_location_fields,
    extract_organization_fields,
    extract_practitioner_fields,
)
from .entity_rules import (
    LOCATION_APPROVAL_THRESHOLD,
    LOCATION_RULES,
    ORGANIZATION_APPROVAL_THRESHOLD,
    ORGANIZATION_RULES,
    PRACTITIONER_APPROVAL_THRESHOLD,
    PRACTITIONER_RULES,
)
from .ingest import IngestReport, maybe_match_on_ingest, match_on_ingest
from .linkage import (
    MATCHING_EXTENSION_URL,
    build_linkage_resource,
    canonical_pair_key,
    create_linkage_tables,
    load_linkage_resources,
    upsert_linkage,
)
from .fuzzy import (
    FUZZY_NAME_MIN_LEN,
    damerau_le1,
    dob_fuzzy_matches,
    name_fuzzy_match,
)
from .normalizers import (
    extract_patient_fields,
    nickname_set,
    norm_date,
    norm_name_parts,
    norm_phone,
    norm_text,
    parse_suffix,
    suffix_conflict,
)
from .rules import (
    APPROVAL_THRESHOLD,
    BAND_EDGES,
    BAND_U_VALUES,
    CATEGORY1_RULES,
    EMBED,
    FIELD_U_PROBS,
    MatchRule,
    embedding_rules,
    p_collision,
    patient_rules_with_embedding,
)
from . import name_embedding
from .name_embedding import name_distance_band  # noqa: F401 (re-export)
from .related_person import RelatedPersonReport, match_related_persons
from .store import (
    create_matching_tables,
    exact_candidates,
    index_entity,
    index_patient,
)

__version__ = "0.0.26"

__all__ = [
    "register_matching_macros",
    "normalize_patient_fields",
    "MatchResult",
    "match_patient",
    "MatchRule",
    "CATEGORY1_RULES",
    "FIELD_U_PROBS",
    "APPROVAL_THRESHOLD",
    "p_collision",
    # FHIR4-20: embedding match rules
    "EMBED",
    "BAND_U_VALUES",
    "BAND_EDGES",
    "embedding_rules",
    "patient_rules_with_embedding",
    "name_embedding",
    "name_distance_band",
    "damerau_le1",
    "name_fuzzy_match",
    "dob_fuzzy_matches",
    "FUZZY_NAME_MIN_LEN",
    "create_matching_tables",
    "index_patient",
    "index_entity",
    "exact_candidates",
    "extract_patient_fields",
    "nickname_set",
    "norm_date",
    "norm_name_parts",
    "norm_phone",
    "norm_text",
    "parse_suffix",
    "suffix_conflict",
    "MATCHING_EXTENSION_URL",
    "canonical_pair_key",
    "build_linkage_resource",
    "create_linkage_tables",
    "upsert_linkage",
    "load_linkage_resources",
    "create_audit_tables",
    "record_match_audit",
    "IngestReport",
    "match_on_ingest",
    "maybe_match_on_ingest",
    "CorpusReport",
    "match_corpus",
    "build_membership",
    "individual_context_patients",
    "find_contradictions",
    "individual_patients_view",
    # AMUX-150 chunk B: identity strategies
    "extract_practitioner_fields",
    "extract_organization_fields",
    "extract_location_fields",
    "PRACTITIONER_RULES",
    "ORGANIZATION_RULES",
    "LOCATION_RULES",
    "PRACTITIONER_APPROVAL_THRESHOLD",
    "ORGANIZATION_APPROVAL_THRESHOLD",
    "LOCATION_APPROVAL_THRESHOLD",
    "RelatedPersonReport",
    "match_related_persons",
    "__version__",
]

# Basic text-normalization macro for ad-hoc SQL exploration. The full CMS
# normalizer pack (diacritic fold, phone/date/name rules) is Python-side;
# fuzzy comparators are Python-only by design (slice 2).
_NORM_TEXT_MACRO = """
CREATE OR REPLACE MACRO matching_norm_text(x) AS
    trim(lower(regexp_replace(regexp_replace(x, '[^a-zA-Z0-9 ]', '', 'g'), '\\s+', ' ', 'g')))
"""


def register_matching_macros(conn: duckdb.DuckDBPyConnection) -> None:
    """Register the matching helper SQL macros on a DuckDB connection."""
    from ._conn import require_open_connection

    require_open_connection(conn, "register matching macros")
    conn.execute(_NORM_TEXT_MACRO)


def normalize_patient_fields(resource: dict) -> dict[str, list[str]]:
    """Normalize a Patient resource into the CMS field vocabulary."""
    return extract_patient_fields(resource)
