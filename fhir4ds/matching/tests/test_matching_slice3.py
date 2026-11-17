"""Slice-3 tests: Linkage writer, audit trail, ingest hook, determinism."""

from __future__ import annotations

import json

import duckdb
import pytest

from fhir4ds.matching import (
    MATCHING_EXTENSION_URL,
    IngestReport,
    build_linkage_resource,
    canonical_pair_key,
    create_audit_tables,
    create_linkage_tables,
    create_matching_tables,
    index_patient,
    load_linkage_resources,
    maybe_match_on_ingest,
    match_on_ingest,
    match_patient,
    record_match_audit,
    upsert_linkage,
)
from fhir4ds.matching.engine import MatchResult


def _conn():
    conn = duckdb.connect()
    create_matching_tables(conn)
    create_linkage_tables(conn)
    create_audit_tables(conn)
    return conn


def _patient(pid, *, first="Alice", last="Smith", dob="1990-01-01", phone="212-555-0100"):
    return {
        "resourceType": "Patient",
        "id": pid,
        "name": [{"use": "official", "family": last, "given": [first]}],
        "birthDate": dob,
        "telecom": [{"system": "phone", "value": phone}],
    }


# A precise-duplicate pair (rule 11: first + dob + phone, all exact)
A1 = _patient("pat-a1")
A2 = _patient("pat-a2")
A3 = _patient("pat-a3")  # third copy -> ambiguous over {A1, A2}
UNIQUE = _patient("pat-uniq", first="Zoya", last="Quinn", dob="1960-06-06", phone="917-555-9999")


def _match_result(rule_id="11", evidence=None, confidence=1.0 - 2e-12):
    return MatchResult(
        outcome="match",
        rule_id=rule_id,
        confidence=confidence,
        matched_ids=("pat-a1",),
        evidence=evidence if evidence is not None else {"first": "alice", "dob": "1990-01-01", "phone": "2125550100"},
        match_type="exact",
    )


# ---------------------------------------------------------------------------
# Linkage resource shape
# ---------------------------------------------------------------------------


class TestLinkageResourceShape:
    def test_r4_fields_and_extension(self):
        resource = build_linkage_resource(_match_result(), "pat-a2", "pat-a1")
        assert resource["resourceType"] == "Linkage"
        assert resource["active"] is True
        assert resource["item"][0] == {
            "type": "source",
            "resource": {"reference": "Patient/pat-a1"},
        }
        assert resource["item"][1] == {
            "type": "alternate",
            "resource": {"reference": "Patient/pat-a2"},
        }
        assert len(resource["extension"]) == 1
        ext = resource["extension"][0]
        assert ext["url"] == MATCHING_EXTENSION_URL
        sub = {e["url"]: e for e in ext["extension"]}
        assert sub["ruleId"] == {"url": "ruleId", "valueString": "11"}
        assert sub["matchType"] == {"url": "matchType", "valueString": "exact"}
        assert sub["confidence"]["valueDecimal"] == pytest.approx(1.0 - 2e-12)
        # determinism: NO wall-clock timestamp — evaluatedAt carries no value
        assert sub["evaluatedAt"] == {"url": "evaluatedAt"}
        evidence_entries = {
            e["url"]: e["valueString"] for e in sub["evidence"]["extension"]
        }
        assert evidence_entries == {
            "first": "alice",
            "dob": "1990-01-01",
            "phone": "2125550100",
        }

    def test_canonical_ordering_both_directions(self):
        forward = build_linkage_resource(_match_result(), "pat-a2", "pat-a1")
        backward = build_linkage_resource(_match_result(), "pat-a1", "pat-a2")
        assert forward == backward
        assert canonical_pair_key("pat-b", "pat-a") == "Patient/pat-a|Patient/pat-b"
        # source is ALWAYS the lexicographically-smallest id
        assert forward["item"][0]["resource"]["reference"] == "Patient/pat-a1"

    def test_fuzzy_evidence_is_direction_independent(self):
        ev_new_first = _match_result(evidence={"last": "thompsno~thompson"})
        ev_existing_first = _match_result(evidence={"last": "thompson~thompsno"})
        r1 = build_linkage_resource(ev_new_first, "pat-x", "pat-y")
        r2 = build_linkage_resource(ev_existing_first, "pat-y", "pat-x")
        assert r1 == r2

    def test_missing_rule_id_rejected(self):
        with pytest.raises(ValueError):
            build_linkage_resource(MatchResult(outcome="match"), "a", "b")


# ---------------------------------------------------------------------------
# upsert semantics
# ---------------------------------------------------------------------------


class TestUpsertLinkage:
    def test_created_then_noop(self):
        conn = _conn()
        first = upsert_linkage(conn, _match_result(), "pat-a2", "pat-a1")
        assert first["action"] == "created"
        second = upsert_linkage(conn, _match_result(), "pat-a1", "pat-a2")
        assert second["action"] == "noop"
        assert second["resource"] == first["resource"]
        assert conn.execute("SELECT COUNT(*) FROM linkage").fetchone()[0] == 1

    def test_rule_change_overwrites(self):
        conn = _conn()
        upsert_linkage(conn, _match_result(rule_id="11"), "pat-a2", "pat-a1")
        changed = upsert_linkage(conn, _match_result(rule_id="12"), "pat-a2", "pat-a1")
        assert changed["action"] == "overwritten"
        row = conn.execute(
            "SELECT rule_id, resource FROM linkage WHERE linkage_id = ?",
            [canonical_pair_key("pat-a1", "pat-a2")],
        ).fetchone()
        assert row[0] == "12"
        assert json.loads(row[1])["extension"][0]["extension"][0]["valueString"] == "12"

    def test_extracted_columns(self):
        conn = _conn()
        upsert_linkage(conn, _match_result(), "pat-a2", "pat-a1")
        row = conn.execute(
            "SELECT linkage_id, rule_id, match_type, confidence FROM linkage"
        ).fetchone()
        assert row == (
            "Patient/pat-a1|Patient/pat-a2",
            "11",
            "exact",
            pytest.approx(1.0 - 2e-12),
        )

    def test_load_linkage_resources(self):
        conn = _conn()
        upsert_linkage(conn, _match_result(), "pat-a2", "pat-a1")
        upsert_linkage(
            conn,
            _match_result(rule_id="11", evidence={"first": "zoya"}),
            "pat-uniq",
            "pat-zeta",
        )
        resources = load_linkage_resources(conn)
        assert [r["item"][0]["resource"]["reference"] for r in resources] == [
            "Patient/pat-a1",
            "Patient/pat-uniq",
        ]


# ---------------------------------------------------------------------------
# audit rows for all three outcomes
# ---------------------------------------------------------------------------


class TestMatchAudit:
    def _rows(self, conn):
        return conn.execute(
            "SELECT run_id, patient_id, candidate_id, outcome, rule_id, "
            "confidence, evidence FROM match_audit ORDER BY patient_id, candidate_id"
        ).fetchall()

    def test_match_ambiguous_no_match_rows(self):
        conn = _conn()
        for p in (A1, A2, UNIQUE):
            index_patient(conn, p)
        record_match_audit(conn, "run-1", "pat-a3", match_patient(conn, A3))
        record_match_audit(
            conn, "run-1", "pat-uniq", match_patient(conn, UNIQUE, exclude={"pat-uniq"})
        )
        rows = self._rows(conn)
        # A3 is ambiguous over {A1, A2}: exactly one row, candidates in evidence
        ambiguous = [r for r in rows if r[3] == "ambiguous"]
        assert len(ambiguous) == 1
        assert ambiguous[0][2] is None  # candidate_id NULL
        assert json.loads(ambiguous[0][6]) == {"candidates": ["pat-a1", "pat-a2"]}
        # rule 02 (first + last* + dob* + phone) outranks rule 11 in the
        # deterministic P(collision)-ascending rule order
        assert ambiguous[0][4] == "02"
        # no_match: one row, NULL candidate/rule/confidence
        no_match = [r for r in rows if r[3] == "no_match"]
        assert len(no_match) == 1
        assert no_match[0][2] is None and no_match[0][4] is None
        assert no_match[0][5] is None
        assert "evaluatedRules" in json.loads(no_match[0][6])
        # match rows: one per matched pair
        record_match_audit(conn, "run-1", "pat-a2", match_patient(conn, A2, exclude={"pat-a2"}))
        rows = self._rows(conn)
        match_rows = [r for r in rows if r[3] == "match"]
        assert len(match_rows) == 1
        assert match_rows[0][2] == "pat-a1"
        assert match_rows[0][4] == "02"
        assert match_rows[0][5] == pytest.approx(1.0 - 2e-12)
        assert json.loads(match_rows[0][6])["first"] == "alice"
    def test_match_outcome_writes_one_row_per_matched_id(self):
        conn = _conn()
        record_match_audit(
            conn,
            "run-1",
            "p",
            MatchResult(outcome="match", rule_id="11", confidence=0.9, matched_ids=("c1", "c2")),
        )
        rows = self._rows(conn)
        assert [r[2] for r in rows] == ["c1", "c2"]

    def test_run_id_required(self):
        conn = _conn()
        with pytest.raises(ValueError):
            record_match_audit(conn, "", "p", MatchResult(outcome="no_match"))


# ---------------------------------------------------------------------------
# ingest hook end-to-end
# ---------------------------------------------------------------------------


class TestMatchOnIngest:
    def test_e2e_two_dup_one_ambiguous_one_unique(self):
        conn = _conn()
        report = match_on_ingest(
            conn, [A1, A2, A3, UNIQUE, {"resourceType": "Observation", "id": "skip"}], "run-1"
        )
        assert isinstance(report, IngestReport)
        # A1 no_match; A2 matches A1; A3 ambiguous over {A1,A2}; UNIQUE no_match
        assert report.counts == {
            "indexed": 4,
            "matched": 1,
            "ambiguous": 1,
            "no_match": 2,
            "links_created": 1,
        }
        resources = load_linkage_resources(conn)
        assert len(resources) == 1
        assert resources[0]["item"][0]["resource"]["reference"] == "Patient/pat-a1"
        outcomes = conn.execute(
            "SELECT patient_id, outcome FROM match_audit WHERE run_id = 'run-1' "
            "ORDER BY patient_id, outcome"
        ).fetchall()
        assert outcomes == [
            ("pat-a1", "no_match"),
            ("pat-a2", "match"),
            ("pat-a3", "ambiguous"),
            ("pat-uniq", "no_match"),
        ]

    def test_rerun_same_corpus_zero_duplicate_linkages(self):
        conn = _conn()
        corpus = [A1, A2, UNIQUE]
        first = match_on_ingest(conn, corpus, "run-1")
        assert first.links_created == 1
        second = match_on_ingest(conn, corpus, "run-2")
        assert second.links_created == 0
        # on re-ingest both duplicate sides match each other (self excluded)
        assert second.matched == 2
        assert conn.execute("SELECT COUNT(*) FROM linkage").fetchone()[0] == 1

    def test_disabled_flag_is_strict_noop(self):
        conn = duckdb.connect()
        report = maybe_match_on_ingest(conn, [A1, A2], enabled=False, run_id="run-1")
        assert report.counts == {
            "indexed": 0,
            "matched": 0,
            "ambiguous": 0,
            "no_match": 0,
            "links_created": 0,
        }
        # strict no-op: nothing created on a fresh connection
        assert conn.execute("SHOW TABLES").fetchall() == []
        maybe_match_on_ingest(conn, [A1], enabled=True, run_id="run-1")
        assert conn.execute("SELECT COUNT(*) FROM match_audit").fetchone()[0] == 1

    def test_invalid_link_threshold_rejected(self):
        conn = _conn()
        with pytest.raises(ValueError):
            match_on_ingest(conn, [A1], "run-1", link_threshold={"match", "bogus"})

    def test_run_id_validated(self):
        conn = _conn()
        with pytest.raises(ValueError):
            match_on_ingest(conn, [A1], "")


# ---------------------------------------------------------------------------
# determinism (design doc §4)
# ---------------------------------------------------------------------------

# 5-patient corpus: two exact-duplicate pairs + one unique patient
P1A = _patient("det-p1a", phone="212-555-1111")
P1B = _patient("det-p1b", phone="212-555-1111")
P2A = _patient("det-p2a", first="Maria", last="Garcia", dob="1985-03-03", phone="917-555-2222")
P2B = _patient("det-p2b", first="Maria", last="Garcia", dob="1985-03-03", phone="917-555-2222")
DET_UNIQUE = _patient("det-u", first="Ken", last="Tanaka", dob="1970-09-09", phone="646-555-3333")
DET_CORPUS = {p["id"]: p for p in (P1A, P1B, P2A, P2B, DET_UNIQUE)}


def _corpus_run(conn, order):
    """Index all patients (given order), then run corpus matching: each
    patient against the full corpus, self excluded — decisions depend only
    on the patient SET, never the insertion order."""
    create_matching_tables(conn)
    create_linkage_tables(conn)
    create_audit_tables(conn)
    for pid in order:
        index_patient(conn, DET_CORPUS[pid])
    links = 0
    for pid in sorted(DET_CORPUS):
        resource = DET_CORPUS[pid]
        result = match_patient(conn, resource, exclude={pid})
        record_match_audit(conn, "det-run", pid, result)
        if result.outcome == "match":
            for cid in result.matched_ids:
                outcome = upsert_linkage(conn, result, pid, cid)
                links += 1 if outcome["action"] == "created" else 0
    return links


class TestDeterminism:
    def test_insertion_order_does_not_change_linkage_or_audit(self):
        order_one = ["det-p1a", "det-p1b", "det-p2a", "det-p2b", "det-u"]
        order_two = ["det-u", "det-p2b", "det-p1b", "det-p2a", "det-p1a"]
        conn_one, conn_two = duckdb.connect(), duckdb.connect()
        _corpus_run(conn_one, order_one)
        _corpus_run(conn_two, order_two)
        # identical Linkage JSON sets (sorted, byte-for-byte)
        links_one = [json.dumps(r, sort_keys=True) for r in load_linkage_resources(conn_one)]
        links_two = [json.dumps(r, sort_keys=True) for r in load_linkage_resources(conn_two)]
        assert sorted(links_one) == sorted(links_two)
        assert len(links_one) == 2  # one per duplicate pair, not four
        # identical audit decisions (ignoring rowid)
        audit_one = conn_one.execute(
            "SELECT run_id, patient_id, candidate_id, outcome, rule_id, "
            "confidence, evidence FROM match_audit ORDER BY patient_id, candidate_id"
        ).fetchall()
        audit_two = conn_two.execute(
            "SELECT run_id, patient_id, candidate_id, outcome, rule_id, "
            "confidence, evidence FROM match_audit ORDER BY patient_id, candidate_id"
        ).fetchall()
        assert audit_one == audit_two
        # every duplicate matched (both sides), unique patient did not
        by_patient = {r[1]: r[3] for r in audit_one}
        assert by_patient == {
            "det-p1a": "match",
            "det-p1b": "match",
            "det-p2a": "match",
            "det-p2b": "match",
            "det-u": "no_match",
        }

    def test_corpus_repass_is_idempotent(self):
        conn = duckdb.connect()
        assert _corpus_run(conn, list(DET_CORPUS)) == 2
        # second pass over the same corpus: no new links
        links = 0
        for pid in sorted(DET_CORPUS):
            result = match_patient(conn, DET_CORPUS[pid], exclude={pid})
            if result.outcome == "match":
                for cid in result.matched_ids:
                    outcome = upsert_linkage(conn, result, pid, cid)
                    links += 1 if outcome["action"] == "created" else 0
        assert links == 0
        assert conn.execute("SELECT COUNT(*) FROM linkage").fetchone()[0] == 2
