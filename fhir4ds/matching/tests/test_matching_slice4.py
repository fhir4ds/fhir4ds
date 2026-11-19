"""Slice-4 tests: corpus pass, membership components, contradictions, views."""

from __future__ import annotations

import duckdb
import pytest

from fhir4ds.matching import (
    CorpusReport,
    build_membership,
    create_audit_tables,
    create_linkage_tables,
    create_matching_tables,
    find_contradictions,
    index_patient,
    individual_context_patients,
    individual_patients_view,
    match_corpus,
    upsert_linkage,
)
from fhir4ds.matching.engine import MatchResult


def _conn():
    conn = duckdb.connect()
    create_matching_tables(conn)
    create_linkage_tables(conn)
    create_audit_tables(conn)
    return conn


def _patient(
    pid,
    *,
    first="Alice",
    last="Smith",
    dob="1990-01-01",
    phone="212-555-0100",
    ssn4=None,
    street=None,
    suffix=None,
):
    resource = {
        "resourceType": "Patient",
        "id": pid,
        "name": [
            {
                "use": "official",
                "family": last + (f" {suffix}" if suffix else ""),
                "given": [first],
            }
        ],
        "birthDate": dob,
        "telecom": [{"system": "phone", "value": phone}],
    }
    if street is not None:
        resource["address"] = [{"line": [street]}]
    if ssn4 is not None:
        resource["identifier"] = [
            {"system": "http://hl7.org/fhir/sid/us-ssn", "value": f"123-45-{ssn4}"}
        ]
    return resource


# 6-patient corpus fixture per the slice brief: a duplicate pair, an
# ambiguous trio (three mutually-identical patients -> every direction sees
# TWO candidates -> ambiguous, no linkage), and two unique patients.
DUP_1 = _patient("pat-d1")
DUP_2 = _patient("pat-d2")
TRIO_1 = _patient("pat-t1", first="Bob", last="Jones", dob="1980-05-05", phone="404-555-0181")
TRIO_2 = _patient("pat-t2", first="Bob", last="Jones", dob="1980-05-05", phone="404-555-0181")
TRIO_3 = _patient("pat-t3", first="Bob", last="Jones", dob="1980-05-05", phone="404-555-0181")
UNIQ_1 = _patient("pat-u1", first="Zoya", last="Quinn", dob="1960-06-06", phone="917-555-9999")
UNIQ_2 = _patient("pat-u2", first="Carl", last="Vega", dob="1975-12-12", phone="646-555-0123")

FIXTURE = [DUP_1, DUP_2, TRIO_1, TRIO_2, TRIO_3, UNIQ_1, UNIQ_2]


def _index_all(conn, resources):
    for resource in resources:
        index_patient(conn, resource)


# ---------------------------------------------------------------------------
# Corpus pass
# ---------------------------------------------------------------------------


class TestMatchCorpus:
    def test_report_counts_and_linkage_rows(self):
        conn = _conn()
        _index_all(conn, FIXTURE)
        report = match_corpus(conn, "run-1")
        assert isinstance(report, CorpusReport)
        assert report.patients_evaluated == 7
        assert report.match_outcomes == 2  # pat-d1 and pat-d2 match each other
        assert report.ambiguous_outcomes == 3  # trio: each sees two candidates
        assert report.no_match_outcomes == 2
        assert report.unique_pairs == 1  # both directions -> one canonical pair
        assert report.links_created == 1
        rows = conn.execute(
            "SELECT linkage_id FROM linkage ORDER BY linkage_id"
        ).fetchall()
        assert [r[0] for r in rows] == ["Patient/pat-d1|Patient/pat-d2"]

    def test_audit_rows_written_for_every_decision(self):
        conn = _conn()
        _index_all(conn, FIXTURE)
        match_corpus(conn, "run-1")
        rows = conn.execute(
            "SELECT patient_id, outcome, candidate_id FROM match_audit "
            "WHERE run_id = 'run-1' ORDER BY patient_id"
        ).fetchall()
        by_patient = {r[0]: (r[1], r[2]) for r in rows}
        assert len(rows) == 7
        assert by_patient["pat-d1"] == ("match", "pat-d2")
        assert by_patient["pat-d2"] == ("match", "pat-d1")
        for pid in ("pat-t1", "pat-t2", "pat-t3"):
            assert by_patient[pid] == ("ambiguous", None)
        for pid in ("pat-u1", "pat-u2"):
            assert by_patient[pid] == ("no_match", None)

    def test_rerun_is_idempotent_for_linkage(self):
        conn = _conn()
        _index_all(conn, FIXTURE)
        first = match_corpus(conn, "run-1")
        second = match_corpus(conn, "run-2")
        assert second.unique_pairs == 1
        assert second.links_created == 0  # upsert noop
        assert conn.execute("SELECT COUNT(*) FROM linkage").fetchone()[0] == 1
        assert first.links_created == 1

    def test_empty_corpus(self):
        conn = _conn()
        report = match_corpus(conn, "run-1")
        assert report.counts == {
            "patients_evaluated": 0,
            "match_outcomes": 0,
            "ambiguous_outcomes": 0,
            "no_match_outcomes": 0,
            "unique_pairs": 0,
            "links_created": 0,
        }

    def test_run_id_validation(self):
        conn = _conn()
        with pytest.raises(ValueError):
            match_corpus(conn, "")


# ---------------------------------------------------------------------------
# Membership / connected components
# ---------------------------------------------------------------------------


class TestBuildMembership:
    def test_components_and_identity_rows(self):
        conn = _conn()
        _index_all(conn, FIXTURE)
        match_corpus(conn, "run-1")
        components = build_membership(conn)
        assert components == 6  # dup pair (1) + trio singletons (3) + uniques (2)
        rows = dict(
            conn.execute(
                "SELECT member_patient_id, individual_id FROM patient_membership"
            ).fetchall()
        )
        assert len(rows) == 7  # identity rows for unlinked patients
        assert rows["pat-d1"] == "pat-d1"  # smallest member is the component id
        assert rows["pat-d2"] == "pat-d1"
        assert rows["pat-t1"] == "pat-t1"
        assert rows["pat-t2"] == "pat-t2"
        assert rows["pat-t3"] == "pat-t3"
        assert rows["pat-u1"] == "pat-u1"
        assert rows["pat-u2"] == "pat-u2"

    def test_transitive_component(self):
        conn = _conn()
        # A ~ B via one rule, B ~ C via another -> one component of three,
        # labeled by the smallest member id.
        a = _patient("p-a", first="Eve", last="Adams", dob="1970-01-01", phone="312-555-0111")
        b = _patient("p-b", first="Eve", last="Adams", dob="1970-01-01", phone="312-555-0111")
        c = _patient("p-c", first="Eve", last="Adams", dob="1970-01-01", phone="312-555-0222")
        _index_all(conn, [a, b, c])
        # Link A~B and B~C directly (engine pair decisions land per-pair).
        result_ab = MatchResult(
            outcome="match", rule_id="11", confidence=0.99, matched_ids=("p-b",)
        )
        result_bc = MatchResult(
            outcome="match", rule_id="11", confidence=0.99, matched_ids=("p-c",)
        )
        upsert_linkage(conn, result_ab, "p-a", "p-b")
        upsert_linkage(conn, result_bc, "p-b", "p-c")
        assert build_membership(conn) == 1
        rows = dict(
            conn.execute(
                "SELECT member_patient_id, individual_id FROM patient_membership"
            ).fetchall()
        )
        assert rows == {"p-a": "p-a", "p-b": "p-a", "p-c": "p-a"}

    def test_veto_pairs_split_a_component(self):
        conn = _conn()
        _index_all(conn, FIXTURE)
        match_corpus(conn, "run-1")
        components = build_membership(conn, veto_pairs=[("pat-d2", "pat-d1")])
        assert components == 7  # the dup pair is split back into singletons
        rows = dict(
            conn.execute(
                "SELECT member_patient_id, individual_id FROM patient_membership"
            ).fetchall()
        )
        assert rows["pat-d1"] == "pat-d1"
        assert rows["pat-d2"] == "pat-d2"
        # veto also accepts Patient/ refs
        components = build_membership(conn, veto_pairs=[("Patient/pat-d1", "Patient/pat-d2")])
        assert components == 7

    def test_determinism_shuffled_ingest_identical_membership(self):
        rows_a = None
        rows_b = None
        for ordering in (
            FIXTURE,
            list(reversed(FIXTURE)),
            [TRIO_2, UNIQ_1, DUP_1, TRIO_3, DUP_2, UNIQ_2, TRIO_1],
        ):
            conn = _conn()
            _index_all(conn, ordering)
            match_corpus(conn, "run-x")
            build_membership(conn)
            rows = conn.execute(
                "SELECT member_patient_id, individual_id FROM patient_membership "
                "ORDER BY member_patient_id"
            ).fetchall()
            if rows_a is None:
                rows_a = rows
            else:
                rows_b = rows
                assert rows_a == rows_b

    def test_rebuild_replaces_prior_state(self):
        conn = _conn()
        _index_all(conn, [DUP_1, DUP_2])
        match_corpus(conn, "run-1")
        assert build_membership(conn) == 1
        conn.execute("DELETE FROM linkage")
        assert build_membership(conn) == 2  # identity again after links removed
        rows = dict(
            conn.execute(
                "SELECT member_patient_id, individual_id FROM patient_membership"
            ).fetchall()
        )
        assert rows == {"pat-d1": "pat-d1", "pat-d2": "pat-d2"}

    def test_individual_context_patients(self):
        conn = _conn()
        _index_all(conn, FIXTURE)
        match_corpus(conn, "run-1")
        build_membership(conn)
        patients = individual_context_patients(conn)
        assert patients == [
            ("pat-d1", 2),
            ("pat-t1", 1),
            ("pat-t2", 1),
            ("pat-t3", 1),
            ("pat-u1", 1),
            ("pat-u2", 1),
        ]


# ---------------------------------------------------------------------------
# Hard contradictions (v1: surface only, never auto-split)
# ---------------------------------------------------------------------------


def _match_result(rule_id="11", confidence=1.0 - 2e-12):
    return MatchResult(
        outcome="match",
        rule_id=rule_id,
        confidence=confidence,
        matched_ids=("x",),
        evidence={},
        match_type="exact",
    )


class TestFindContradictions:
    def test_disjoint_ssn4_flagged(self):
        conn = _conn()
        # Linked via rule 11 (first + dob + phone) while carrying disjoint
        # SSN last-4 — rule 04 cannot fire, so the link survives with the
        # hard contradiction.
        a = _patient("p-a", ssn4="1111")
        b = _patient("p-b", ssn4="2222")
        _index_all(conn, [a, b])
        report = match_corpus(conn, "run-1")
        assert report.match_outcomes == 2  # they did link
        build_membership(conn)
        found = find_contradictions(conn)
        assert len(found) == 1
        assert found[0]["individual_id"] == "p-a"
        assert found[0]["members"] == ["p-a", "p-b"]
        (contradiction,) = found[0]["contradictions"]
        assert contradiction["field"] == "ssn4"
        assert contradiction["members"] == ["p-a", "p-b"]
        assert contradiction["values"] == {"p-a": ["1111"], "p-b": ["2222"]}

    def test_plus_minus_1_day_dob_not_flagged(self):
        conn = _conn()
        # Rule 01 (all-fuzzy): same names, same street, DOB one day apart.
        a = _patient("p-a", first="Mary", last="Ng", dob="1988-03-10", street="12 Cedar St")
        b = _patient("p-b", first="Mary", last="Ng", dob="1988-03-11", street="12 Cedar St")
        _index_all(conn, [a, b])
        report = match_corpus(conn, "run-1")
        assert report.match_outcomes == 2  # fuzzy DOB still links them
        build_membership(conn)
        assert find_contradictions(conn) == []  # ±1 day is NOT a contradiction

    def test_same_ssn4_not_flagged(self):
        conn = _conn()
        a = _patient("p-a", ssn4="1111")
        b = _patient("p-b", ssn4="1111")
        _index_all(conn, [a, b])
        report = match_corpus(conn, "run-1")
        assert report.match_outcomes == 2
        build_membership(conn)
        assert find_contradictions(conn) == []

    def test_far_apart_dobs_flagged(self):
        conn = _conn()
        # Every engine rule requires a DOB match (exact or ±1 day), so a
        # far-apart-DOB component can only arise from a manual/legacy
        # Linkage row — the detector must still surface it.
        a = _patient("p-a", first="Robert", last="Frost", dob="1960-01-01", phone="212-555-0100")
        b = _patient("p-b", first="Bob", last="Frost", dob="1975-06-15", phone="212-555-0199")
        _index_all(conn, [a, b])
        upsert_linkage(conn, _match_result(), "p-a", "p-b")
        build_membership(conn)
        found = find_contradictions(conn)
        assert len(found) == 1
        kinds = {c["field"] for c in found[0]["contradictions"]}
        assert "dob" in kinds

    def test_suffix_conflict_flagged_when_linkage_present(self):
        conn = _conn()
        # The engine's suffix negation prevents linking disjoint suffixes,
        # so this class can only arise from a manual/legacy Linkage row —
        # the detector must still surface it.
        a = _patient("p-a", last="Smith", suffix="Jr")
        b = _patient("p-b", last="Smith", suffix="Sr")
        # Distinguish them so the engine does not link (suffix negation) —
        # insert the linkage row manually as a legacy artifact.
        a["telecom"] = [{"system": "phone", "value": "212-555-0100"}]
        b["telecom"] = [{"system": "phone", "value": "212-555-0199"}]
        _index_all(conn, [a, b])
        upsert_linkage(conn, _match_result(), "p-a", "p-b")
        build_membership(conn)
        found = find_contradictions(conn)
        assert len(found) == 1
        (contradiction,) = found[0]["contradictions"]
        assert contradiction["field"] == "suffix"
        assert contradiction["values"] == {"p-a": ["jr"], "p-b": ["sr"]}
        # The operator path: veto the pair and rebuild.
        assert build_membership(conn, veto_pairs=[("p-a", "p-b")]) == 2
        # find_contradictions recomputes components independently, so the
        # veto must be handed to it as well.
        assert find_contradictions(conn, veto_pairs=[("p-a", "p-b")]) == []

    def test_singleton_components_not_reported(self):
        conn = _conn()
        _index_all(conn, [UNIQ_1, UNIQ_2])
        match_corpus(conn, "run-1")
        build_membership(conn)
        assert find_contradictions(conn) == []


# ---------------------------------------------------------------------------
# §5 substrate: individual-context views
# ---------------------------------------------------------------------------


class TestIndividualViews:
    def test_view_row_counts(self):
        conn = _conn()
        _index_all(conn, FIXTURE)
        match_corpus(conn, "run-1")
        components = build_membership(conn)
        individual_patients_view(conn)
        individuals = conn.execute(
            "SELECT patient_id FROM _individual_patients ORDER BY patient_id"
        ).fetchall()
        assert len(individuals) == components == 6
        mapping = dict(
            conn.execute(
                "SELECT member_patient_id, individual_id FROM _individual_resource_map"
            ).fetchall()
        )
        assert len(mapping) == 7  # one row per member patient
        assert mapping["pat-d2"] == "pat-d1"
        assert mapping["pat-u1"] == "pat-u1"

    def test_views_refresh_after_rebuild(self):
        conn = _conn()
        _index_all(conn, [DUP_1, DUP_2])
        match_corpus(conn, "run-1")
        build_membership(conn)
        individual_patients_view(conn)
        assert conn.execute("SELECT COUNT(*) FROM _individual_patients").fetchone()[0] == 1
        conn.execute("DELETE FROM linkage")
        build_membership(conn)
        individual_patients_view(conn)
        assert conn.execute("SELECT COUNT(*) FROM _individual_patients").fetchone()[0] == 2
