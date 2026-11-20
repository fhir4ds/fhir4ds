"""AMUX-150 chunk B — RelatedPerson piggyback dedup (rule RP1).

RelatedPersons have no identity rule table of their own (FDD §3.4): they
are duplicates iff they point at the SAME patient individual and carry
the same relationship over overlapping/nested periods. This is a pure
function over the membership table + the resource list:

- Group RelatedPersons by their RESOLVED patient master id
  (``patient_membership.individual_id`` via the referenced
  ``Patient/<id>``); an unresolvable/unlinked patient groups by the raw
  patient reference (identity grouping).
- Within a group, a pair is a duplicate iff their ``relationship``
  coding sets intersect (any-intersection, system canonicalized by
  lowercasing — systems are compared as authored URLs) AND their
  ``period`` ranges overlap-or-nest (one-sided bounds are unbounded).
- Every qualifying pair writes the SAME pairwise matching Linkage
  pattern with rule id ``RP1`` and one audit row per decision, under the
  caller's ``run_id`` namespace.

Deterministic: pairs iterate in sorted rid order; no wall-clock.
"""

from __future__ import annotations

import datetime as _dt
from dataclasses import asdict, dataclass
from typing import Optional

import duckdb

from .audit import record_match_audit
from .engine import MatchResult
from .linkage import upsert_linkage

__all__ = ["RelatedPersonReport", "match_related_persons", "RP1"]

#: Rule id + collision budget for the piggyback decision (documented
#: fhir4ds estimate: same patient individual + same relationship code +
#: overlapping period).
RP1 = "RP1"
_RP1_P_COLLISION = 1e-6


@dataclass
class RelatedPersonReport:
    related_persons: int = 0
    groups: int = 0
    pairs_evaluated: int = 0
    pairs_matched: int = 0
    links_created: int = 0

    @property
    def counts(self) -> dict[str, int]:
        return asdict(self)


def _member_id(conn: duckdb.DuckDBPyConnection) -> dict[str, str]:
    """member patient id -> individual id (identity rows included)."""
    rows = conn.execute(
        "SELECT member_patient_id, individual_id FROM patient_membership "
        "ORDER BY member_patient_id").fetchall()
    return {r[0]: r[1] for r in rows}


def _patient_ref(resource: dict) -> Optional[str]:
    """Normalized ``Patient/<id>`` reference of ``RelatedPerson.patient``
    (anchored tail, ``_history``-stripped — loader doctrine)."""
    import re

    patient = resource.get("patient")
    if not isinstance(patient, dict):
        return None
    reference = patient.get("reference")
    if not isinstance(reference, str) or not reference:
        return None
    cleaned = re.sub(r"/_history/[A-Za-z0-9\-.]+$", "", reference)
    match = re.search(r"(?:^|/)Patient/([A-Za-z0-9\-.]{1,64})$", cleaned)
    return f"Patient/{match.group(1)}" if match else None


def _relationship_codes(resource: dict) -> frozenset[tuple[str, str]]:
    codes: set[tuple[str, str]] = set()
    for coding_list in resource.get("relationship") or []:
        if not isinstance(coding_list, dict):
            continue
        for coding in coding_list.get("coding") or []:
            if not isinstance(coding, dict):
                continue
            code = coding.get("code")
            system = coding.get("system")
            if isinstance(code, str) and code and isinstance(system, str) \
                    and system:
                codes.add((system.lower(), code))
    return frozenset(codes)


def _parse_bound(raw) -> Optional[_dt.datetime]:
    if not isinstance(raw, str) or not raw:
        return None
    try:
        return _dt.datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def _periods_overlap_or_nest(a: dict, b: dict) -> bool:
    """Inclusive overlap test with one-sided-unbounded bounds; a malformed
    bound on one side degrades to False (conservative miss)."""
    a_start = _parse_bound(a.get("start"))
    a_end = _parse_bound(a.get("end"))
    b_start = _parse_bound(b.get("start"))
    b_end = _parse_bound(b.get("end"))
    if a_start is None and a_end is None and a.get("start") is not None:
        return False
    if b_start is None and b_end is None and b.get("start") is not None:
        return False
    if a.get("start") is not None and a_start is None:
        return False
    if a.get("end") is not None and a_end is None:
        return False
    if b.get("start") is not None and b_start is None:
        return False
    if b.get("end") is not None and b_end is None:
        return False
    if a_start is not None and b_end is not None and a_start > b_end:
        return False
    if b_start is not None and a_end is not None and b_start > a_end:
        return False
    return True


def _group_key(resource: dict, membership: dict[str, str]) -> Optional[str]:
    patient_ref = _patient_ref(resource)
    if patient_ref is None:
        return None
    member_id = patient_ref[len("Patient/"):]
    individual = membership.get(member_id)
    return f"individual:{individual}" if individual is not None \
        else f"unresolved:{patient_ref}"


def match_related_persons(
    conn: duckdb.DuckDBPyConnection,
    run_id: str,
    related_persons: list[dict],
    *,
    membership: Optional[dict[str, str]] = None,
) -> RelatedPersonReport:
    """Dedup RelatedPersons (RP1) and write pairwise Linkage + audit rows.

    ``membership``: member patient id -> individual id (e.g. from
    ``build_membership``); ``None`` reads ``patient_membership`` when the
    table exists, else every patient groups by its own reference.
    """
    if not isinstance(run_id, str) or not run_id:
        raise ValueError("run_id must be a non-empty string")
    if membership is None:
        try:
            membership = _member_id(conn)
        except duckdb.Error:
            membership = {}
    report = RelatedPersonReport()

    groups: dict[str, list[dict]] = {}
    singles: list[dict] = []
    for resource in related_persons:
        if not isinstance(resource, dict) \
                or resource.get("resourceType") != "RelatedPerson":
            continue
        report.related_persons += 1
        key = _group_key(resource, membership)
        if key is None:
            singles.append(resource)
        else:
            groups.setdefault(key, []).append(resource)

    report.groups = len(groups)
    evidence_base = {"rule": RP1}
    for key in sorted(groups):
        members = sorted(
            groups[key], key=lambda r: (
                r.get("id") if isinstance(r.get("id"), str) else ""))
        for i, left in enumerate(members):
            for right in members[i + 1:]:
                report.pairs_evaluated += 1
                shared = _relationship_codes(left) & _relationship_codes(
                    right)
                if not shared:
                    continue
                left_period = left.get("period")
                right_period = right.get("period")
                left_period = left_period if isinstance(
                    left_period, dict) else {}
                right_period = right_period if isinstance(
                    right_period, dict) else {}
                if not _periods_overlap_or_nest(left_period, right_period):
                    continue
                left_id = left.get("id")
                right_id = right.get("id")
                if not isinstance(left_id, str) or not isinstance(
                        right_id, str):
                    continue
                result = MatchResult(
                    outcome="match",
                    rule_id=RP1,
                    confidence=1.0 - _RP1_P_COLLISION,
                    matched_ids=(right_id,),
                    match_type="exact",
                    evidence=dict(
                        evidence_base,
                        group=key,
                        relationship="|".join(
                            f"{system}|{code}" for system, code
                            in sorted(shared)),
                    ),
                )
                record_match_audit(conn, run_id, left_id, result)
                outcome = upsert_linkage(conn, result, left_id, right_id,
                                         entity_type="RelatedPerson")
                report.pairs_matched += 1
                if outcome["action"] == "created":
                    report.links_created += 1
    # No-patient-reference RelatedPersons never pair; audit one no_match
    # row each so the decision is reconstructible.
    for resource in singles:
        rid = resource.get("id")
        if not isinstance(rid, str):
            continue
        record_match_audit(
            conn, run_id, rid,
            MatchResult(outcome="no_match", evaluated_rules=(RP1,)))
    return report
