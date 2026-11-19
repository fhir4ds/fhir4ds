"""Rule-30 sibling disagreement guard tests (fhir4ds deviation from upstream
table2, Joel-approved 2026-11-17).

Rule 30 (Last Name* + DOB + Phone, P=5.0e-13) has no sibling guard upstream,
so siblings sharing a household phone + last name + DOB link as the same
person. fhir4ds adds ``guards=("ssn4_agreement", "first_name_agreement")``:
after verification passes, the pair is dropped from the rule when BOTH sides
have non-empty ssn4 sets that are disjoint, or BOTH sides have non-empty
first-name sets with no cross-pair match (exact / nickname / fuzzy). A guard
failure skips the rule for that pair — it is NOT a hard negation; any other
rule may still fire.
"""

from __future__ import annotations

import duckdb
import pytest

from fhir4ds.matching import (
    CATEGORY1_RULES,
    create_matching_tables,
    index_patient,
    match_patient,
    register_matching_macros,
)
from fhir4ds.matching.engine import evaluate_rule
from fhir4ds.matching.rules import FIRST_NAME_AGREEMENT, SSN4_AGREEMENT


def _rule(rule_id: str):
    return {r.rule_id: r for r in CATEGORY1_RULES}[rule_id]


def _conn():
    conn = duckdb.connect()
    create_matching_tables(conn)
    register_matching_macros(conn)
    return conn


def _sibling(
    pid: str,
    first: str,
    ssn4: str | None,
    last: str = "Thompson",
    dob: str = "1995-05-05",
    phone: str = "206-555-0123",
    member_id: str | None = None,
    mbi: str | None = None,
) -> dict:
    resource: dict = {
        "resourceType": "Patient",
        "id": pid,
        "name": [{"use": "official", "family": last, "given": [first]}],
        "birthDate": dob,
        "telecom": [{"system": "phone", "value": phone}],
    }
    identifiers = []
    if ssn4 is not None:
        identifiers.append(
            {
                "system": "http://hl7.org/fhir/sid/us-ssn",
                "value": f"123-45-{ssn4}",
            }
        )
    if member_id is not None:
        identifiers.append(
            {"system": "http://example.org/member", "value": member_id}
        )
    if mbi is not None:
        identifiers.append({"system": "http://example.org/mbi", "value": mbi})
    if identifiers:
        resource["identifier"] = identifiers
    return resource


class TestRule30GuardConfiguration:
    def test_rule30_carries_deviation_guards(self):
        by_id = {r.rule_id: r for r in CATEGORY1_RULES}
        assert by_id["30"].guards == (SSN4_AGREEMENT, FIRST_NAME_AGREEMENT)
        # no other rule carries guards (deviation is scoped to rule 30)
        assert all(r.guards == () for r in CATEGORY1_RULES if r.rule_id != "30")

    def test_rule30_fields_and_p_unchanged_by_deviation(self):
        by_id = {r.rule_id: r for r in CATEGORY1_RULES}
        rule = by_id["30"]
        assert rule.fields == (
            ("last", "fuzzy"),
            ("dob", "exact"),
            ("phone", "exact"),
        )
        assert rule.p_collision == pytest.approx(5.0e-13)
        assert rule.p_collision_fuzzy == pytest.approx(1.0e-12)


class TestRule30SiblingGuard:
    def test_sibling_disagreeing_first_and_ssn4_no_match(self):
        # Same household: last + DOB + phone shared; different first names
        # AND disjoint ssn4 -> BOTH guards fail -> rule 30 skipped, and no
        # other rule covers the field set -> no match overall.
        conn = _conn()
        index_patient(conn, _sibling("sib-a", "Alice", "1111"))
        result = match_patient(conn, _sibling("sib-b", "Bob", "2222"))
        assert result.outcome == "no_match"
        assert "30" in result.evaluated_rules  # rule 30 was tried and guarded

    def test_sibling_sharing_first_name_guards_pass(self):
        # Shared first name + agreeing ssn4 -> both guards pass. The PAIR
        # matches (first-firing rule 02, which preempts 30 at lower P);
        # rule 30 in isolation also fires (guard passes).
        conn = _conn()
        index_patient(conn, _sibling("sib-a", "Alice", "1111"))
        patient = _sibling("sib-b", "Alice", "1111")
        result = match_patient(conn, patient)
        assert result.outcome == "match"
        assert result.matched_ids == ("sib-a",)
        isolated = evaluate_rule(conn, _rule("30"), patient)
        assert isolated.outcome == "match"
        assert isolated.matched_ids == ("sib-a",)

    def test_sibling_one_side_missing_ssn4_guard_passes(self):
        # ssn4 present on one side only -> ssn4 guard passes (no evidence of
        # disagreement); first names agree -> rule 30 fires in isolation.
        conn = _conn()
        index_patient(conn, _sibling("sib-a", "Alice", "1111"))
        patient = _sibling("sib-b", "Alice", None)
        result = match_patient(conn, patient)
        assert result.outcome == "match"
        isolated = evaluate_rule(conn, _rule("30"), patient)
        assert isolated.outcome == "match"
        assert isolated.matched_ids == ("sib-a",)

    def test_missing_ssn4_does_not_bypass_first_name_guard(self):
        # One-sided ssn4 passes the ssn4 guard, but disagreeing first names
        # still fail the first-name guard -> no match via rule 30.
        conn = _conn()
        index_patient(conn, _sibling("sib-a", "Alice", "1111"))
        result = match_patient(conn, _sibling("sib-b", "Bob", None))
        assert result.outcome == "no_match"

    def test_fuzzy_first_name_agreement_passes_guard(self):
        # Guard agreement uses name_fuzzy_match: "alicia" vs "aliciq"
        # (DL<=1, both >= 5 chars) counts as agreement -> with agreeing
        # ssn4 the guard passes and rule 30 fires in isolation; with
        # disjoint ssn4 the ssn4 guard still fails.
        conn = _conn()
        index_patient(conn, _sibling("sib-a", "Alicia", "1111"))
        agreeing = _sibling("sib-b", "Aliciq", "1111")
        isolated = evaluate_rule(conn, _rule("30"), agreeing)
        assert isolated.outcome == "match"
        disjoint = _sibling("sib-b", "Aliciq", "2222")
        result = match_patient(conn, disjoint)
        assert result.outcome == "no_match"

    def test_nickname_first_name_agreement_passes_guard(self):
        # "Bob" vs "Robert" agree via nickname set -> first-name guard passes.
        conn = _conn()
        index_patient(conn, _sibling("sib-a", "Robert", None))
        patient = _sibling("sib-b", "Bob", None)
        result = match_patient(conn, patient)
        assert result.outcome == "match"
        isolated = evaluate_rule(conn, _rule("30"), patient)
        assert isolated.outcome == "match"

    def test_guard_failure_is_not_hard_negation(self):
        # Siblings failing rule 30's guards still match through ANOTHER rule
        # (17: Phone + MBI, P=1e-12 > rule 30's 5e-13, so rule 30 is
        # evaluated first and guarded out) -> the guard skips rule 30 only;
        # the pair links anyway.
        conn = _conn()
        index_patient(conn, _sibling("sib-a", "Alice", "1111", mbi="1EG4-TE5-MK73"))
        result = match_patient(
            conn, _sibling("sib-b", "Bob", "2222", mbi="1EG4-TE5-MK73")
        )
        assert result.outcome == "match"
        assert result.rule_id == "17"
        assert "30" in result.evaluated_rules  # rule 30 was tried, guarded out

    def test_sibling_sharing_first_but_disjoint_ssn4_matches_via_rule02(self):
        # The deviation is scoped to rule 30: sharing the first name lets
        # the LOWER-P unguarded rule 02 (First + Last* + DOB* + Phone) fire
        # even though rule 30's ssn4 guard would fail. Documented scope of
        # the Joel-approved deviation.
        conn = _conn()
        index_patient(conn, _sibling("sib-a", "Alice", "1111"))
        patient = _sibling("sib-b", "Alice", "2222")
        result = match_patient(conn, patient)
        assert result.outcome == "match"
        assert result.rule_id == "02"
        # rule 30 in isolation is still guarded out (disjoint ssn4)
        isolated = evaluate_rule(conn, _rule("30"), patient)
        assert isolated.outcome == "no_match"
