"""D14 HISTORIAN regression tests (v0.0.26 evolution, iteration 43).

Red-first coverage for:
- QA-D14H-001: ``evaluate_rule`` must share ``match_fields`` semantics for
  EMBED-band rules — bands merge over SURVIVING candidates only, and the
  merge is LOOSEST-wins per embed field (a guard- or suffix-dropped
  candidate must not influence the confidence; a later-sorted tighter band
  must not mask a looser surviving band).
- QA-D14H-002: ``find_contradictions`` field sets are Patient-scoped —
  rows of OTHER entity types (Practitioner/Organization/Location) sharing
  a member id must not leak into patient contradiction detection.
"""

from __future__ import annotations

import duckdb
import pytest

from fhir4ds.matching import corpus as m_corpus
from fhir4ds.matching import engine as m_engine
from fhir4ds.matching import rules as m_rules
from fhir4ds.matching import store as m_store
from fhir4ds.matching.name_embedding import name_distance_band

# Non-fuzzy name pairs per band (verified against the pinned artifact;
# fuzzy-equal pairs would let Category-1 rules preempt the E-rules).
TIGHT = ("rick", "nick")    # band == tight, not name_fuzzy_match
MID = ("rick", "sophia")    # band == mid, not name_fuzzy_match
LOOSE = ("rick", "sue")     # band == loose, not name_fuzzy_match


def _patient(pid, first, *, ssn=None, phone="555-000-0001"):
    r = {
        "resourceType": "Patient",
        "id": pid,
        "name": [{"use": "official", "given": [first], "family": "Ng"}],
        "birthDate": "1990-01-01",
        "telecom": [{"system": "phone", "value": phone}],
    }
    if ssn:
        r["identifier"] = [
            {"system": "http://hl7.org/fhir/sid/us-ssn", "value": ssn}]
    return r


def _e2():
    return next(r for r in m_rules.patient_rules_with_embedding()
                if r.rule_id == "E2")


@pytest.fixture()
def conn():
    c = duckdb.connect()
    m_store.create_matching_tables(c)
    return c


class TestEvaluateRuleBandMergeD14H:
    def test_guard_failed_candidate_band_does_not_leak(self, conn):
        """QA-D14H-001(a): a candidate dropped by the E2 ssn4 guard after
        verification must NOT contribute its (looser) embed band."""
        # a1: tight-band first, ssn4 agrees with the query -> survives.
        # z9: loose-band first, ssn4 DISJOINT -> guard drops it.
        m_store.index_patient(conn, _patient("a1", TIGHT[1], ssn="123-45-6789"))
        m_store.index_patient(conn, _patient("z9", LOOSE[1], ssn="999-99-9999"))
        assert name_distance_band(*TIGHT) == "tight"
        assert name_distance_band(*LOOSE) == "loose"
        query = _patient("q", TIGHT[0], ssn="123-45-6789")
        res = m_engine.evaluate_rule(conn, _e2(), query)
        res_engine = m_engine.match_patient(conn, query, exclude=frozenset({"q"}))
        p_tight = _e2().effective_p({"first": "tight"})
        assert res.outcome == "match"
        assert res_engine.outcome == "match"
        assert res.confidence == pytest.approx(1.0 - p_tight, abs=1e-18)
        assert res.confidence == res_engine.confidence

    def test_multi_survivor_merge_is_loosest_wins(self, conn):
        """QA-D14H-001(b): with two surviving candidates in different
        bands, evaluate_rule must merge LOOSEST (like match_fields), not
        last-writer over sorted candidate order."""
        m_store.index_patient(conn, _patient("a2", MID[1]))    # mid band vs query
        m_store.index_patient(conn, _patient("z9", TIGHT[1]))  # tight, sorts last
        assert name_distance_band(*MID) == "mid"
        query = _patient("q", TIGHT[0])
        res = m_engine.evaluate_rule(conn, _e2(), query)
        res_engine = m_engine.match_patient(conn, query, exclude=frozenset({"q"}))
        p_mid = _e2().effective_p({"first": "mid"})
        assert res.outcome == "ambiguous"
        assert res_engine.outcome == "ambiguous"
        assert res.confidence == pytest.approx(1.0 - p_mid, abs=1e-18)
        assert res.confidence == res_engine.confidence


class TestContradictionsEntityScopedD14H:
    def test_practitioner_rows_do_not_leak_into_patient_contradictions(self, conn):
        """QA-D14H-002: a Practitioner sharing a member id must not create
        a false suffix contradiction between two linked patients."""
        m_store.index_entity(
            conn, "Patient", {"resourceType": "Patient", "id": "pt1"},
            {"first": ["al"], "last": ["zoo"], "dob": ["1980-01-01"],
             "phone": ["5550000000"], "suffix": ["jr"]})
        m_store.index_entity(
            conn, "Patient", {"resourceType": "Patient", "id": "pt2"},
            {"first": ["alan"], "last": ["zoo"], "dob": ["1980-01-01"],
             "phone": ["5550000000"]})  # no patient suffix
        m_store.index_entity(
            conn, "Practitioner",
            {"resourceType": "Practitioner", "id": "pt2"},
            {"last": ["who"], "first": ["doc"], "suffix": ["md"]})
        m_corpus.match_corpus(conn, "run-d14h")
        contradictions = m_corpus.find_contradictions(conn)
        assert contradictions == []

    def test_real_patient_contradiction_still_surfaces(self, conn):
        """Control: a genuine suffix contradiction between two PATIENTS
        (not practitioners) is still detected after the scoping fix.
        (Suffix-conflicting patients never LINK, so the realistic path is a
        suffix added by a re-index AFTER the linkage was written.)"""
        m_store.index_entity(
            conn, "Patient", {"resourceType": "Patient", "id": "p1"},
            {"first": ["al"], "last": ["zoo"], "dob": ["1980-01-01"],
             "phone": ["5550000000"], "suffix": ["jr"]})
        m_store.index_entity(
            conn, "Patient", {"resourceType": "Patient", "id": "p2"},
            {"first": ["al"], "last": ["zoo"], "dob": ["1980-01-01"],
             "phone": ["5550000000"]})
        m_corpus.match_corpus(conn, "run-d14h-2")  # links p1~p2 (no conflict)
        # corpus change: p2 now carries a conflicting suffix; the linkage
        # row persists (same rule, evidence drift is a noop here).
        m_store.index_entity(
            conn, "Patient", {"resourceType": "Patient", "id": "p2"},
            {"first": ["al"], "last": ["zoo"], "dob": ["1980-01-01"],
             "phone": ["5550000000"], "suffix": ["sr"]})
        m_corpus.match_corpus(conn, "run-d14h-2b")
        contradictions = m_corpus.find_contradictions(conn)
        assert len(contradictions) == 1
        assert contradictions[0]["contradictions"][0]["field"] == "suffix"
