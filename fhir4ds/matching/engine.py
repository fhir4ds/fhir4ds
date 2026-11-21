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

import math
from dataclasses import dataclass, field as dc_field
from typing import Optional

import duckdb

from .fuzzy import dob_fuzzy_matches, name_fuzzy_match, text_fuzzy_match
from .normalizers import extract_patient_fields, suffix_conflict
from .rules import (
    CATEGORY1_RULES,
    EMBED,
    EXACT,
    FIELD_DEPENDENCY_GROUPS,
    FIELD_U_PROBS,
    GUARD_FIELD_BY_NAME,
    MatchRule,
    patient_rules_with_embedding,
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
    # CR-002: the approval-threshold enforcement decision (non-Patient
    # entities only; None on every Patient result). Shape:
    # {required, satisfied, rule_id, firing_p, combined_p, threshold,
    #  corroborating_fields}. On a `match` it describes the winning
    # candidate; on a `no_match` it describes the LAST rule that fired
    # but was refused for want of corroboration.
    threshold_enforcement: Optional[dict] = None


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
    mode: str,
    embed_bands_allowed: Optional[frozenset[str]] = None,
) -> tuple[bool, bool, str, Optional[str]]:
    """Match one rule field: (matched, was_fuzzy, evidence, embed_band).

    Exact-any first (patient value present among the candidate's indexed
    values); then, when the field is fuzzy-marked, pairwise fuzzy
    verification (person names / org-location names / dob comparators).
    EMBED-mode name fields verify through the pinned name-embedding
    distance bands (FHIR4-20); the matched band is returned so the
    decider can select the band's u-value, and the evidence carries
    ``a~b|band=<band>|model=name-embed-v1@<sha8>``.
    ``embed_bands_allowed`` (FHIR4-20 P4 calibration) gates the band to
    the rule's approvable band list — a pair landing in a band the rule
    does not carry (dropped by the approval budget) does NOT match.
    """
    cand_set = set(candidate_values)
    for pv in patient_values:
        if pv in cand_set:
            return True, False, pv, None
    if mode != EXACT:
        if field_name in _NAME_FIELDS:
            if mode == EMBED:
                from . import name_embedding

                model_id = name_embedding.embedding_model_id() or "unavailable"
                for pv in patient_values:
                    for cv in candidate_values:
                        band = name_embedding.name_distance_band(pv, cv)
                        if band is not None and (
                            embed_bands_allowed is None
                            or band in embed_bands_allowed
                        ):
                            return (
                                True,
                                True,
                                f"{pv}~{cv}|band={band}|model={model_id}",
                                band,
                            )
                return False, False, "", None
            for pv in patient_values:
                for cv in candidate_values:
                    if name_fuzzy_match(pv, cv):
                        return True, True, f"{pv}~{cv}", None
        elif field_name in _TEXT_NAME_FIELDS:
            for pv in patient_values:
                for cv in candidate_values:
                    if text_fuzzy_match(pv, cv):
                        return True, True, f"{pv}~{cv}", None
        elif field_name == "dob":
            for pv in patient_values:
                for cv in candidate_values:
                    if dob_fuzzy_matches(pv, cv):
                        return True, True, f"{pv}~{cv}", None
    return False, False, "", None


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
) -> tuple[bool, bool, dict[str, str], dict[str, str]]:
    """Verify every rule field against one candidate.

    Returns (matched, any_field_fuzzy, evidence, embed_bands). Exact-mode
    fields never fuzzy-match; fuzzy-mode fields try exact first (so
    unchanged values do not taint match_type). EMBED fields resolve to
    their matched band (an exactly-equal pair is the tight band).
    """
    evidence: dict[str, str] = {}
    embed_bands: dict[str, str] = {}
    any_fuzzy = False
    allowed = (
        frozenset(b for b, _u in rule.band_u_values)
        if rule.band_u_values else None
    )
    for field_name, mode in rule.fields:
        matched, was_fuzzy, ev, band = _field_match(
            field_name,
            fields.get(field_name, []),
            _indexed_values(conn, entity_type, field_name, candidate_id),
            mode=mode,
            embed_bands_allowed=allowed,
        )
        if not matched:
            return False, False, {}, {}
        if mode == EMBED:
            embed_bands[field_name] = band or "tight"
        any_fuzzy = any_fuzzy or was_fuzzy
        evidence[field_name] = ev
    return True, any_fuzzy, evidence, embed_bands


def _exceeds_threshold(p: float, threshold: float) -> bool:
    """CR-002 'exceeds' with a relative-epsilon guard: authored rules that
    sit EXACTLY at their budget (location L1/L2, P = 1e-4 x 0.01) must not
    flip to over-budget by float-product noise (1.0000000000000002e-06)."""
    return p > threshold and not math.isclose(p, threshold, rel_tol=1e-12)


def _combined_p_with_corroboration(
    conn: duckdb.DuckDBPyConnection,
    rule: MatchRule,
    fields: dict[str, list[str]],
    candidate_id: str,
    entity_type: str,
    firing_p: float,
) -> tuple[float, list[str]]:
    """CR-002 combined evidence: firing-rule P x the u-probabilities of
    ADDITIONAL exactly-agreeing fields (the engine's existing product
    combination semantics over ``FIELD_U_PROBS``).

    A field corroborates when it is not part of the firing rule, is not
    informationally dependent on any rule field (``FIELD_DEPENDENCY_GROUPS``
    — e.g. ``street_line`` cannot corroborate an ``addr_key`` rule, its
    information is already embedded in the key), has a u-probability
    entry, and the query entity's and the candidate's indexed value sets
    are both non-empty and intersect EXACTLY (fuzzy agreement deliberately
    does not corroborate — conservative direction). ``suffix`` never
    corroborates (it is negation machinery, not evidence).
    """
    rule_field_names = {name for name, _mode in rule.fields}
    independent = {
        name for name in fields
        if not any(group.intersection({name, *rule_field_names})
                   and name in group
                   for group in FIELD_DEPENDENCY_GROUPS)
    }
    combined = firing_p
    corroborating: list[str] = []
    for field_name in sorted(independent - rule_field_names - {"suffix"}):
        if field_name not in FIELD_U_PROBS:
            continue
        query_values = fields.get(field_name) or []
        if not query_values:
            continue
        candidate_values = _indexed_values(
            conn, entity_type, field_name, candidate_id)
        if candidate_values and \
                set(query_values) & set(candidate_values):
            combined *= FIELD_U_PROBS[field_name][0]
            corroborating.append(field_name)
    return combined, corroborating


def match_patient(
    conn: duckdb.DuckDBPyConnection,
    patient_resource: dict,
    exclude: frozenset[str] = frozenset(),
    *,
    use_embedding: bool = True,
) -> MatchResult:
    """Match one Patient resource against the indexed corpus.

    ``exclude`` (slice 3) drops patient ids from every rule's candidate
    pool before verification — used by the ingest hook so an
    already-indexed patient never matches itself, and by corpus-mode
    matching so decisions depend only on the patient SET (determinism
    doctrine, design doc §4).

    ``use_embedding`` (FHIR4-20) evaluates the additive E1-E3 embedding
    rules alongside the Category-1 table; inert when the pinned artifact
    is absent (the combined table then equals CATEGORY1_RULES). Pass
    False to pin exact legacy behavior.
    """
    create_matching_tables(conn)
    return match_fields(
        conn, extract_patient_fields(patient_resource), exclude=exclude,
        rules=patient_rules_with_embedding() if use_embedding else CATEGORY1_RULES,
    )


def match_fields(
    conn: duckdb.DuckDBPyConnection,
    fields: dict[str, list[str]],
    exclude: frozenset[str] = frozenset(),
    *,
    rules: list[MatchRule] = CATEGORY1_RULES,
    entity_type: str = "Patient",
    approval_threshold: Optional[float] = None,
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

    CR-002 (non-Patient entities only): when an approval threshold is in
    effect — an explicit ``approval_threshold`` argument, or the
    ``approval_threshold`` attribute of a :class:`~fhir4ds.matching.
    entity_rules.RuleSet` — a rule whose effective P(collision) EXCEEDS
    the threshold does not link a candidate alone: the candidate survives
    only when additional exactly-agreeing fields (not in the firing rule)
    bring the COMBINED probability (rule P x field u-probabilities) back
    under budget. Enforcement decisions are recorded on the result
    (``MatchResult.threshold_enforcement``) and in the audit evidence.
    Patient matching never enforces (plain rule list, no threshold).
    """
    create_matching_tables(conn)
    if approval_threshold is None:
        approval_threshold = getattr(rules, "approval_threshold", None)
    enforce_threshold = approval_threshold \
        if entity_type != "Patient" else None
    candidate_suffixes = fields.get("suffix", [])

    skipped: list[str] = []
    evaluated: list[str] = []
    last_refusal: Optional[dict] = None
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
        verified: dict[str, tuple[bool, dict[str, str], dict[str, str]]] = {}
        for pid in sorted(candidates):
            matched, any_fuzzy, evidence, embed_bands = _verify_candidate(
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
            verified[pid] = (any_fuzzy, evidence, embed_bands)
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
        if rule.band_u_values:
            # FHIR4-20: per-band P selection — the matched embed band(s)
            # choose their u-value in the product. A single surviving
            # band set is needed for an unambiguous P; mixed bands across
            # survivors take the LOOSEST (most conservative) band per
            # embed field.
            merged_bands: dict[str, str] = {}
            order = [b for b, _u in rule.band_u_values]
            for pid in surviving:
                for fname, band in verified[pid][2].items():
                    if fname not in merged_bands or \
                            order.index(band) > order.index(merged_bands[fname]):
                        merged_bands[fname] = band
            p = rule.effective_p(merged_bands)
        else:
            p = rule.p_collision_fuzzy if any_fuzzy else rule.p_collision
        match_type = "fuzzy" if any_fuzzy else "exact"
        enforcement_by_pid: dict[str, dict] = {}
        if enforce_threshold is not None \
                and _exceeds_threshold(p, enforce_threshold):
            # CR-002: the rule alone exceeds the approval budget — each
            # candidate must corroborate the link with additional
            # exactly-agreeing fields until the COMBINED P is under budget.
            corroborated: list[str] = []
            for pid in surviving:
                combined, corroborating = _combined_p_with_corroboration(
                    conn, rule, fields, pid, entity_type, p)
                enforcement_by_pid[pid] = {
                    "required": True,
                    "satisfied": not _exceeds_threshold(
                        combined, enforce_threshold),
                    "rule_id": rule.rule_id,
                    "firing_p": p,
                    "combined_p": combined,
                    "threshold": enforce_threshold,
                    "corroborating_fields": corroborating,
                }
                if enforcement_by_pid[pid]["satisfied"]:
                    corroborated.append(pid)
            if not corroborated:
                last_refusal = enforcement_by_pid[surviving[0]]
                continue  # rule refused for every candidate
            surviving = corroborated
        if len(surviving) == 1:
            matched_id = surviving[0]
            return MatchResult(
                outcome="match",
                rule_id=rule.rule_id,
                confidence=1.0 - enforcement_by_pid[matched_id]["combined_p"]
                if matched_id in enforcement_by_pid else 1.0 - p,
                matched_ids=(matched_id,),
                evidence=verified[matched_id][1],
                skipped_rules=tuple(skipped),
                evaluated_rules=tuple(evaluated),
                match_type=match_type,
                threshold_enforcement=enforcement_by_pid.get(matched_id),
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
        threshold_enforcement=last_refusal,
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
    merged_bands: dict[str, str] = {}
    for pid in sorted(candidates):
        matched, fuzzy, _ev, bands = _verify_candidate(
            conn, rule, fields, pid, entity_type)
        if not matched:
            continue
        if bands:
            merged_bands.update(bands)
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
            confidence=1.0 - (
                rule.effective_p(merged_bands) if rule.band_u_values
                else (rule.p_collision_fuzzy if any_fuzzy else rule.p_collision)),
            matched_ids=(surviving[0],),
            match_type="fuzzy" if any_fuzzy else "exact",
            evaluated_rules=(rule.rule_id,),
        )
    if surviving:
        return MatchResult(
            outcome="ambiguous",
            rule_id=rule.rule_id,
            confidence=1.0 - (
                rule.effective_p(merged_bands) if rule.band_u_values
                else (rule.p_collision_fuzzy if any_fuzzy else rule.p_collision)),
            matched_ids=tuple(surviving),
            match_type="fuzzy" if any_fuzzy else "exact",
            evaluated_rules=(rule.rule_id,),
        )
    return MatchResult(outcome="no_match", evaluated_rules=(rule.rule_id,))
