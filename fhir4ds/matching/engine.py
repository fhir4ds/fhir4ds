"""Deterministic matching engine (slices 1-2; AMUX-150 generalized).

Rules are evaluated in table order (P(collision) ascending, ties by rule
id); first firing rule wins; candidate ids sorted; confidence is the
lookup 1 - P(collision) (the fuzzy P when any fuzzy field matched
fuzzily), never a computed posterior.

Blocking stays exact-index-first: for a rule with exact fields, candidates
come from the exact (field, value) index intersection; for an all-fuzzy
rule (rule 01), the candidate pool is entities holding at least one value
for every rule field. Fuzzy fields are then verified pairwise against each
candidate's indexed values — a field matches when ANY of the query
entity's values matches ANY of the candidate's values, exact first, then
fuzzy (person names: nickname equivalence or Damerau-Levenshtein <= 1 at
>= 5 chars; DOB: +/- 1 day; org/location names: DL <= 1 at >= 5 chars).
Suffix-conflict negation is unchanged.

fhir4ds deviation (Joel-approved 2026-11-17): rules may carry post-
verification ``guards`` (rule 30: ssn4/first-name agreement) - after
field verification passes, a candidate whose guarded field values
exist and disagree on both sides is dropped from that rule; another
rule may still fire (see rules.py).

AMUX-150 chunk B generalization: ``match_fields`` takes the rule set and
``entity_type`` as parameters (default: the Patient Category-1 table and
``'Patient'``) and every index query is entity-scoped. Patient behavior
is byte-for-byte unchanged — the existing patient matching suite is the
regression gate.
"""

from __future__ import annotations

from dataclasses import dataclass, field as dc_field
from typing import Optional

import duckdb

from .fuzzy import dob_fuzzy_matches, name_fuzzy_match, text_fuzzy_match
from .normalizers import extract_patient_fields, suffix_conflict
from .rules import (
    CATEGORY1_RULES,
    EXACT,
    GUARD_FIELD_BY_NAME,
    MatchRule,
)
from .store import create_matching_tables, exact_candidates, index_patient  # noqa: F401

__all__ = ["MatchResult", "match_patient", "match_fields", "evaluate_rule"]

_NAME_FIELDS = frozenset({"first", "last"})
_TEXT_NAME_FIELDS = frozenset({"org_name", "loc_name"})


@dataclass(frozen=True)
class MatchResult:
    outcome: str  # 'match' | 'no_match' | 'ambiguous'
    rule_id: Optional[str] = None
    confidence: Optional[float] = None
    matched_ids: tuple[str, ...] = ()
    evidence: dict[str, str] = dc_field(default_factory=dict)
    skipped_rules: tuple[str, ...] = ()  # empty since slice 2 (fuzzy implemented)
    evaluated_rules: tuple[str, ...] = ()
    match_type: str = "exact"  # 'exact' | 'fuzzy' — per the FIRING rule's evaluation


def _candidate_suffixes(
    conn: duckdb.DuckDBPyConnection, entity_type: str, entity_id: str
) -> list[str]:
    rows = conn.execute(
        "SELECT value FROM field_values WHERE entity_type = ? "
        "AND field_name = 'suffix' AND patient_id = ?",
        [entity_type, entity_id],
    ).fetchall()
    return [r[0] for r in rows]


def _indexed_values(
    conn: duckdb.DuckDBPyConnection, entity_type: str, field_name: str,
    entity_id: str,
) -> list[str]:
    rows = conn.execute(
        "SELECT value FROM field_values WHERE entity_type = ? "
        "AND field_name = ? AND patient_id = ?",
        [entity_type, field_name, entity_id],
    ).fetchall()
    return [r[0] for r in rows]


def _rule_candidate_ids(
    conn: duckdb.DuckDBPyConnection, rule: MatchRule,
    fields: dict[str, list[str]], entity_type: str,
) -> set[str]:
    """Candidate ids matching ALL exact fields (exists-per-field semantics)."""
    candidates: Optional[set[str]] = None
    for field_name in rule.exact_fields():
        values = fields.get(field_name, [])
        if not values:
            return set()  # rule cannot fire: entity lacks this field
        field_ids: set[str] = set()
        for value in values:
            field_ids.update(
                exact_candidates(conn, field_name, value, entity_type))
        candidates = field_ids if candidates is None else (candidates & field_ids)
        if not candidates:
            return set()
    return candidates or set()


def _fuzzy_rule_pool(
    conn: duckdb.DuckDBPyConnection, rule: MatchRule,
    fields: dict[str, list[str]], entity_type: str,
) -> set[str]:
    """Candidate pool for an all-fuzzy rule: entities holding at least one
    indexed value for EVERY rule field (a fuzzy match needs a value on both
    sides; the exact index cannot prune typo'd values away)."""
    ids: Optional[set[str]] = None
    for field_name, _mode in rule.fields:
        if not fields.get(field_name):
            return set()
        field_ids = {
            r[0]
            for r in conn.execute(
                "SELECT DISTINCT patient_id FROM field_values "
                "WHERE entity_type = ? AND field_name = ?",
                [entity_type, field_name],
            ).fetchall()
        }
        ids = field_ids if ids is None else (ids & field_ids)
        if not ids:
            return set()
    return ids or set()


def _field_match(
    field_name: str,
    patient_values: list[str],
    candidate_values: list[str],
    allow_fuzzy: bool,
) -> tuple[bool, bool, str]:
    """Match one rule field: (matched, was_fuzzy, evidence).

    Exact-any first (patient value present among the candidate's indexed
    values); then, when the field is fuzzy-marked, pairwise fuzzy
    verification (person names / org-location names / dob comparators).
    """
    cand_set = set(candidate_values)
    for pv in patient_values:
        if pv in cand_set:
            return True, False, pv
    if allow_fuzzy:
        if field_name in _NAME_FIELDS:
            for pv in patient_values:
                for cv in candidate_values:
                    if name_fuzzy_match(pv, cv):
                        return True, True, f"{pv}~{cv}"
        elif field_name in _TEXT_NAME_FIELDS:
            for pv in patient_values:
                for cv in candidate_values:
                    if text_fuzzy_match(pv, cv):
                        return True, True, f"{pv}~{cv}"
        elif field_name == "dob":
            for pv in patient_values:
                for cv in candidate_values:
                    if dob_fuzzy_matches(pv, cv):
                        return True, True, f"{pv}~{cv}"
    return False, False, ""


def _guard_passes(
    field_name: str,
    patient_values: list[str],
    candidate_values: list[str],
) -> bool:
    """One post-verification disagreement guard (fhir4ds rule-30 deviation).

    A guard only fails when BOTH sides carry non-empty value sets for
    the guarded field AND every cross-pair disagrees: ssn4/phone sets are
    disjoint, or no first-name pair matches exactly / by nickname set /
    fuzzily (``name_fuzzy_match``). Missing values on either side never
    fail a guard. A guard failure drops the candidate from THIS rule
    only — it is not a hard negation of the pair.
    """
    if not patient_values or not candidate_values:
        return True
    if field_name in ("ssn4", "phone"):
        return bool(set(patient_values) & set(candidate_values))
    if field_name == "first":
        return any(
            name_fuzzy_match(pv, cv) for pv in patient_values for cv in candidate_values
        )
    raise ValueError(f"unknown guard field: {field_name!r}")


def _guards_pass(
    rule: MatchRule,
    fields: dict[str, list[str]],
    candidate_values_by_field: dict[str, list[str]],
) -> bool:
    """All of ``rule.guards`` pass for one candidate (no guards -> True)."""
    for guard in rule.guards:
        try:
            key = GUARD_FIELD_BY_NAME[guard]
        except KeyError:
            raise ValueError(f"unknown guard: {guard!r}") from None
        if not _guard_passes(
            key, fields.get(key, []), candidate_values_by_field.get(key, [])
        ):
            return False
    return True


def _verify_candidate(
    conn: duckdb.DuckDBPyConnection,
    rule: MatchRule,
    fields: dict[str, list[str]],
    candidate_id: str,
    entity_type: str,
) -> tuple[bool, bool, dict[str, str]]:
    """Verify every rule field against one candidate.

    Returns (matched, any_field_fuzzy, evidence). Exact-mode fields never
    fuzzy-match; fuzzy-mode fields try exact first (so unchanged values do
    not taint match_type).
    """
    evidence: dict[str, str] = {}
    any_fuzzy = False
    for field_name, mode in rule.fields:
        matched, was_fuzzy, ev = _field_match(
            field_name,
            fields.get(field_name, []),
            _indexed_values(conn, entity_type, field_name, candidate_id),
            allow_fuzzy=(mode != EXACT),
        )
        if not matched:
            return False, False, {}
        any_fuzzy = any_fuzzy or was_fuzzy
        evidence[field_name] = ev
    return True, any_fuzzy, evidence


def match_patient(
    conn: duckdb.DuckDBPyConnection,
    patient_resource: dict,
    exclude: frozenset[str] = frozenset(),
) -> MatchResult:
    """Match one Patient resource against the indexed corpus.

    ``exclude`` (slice 3) drops patient ids from every rule's candidate
    pool before verification — used by the ingest hook so an
    already-indexed patient never matches itself, and by corpus-mode
    matching so decisions depend only on the patient SET (determinism
    doctrine, design doc §4).
    """
    create_matching_tables(conn)
    return match_fields(
        conn, extract_patient_fields(patient_resource), exclude=exclude
    )


def match_fields(
    conn: duckdb.DuckDBPyConnection,
    fields: dict[str, list[str]],
    exclude: frozenset[str] = frozenset(),
    *,
    rules: list[MatchRule] = CATEGORY1_RULES,
    entity_type: str = "Patient",
) -> MatchResult:
    """Match a normalized field map against the indexed corpus (slice 4).

    Same semantics as :func:`match_patient` but takes the normalized
    ``field_name -> values`` map directly, so corpus-mode matching can
    evaluate an entity whose fields are read back from the ``field_values``
    index (decisions then depend only on indexed state, not on holding the
    original resource).

    AMUX-150: ``rules`` + ``entity_type`` parameterize the rule table and
    the index scope; defaults reproduce the Patient Category-1 behavior
    byte-for-byte. Disabled rules (``enabled=False``) are skipped.
    """
    create_matching_tables(conn)
    candidate_suffixes = fields.get("suffix", [])

    skipped: list[str] = []
    evaluated: list[str] = []
    for rule in rules:
        if not rule.enabled:
            continue
        # Slice 2: fuzzy rules are evaluated (skipped stays empty, kept for
        # API compatibility).
        evaluated.append(rule.rule_id)
        if any(not fields.get(f) for f, _mode in rule.fields):
            continue  # entity lacks a rule field -> rule cannot fire
        if rule.exact_fields():
            candidates = _rule_candidate_ids(conn, rule, fields, entity_type)
        else:
            candidates = _fuzzy_rule_pool(conn, rule, fields, entity_type)
        candidates = candidates - exclude
        if not candidates:
            continue
        # Pairwise verification (exact fields are guaranteed by blocking;
        # fuzzy fields verified exact-first then fuzzy per candidate).
        verified: dict[str, tuple[bool, dict[str, str]]] = {}
        for pid in sorted(candidates):
            matched, any_fuzzy, evidence = _verify_candidate(
                conn, rule, fields, pid, entity_type)
            if not matched:
                continue
            if rule.guards:
                # fhir4ds rule-30 deviation: post-verification disagreement
                # guards over fields NOT in the rule. A failed guard drops
                # the candidate from THIS rule only.
                guard_values = {
                    GUARD_FIELD_BY_NAME[guard]: _indexed_values(
                        conn, entity_type, GUARD_FIELD_BY_NAME[guard], pid)
                    for guard in rule.guards
                }
                if not _guards_pass(rule, fields, guard_values):
                    continue
            verified[pid] = (any_fuzzy, evidence)
        if not verified:
            continue
        # Suffix-conflict negation: a candidate whose suffix set is non-empty
        # and disjoint from the candidate entity's cannot be this person.
        surviving = [
            pid
            for pid in verified
            if not suffix_conflict(
                candidate_suffixes,
                _candidate_suffixes(conn, entity_type, pid))
        ]
        if not surviving:
            continue
        any_fuzzy = any(verified[pid][0] for pid in surviving)
        p = rule.p_collision_fuzzy if any_fuzzy else rule.p_collision
        match_type = "fuzzy" if any_fuzzy else "exact"
        if len(surviving) == 1:
            matched_id = surviving[0]
            return MatchResult(
                outcome="match",
                rule_id=rule.rule_id,
                confidence=1.0 - p,
                matched_ids=(matched_id,),
                evidence=verified[matched_id][1],
                skipped_rules=tuple(skipped),
                evaluated_rules=tuple(evaluated),
                match_type=match_type,
            )
        return MatchResult(
            outcome="ambiguous",
            rule_id=rule.rule_id,
            confidence=1.0 - p,
            matched_ids=tuple(sorted(surviving)),
            evidence={},
            skipped_rules=tuple(skipped),
            evaluated_rules=tuple(evaluated),
            match_type=match_type,
        )
    return MatchResult(
        outcome="no_match",
        skipped_rules=tuple(skipped),
        evaluated_rules=tuple(evaluated),
    )


def evaluate_rule(
    conn: duckdb.DuckDBPyConnection,
    rule: MatchRule,
    patient_resource: dict,
    *,
    entity_type: str = "Patient",
) -> MatchResult:
    """Evaluate a single rule in isolation (diagnostics; same semantics)."""
    create_matching_tables(conn)
    extractor = extract_patient_fields if entity_type == "Patient" else None
    if extractor is None:
        raise ValueError(
            "evaluate_rule over non-Patient entities requires pre-extracted "
            "fields; use match_fields(rules=[rule], entity_type=...) instead")
    fields = extractor(patient_resource)
    if any(not fields.get(f) for f, _mode in rule.fields):
        return MatchResult(outcome="no_match", evaluated_rules=(rule.rule_id,))
    candidates = (
        _rule_candidate_ids(conn, rule, fields, entity_type)
        if rule.exact_fields()
        else _fuzzy_rule_pool(conn, rule, fields, entity_type)
    )
    surviving: list[str] = []
    any_fuzzy = False
    for pid in sorted(candidates):
        matched, fuzzy, _ev = _verify_candidate(
            conn, rule, fields, pid, entity_type)
        if not matched:
            continue
        if rule.guards and not _guards_pass(
            rule,
            fields,
            {GUARD_FIELD_BY_NAME[guard]: _indexed_values(
                conn, entity_type, GUARD_FIELD_BY_NAME[guard], pid)
             for guard in rule.guards},
        ):
            continue
        if not suffix_conflict(
            fields.get("suffix", []),
            _candidate_suffixes(conn, entity_type, pid),
        ):
            surviving.append(pid)
            any_fuzzy = any_fuzzy or fuzzy
    if len(surviving) == 1:
        return MatchResult(
            outcome="match",
            rule_id=rule.rule_id,
            confidence=1.0 - (rule.p_collision_fuzzy if any_fuzzy else rule.p_collision),
            matched_ids=(surviving[0],),
            match_type="fuzzy" if any_fuzzy else "exact",
            evaluated_rules=(rule.rule_id,),
        )
    if surviving:
        return MatchResult(
            outcome="ambiguous",
            rule_id=rule.rule_id,
            confidence=1.0 - (rule.p_collision_fuzzy if any_fuzzy else rule.p_collision),
            matched_ids=tuple(surviving),
            match_type="fuzzy" if any_fuzzy else "exact",
            evaluated_rules=(rule.rule_id,),
        )
    return MatchResult(outcome="no_match", evaluated_rules=(rule.rule_id,))
