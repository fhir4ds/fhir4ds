"""SQL-on-FHIR artifacts for patient matching (AMUX-134 slice 5).

The matching layer surfaces its two SQL-adjacent steps as standard
sql-on-fhir artifacts while the Python engine stays the decision
authority (see
``fhir4ds-private/docs/architecture/plans/FEATURE_PATIENT_MATCHING.md``,
"DuckDB-native, no new services"):

- ``patient_match_fields.vd.json`` — a SQL-on-FHIR v2 ViewDefinition
  over Patient producing the RAW match fields (unnormalized on purpose;
  normalization lives in :mod:`fhir4ds.matching.normalizers`).
- ``exact_candidates.sqlquery.json`` — a SQLQuery Library resource whose
  DuckDB body returns candidate patient ids sharing at least one exact
  normalized ``(field_name, value)`` row with ``$patient_id`` over the
  ``field_values`` index maintained by :mod:`fhir4ds.matching.store`.
"""

from __future__ import annotations

import json
from pathlib import Path

from ...sqlquery import SQLQuery
from ...sqlquery.parser import parse_library
from ...viewdef import ViewDefinition
from ...viewdef.parser import parse_view_definition

__all__ = [
    "ARTIFACTS_DIR",
    "PATIENT_MATCH_FIELDS_VD_PATH",
    "EXACT_CANDIDATES_SQLQUERY_PATH",
    "load_patient_match_fields_vd",
    "load_exact_candidates_sqlquery",
    "load_patient_match_fields_dict",
    "load_exact_candidates_dict",
]

ARTIFACTS_DIR = Path(__file__).resolve().parent
PATIENT_MATCH_FIELDS_VD_PATH = ARTIFACTS_DIR / "patient_match_fields.vd.json"
EXACT_CANDIDATES_SQLQUERY_PATH = ARTIFACTS_DIR / "exact_candidates.sqlquery.json"


def load_patient_match_fields_dict() -> dict:
    """The raw-fields ViewDefinition as a plain dict (verbatim JSON)."""
    return json.loads(PATIENT_MATCH_FIELDS_VD_PATH.read_text(encoding="utf-8"))


def load_patient_match_fields_vd() -> ViewDefinition:
    """Parse the raw-fields ViewDefinition with the fhir4ds viewdef parser."""
    return parse_view_definition(PATIENT_MATCH_FIELDS_VD_PATH.read_text(encoding="utf-8"))


def load_exact_candidates_dict() -> dict:
    """The exact-candidates SQLQuery Library as a plain dict (verbatim JSON)."""
    return json.loads(EXACT_CANDIDATES_SQLQUERY_PATH.read_text(encoding="utf-8"))


def load_exact_candidates_sqlquery() -> SQLQuery:
    """Parse the exact-candidates Library with the fhir4ds sqlquery parser."""
    return parse_library(load_exact_candidates_dict())  # type: ignore[return-value]
