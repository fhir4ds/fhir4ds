"""FHIR R4 Linkage writer for match decisions (AMUX-134 slice 3).

Every approved ``match`` decision writes (or updates) a Linkage resource:

- ``active=true``
- ``item[0]`` = the CANONICAL patient (lexicographically smaller id) as
  ``type: source``
- ``item[1]`` = the other patient as ``type: alternate``
- one fhir4ds matching extension carrying ruleId / matchType / confidence /
  evaluatedAt (deliberately value-less: the determinism doctrine forbids
  wall-clock timestamps) / the per-field MatchResult evidence.

The storage key is the canonical pair key ``Patient/<a>|Patient/<b>`` with
``a <= b``, so the same pair always lands on one row regardless of which
side triggered the decision. Upserts are idempotent for the same rule and
overwrite (preserving history in the audit table) when the firing rule
changed because the corpus changed.

Evidence canonicalization: the engine records fuzzy evidence directionally
(``"thompsno~thompson"``). The Linkage resource sorts the two sides of each
``~`` pair so the stored JSON depends only on the patient SET, not on which
patient was evaluated first (determinism doctrine, design doc §4).
"""

from __future__ import annotations

import json
from typing import Any, Optional

import duckdb

from .engine import MatchResult

__all__ = [
    "MATCHING_EXTENSION_URL",
    "LINKAGE_DDL",
    "canonical_pair_key",
    "build_linkage_resource",
    "create_linkage_tables",
    "upsert_linkage",
    "load_linkage_resources",
]

MATCHING_EXTENSION_URL = "http://fhir4ds.com/fhir/StructureDefinition/matching"

LINKAGE_DDL = """
CREATE TABLE IF NOT EXISTS linkage (
    linkage_id VARCHAR PRIMARY KEY,
    resource JSON,
    rule_id VARCHAR,
    match_type VARCHAR,
    confidence DOUBLE
)
"""


def canonical_pair_key(new_patient_id: str, existing_patient_id: str) -> str:
    """``Patient/<a>|Patient/<b>`` with the two references sorted."""
    a, b = sorted((f"Patient/{new_patient_id}", f"Patient/{existing_patient_id}"))
    return f"{a}|{b}"


def _canonical_evidence(evidence: dict[str, str]) -> dict[str, str]:
    """Direction-independent evidence: sort both sides of fuzzy ``x~y`` pairs."""
    canon: dict[str, str] = {}
    for field_name, value in evidence.items():
        if isinstance(value, str) and "~" in value:
            left, right = value.split("~", 1)
            value = "~".join(sorted((left, right)))
        canon[field_name] = value
    return canon


def build_linkage_resource(
    match_result: MatchResult, new_patient_id: str, existing_patient_id: str
) -> dict[str, Any]:
    """Build the deterministic Linkage resource for one matched pair."""
    if not match_result.rule_id:
        raise ValueError("MatchResult must carry a rule_id to build a Linkage")
    refs = sorted((f"Patient/{new_patient_id}", f"Patient/{existing_patient_id}"))
    return {
        "resourceType": "Linkage",
        "active": True,
        "item": [
            {"type": "source", "resource": {"reference": refs[0]}},
            {"type": "alternate", "resource": {"reference": refs[1]}},
        ],
        "extension": [
            {
                "url": MATCHING_EXTENSION_URL,
                "extension": [
                    {"url": "ruleId", "valueString": match_result.rule_id},
                    {"url": "matchType", "valueString": match_result.match_type},
                    {"url": "confidence", "valueDecimal": match_result.confidence},
                    # Deliberately value-less: the determinism doctrine forbids
                    # wall-clock timestamps in match artifacts.
                    {"url": "evaluatedAt"},
                    {
                        "url": "evidence",
                        "extension": [
                            {"url": field_name, "valueString": value}
                            for field_name, value in sorted(
                                _canonical_evidence(match_result.evidence).items()
                            )
                        ],
                    },
                ],
            }
        ],
    }


def create_linkage_tables(conn: duckdb.DuckDBPyConnection) -> None:
    conn.execute(LINKAGE_DDL)


def upsert_linkage(
    conn: duckdb.DuckDBPyConnection,
    match_result: MatchResult,
    new_patient_id: str,
    existing_patient_id: str,
) -> dict[str, Any]:
    """Insert or update the Linkage row for one matched pair.

    Returns ``{"action": "created" | "noop" | "overwritten", "linkage_id":
    ..., "resource": ...}``. Same pair + same rule + identical resource is a
    no-op; same pair with a changed resource (different rule, or the same
    rule firing with new evidence/match_type/confidence after a corpus
    change) overwrites, keeping decision history in the audit table.
    """
    create_linkage_tables(conn)
    linkage_id = canonical_pair_key(new_patient_id, existing_patient_id)
    resource = build_linkage_resource(match_result, new_patient_id, existing_patient_id)
    existing_rule: Optional[str] = None
    row = conn.execute(
        "SELECT rule_id FROM linkage WHERE linkage_id = ?", [linkage_id]
    ).fetchone()
    if row is not None:
        existing_rule = row[0]
    action: str
    if existing_rule == match_result.rule_id:
        stored = conn.execute(
            "SELECT resource FROM linkage WHERE linkage_id = ?", [linkage_id]
        ).fetchone()
        stored_resource = json.loads(stored[0])
        if stored_resource == resource:
            return {
                "action": "noop",
                "linkage_id": linkage_id,
                "resource": stored_resource,
            }
        # Same rule but the resource changed (evidence / match_type /
        # confidence drifted with the corpus) -> refresh the stored row.
        action = "overwritten"
    else:
        action = "overwritten" if existing_rule is not None else "created"
    conn.execute(
        "INSERT OR REPLACE INTO linkage VALUES (?, ?, ?, ?, ?)",
        [
            linkage_id,
            json.dumps(resource, sort_keys=True),
            match_result.rule_id,
            match_result.match_type,
            match_result.confidence,
        ],
    )
    return {"action": action, "linkage_id": linkage_id, "resource": resource}


def load_linkage_resources(conn: duckdb.DuckDBPyConnection) -> list[dict[str, Any]]:
    """All stored Linkage resources, ordered by canonical pair key."""
    rows = conn.execute(
        "SELECT resource FROM linkage ORDER BY linkage_id"
    ).fetchall()
    return [json.loads(r[0]) for r in rows]
