"""Exact-rule matching engine (slice 1).

Deterministic: rules evaluated in table order (P(collision) ascending,
ties by rule id); first firing rule wins; candidate ids sorted; confidence
is the lookup 1 - P(collision), never a computed posterior.
"""

from __future__ import annotations

from dataclasses import dataclass, field as dc_field
from typing import Optional

import duckdb

from .normalizers import extract_patient_fields, suffix_conflict
from .rules import CATEGORY1_RULES, MatchRule
from .store import create_matching_tables, exact_candidates, index_patient

__all__ = ["MatchResult", "match_patient", "evaluate_rule"]


@dataclass(frozen=True)
class MatchResult:
    outcome: str  # 'match' | 'no_match' | 'ambiguous'
    rule_id: Optional[str] = None
    confidence: Optional[float] = None
    matched_ids: tuple[str, ...] = ()
    evidence: dict[str, str] = dc_field(default_factory=dict)
    skipped_rules: tuple[str, ...] = ()  # fuzzy rules not implemented in v1
    evaluated_rules: tuple[str, ...] = ()


def _candidate_suffixes(conn: duckdb.DuckDBPyConnection, patient_id: str) -> list[str]:
    rows = conn.execute(
        "SELECT value FROM field_values WHERE field_name = 'suffix' AND patient_id = ?",
        [patient_id],
    ).fetchall()
    return [r[0] for r in rows]


def _rule_candidate_ids(
    conn: duckdb.DuckDBPyConnection, rule: MatchRule, fields: dict[str, list[str]]
) -> set[str]:
    """Candidate ids matching ALL exact fields (exists-per-field semantics)."""
    candidates: Optional[set[str]] = None
    for field_name in rule.exact_fields():
        values = fields.get(field_name, [])
        if not values:
            return set()  # rule cannot fire: candidate lacks this field
        field_ids: set[str] = set()
        for value in values:
            field_ids.update(exact_candidates(conn, field_name, value))
        candidates = field_ids if candidates is None else (candidates & field_ids)
        if not candidates:
            return set()
    return candidates or set()


def _evidence_for(
    conn: duckdb.DuckDBPyConnection,
    rule: MatchRule,
    fields: dict[str, list[str]],
    matched_id: str,
) -> dict[str, str]:
    evidence: dict[str, str] = {}
    for field_name in rule.exact_fields():
        stored = {
            r[0]
            for r in conn.execute(
                "SELECT value FROM field_values WHERE field_name = ? AND patient_id = ?",
                [field_name, matched_id],
            ).fetchall()
        }
        shared = [v for v in fields.get(field_name, []) if v in stored]
        if shared:
            evidence[field_name] = shared[0]
    return evidence


def match_patient(conn: duckdb.DuckDBPyConnection, patient_resource: dict) -> MatchResult:
    """Match one Patient resource against the indexed corpus."""
    create_matching_tables(conn)
    fields = extract_patient_fields(patient_resource)
    candidate_suffixes = fields.get("suffix", [])

    skipped: list[str] = []
    evaluated: list[str] = []
    for rule in CATEGORY1_RULES:
        if rule.fuzzy_fields():
            skipped.append(rule.rule_id)
            continue
        evaluated.append(rule.rule_id)
        candidates = _rule_candidate_ids(conn, rule, fields)
        if not candidates:
            continue
        # Suffix-conflict negation: a candidate whose suffix set is non-empty
        # and disjoint from the candidate patient's cannot be this person.
        surviving = [
            pid
            for pid in candidates
            if not suffix_conflict(candidate_suffixes, _candidate_suffixes(conn, pid))
        ]
        if not surviving:
            continue
        if len(surviving) == 1:
            matched_id = surviving[0]
            return MatchResult(
                outcome="match",
                rule_id=rule.rule_id,
                confidence=1.0 - rule.p_collision,
                matched_ids=(matched_id,),
                evidence=_evidence_for(conn, rule, fields, matched_id),
                skipped_rules=tuple(skipped),
                evaluated_rules=tuple(evaluated),
            )
        return MatchResult(
            outcome="ambiguous",
            rule_id=rule.rule_id,
            confidence=1.0 - rule.p_collision,
            matched_ids=tuple(sorted(surviving)),
            evidence={},
            skipped_rules=tuple(skipped),
            evaluated_rules=tuple(evaluated),
        )
    return MatchResult(
        outcome="no_match",
        skipped_rules=tuple(skipped),
        evaluated_rules=tuple(evaluated),
    )
