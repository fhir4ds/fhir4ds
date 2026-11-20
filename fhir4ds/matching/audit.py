"""Match-decision audit trail (AMUX-134 slice 3).

Every ``match_patient`` decision writes exactly one row set:

- ``match`` — one row per matched pair (``candidate_id`` = the matched id,
  carrying the firing rule, confidence, and per-field evidence);
- ``ambiguous`` — one row with the candidate list in the evidence JSON;
- ``no_match`` — one row with the evaluated-rule list in the evidence JSON.

Determinism doctrine: NO wall-clock timestamps anywhere. Ordering comes
from the caller-supplied ``run_id`` plus the implicit sequence id.
"""

from __future__ import annotations

import json

import duckdb

from .engine import MatchResult

__all__ = [
    "MATCH_AUDIT_DDL",
    "MATCH_AUDIT_SEQUENCE_DDL",
    "create_audit_tables",
    "record_match_audit",
]

MATCH_AUDIT_SEQUENCE_DDL = "CREATE SEQUENCE IF NOT EXISTS match_audit_id_seq START 1"

MATCH_AUDIT_DDL = """
CREATE TABLE IF NOT EXISTS match_audit (
    id BIGINT DEFAULT nextval('match_audit_id_seq'),
    run_id VARCHAR NOT NULL,
    patient_id VARCHAR NOT NULL,
    candidate_id VARCHAR,
    outcome VARCHAR NOT NULL,
    rule_id VARCHAR,
    confidence DOUBLE,
    evidence JSON
)
"""


def create_audit_tables(conn: duckdb.DuckDBPyConnection) -> None:
    conn.execute(MATCH_AUDIT_SEQUENCE_DDL)
    conn.execute(MATCH_AUDIT_DDL)


def _evidence_payload(match_result: MatchResult) -> dict:
    if match_result.outcome == "ambiguous":
        return {"candidates": sorted(match_result.matched_ids)}
    payload = (
        {"evaluatedRules": list(match_result.evaluated_rules)}
        if match_result.outcome == "no_match"
        else dict(match_result.evidence)
    )
    # CR-002: the approval-threshold enforcement decision (rule, Ps,
    # threshold, corroboration required/satisfied) rides the audit
    # evidence. Patient results never carry it.
    if match_result.threshold_enforcement is not None:
        payload["thresholdEnforcement"] = match_result.threshold_enforcement
    return payload


def record_match_audit(
    conn: duckdb.DuckDBPyConnection,
    run_id: str,
    patient_id: str,
    match_result: MatchResult,
) -> int:
    """Write the audit row(s) for one decision; returns rows written."""
    if not isinstance(run_id, str) or not run_id:
        raise ValueError("run_id must be a non-empty string")
    create_audit_tables(conn)
    evidence_json = json.dumps(_evidence_payload(match_result), sort_keys=True)
    rows = []
    if match_result.outcome == "match":
        for candidate_id in match_result.matched_ids:
            rows.append(
                (
                    run_id,
                    patient_id,
                    candidate_id,
                    match_result.outcome,
                    match_result.rule_id,
                    match_result.confidence,
                    evidence_json,
                )
            )
    else:
        rows.append(
            (
                run_id,
                patient_id,
                None,
                match_result.outcome,
                match_result.rule_id,
                match_result.confidence,
                evidence_json,
            )
        )
    conn.executemany(
        "INSERT INTO match_audit (run_id, patient_id, candidate_id, outcome, "
        "rule_id, confidence, evidence) VALUES (?, ?, ?, ?, ?, ?, ?)",
        rows,
    )
    return len(rows)
