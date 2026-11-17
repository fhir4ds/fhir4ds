"""fhir4ds.patient-matching — deterministic patient matching (AMUX-134).

Slice 1: CMS A-D normalizers (pure Python), field_values DuckDB index,
Category-1 exact rule table, exact-rule engine. See
fhir4ds-private/docs/architecture/plans/FEATURE_PATIENT_MATCHING.md.
"""

from __future__ import annotations

import duckdb

from .engine import MatchResult, match_patient
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
from .rules import CATEGORY1_RULES, MatchRule
from .store import create_matching_tables, exact_candidates, index_patient

__version__ = "0.0.1"

__all__ = [
    "register_matching_macros",
    "normalize_patient_fields",
    "MatchResult",
    "match_patient",
    "MatchRule",
    "CATEGORY1_RULES",
    "create_matching_tables",
    "index_patient",
    "exact_candidates",
    "extract_patient_fields",
    "nickname_set",
    "norm_date",
    "norm_name_parts",
    "norm_phone",
    "norm_text",
    "parse_suffix",
    "suffix_conflict",
    "__version__",
]

# Basic text-normalization macro for ad-hoc SQL exploration. The full CMS
# normalizer pack (diacritic fold, phone/date/name rules) is Python-side in
# slice 1; SQL macro equivalents land with the fuzzy slice.
_NORM_TEXT_MACRO = """
CREATE OR REPLACE MACRO matching_norm_text(x) AS
    trim(lower(regexp_replace(regexp_replace(x, '[^a-zA-Z0-9 ]', '', 'g'), '\\s+', ' ', 'g')))
"""


def register_matching_macros(conn: duckdb.DuckDBPyConnection) -> None:
    """Register the matching helper SQL macros on a DuckDB connection."""
    conn.execute(_NORM_TEXT_MACRO)


def normalize_patient_fields(resource: dict) -> dict[str, list[str]]:
    """Normalize a Patient resource into the CMS field vocabulary."""
    return extract_patient_fields(resource)
