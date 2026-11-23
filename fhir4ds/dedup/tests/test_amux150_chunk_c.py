"""AMUX-150 chunk C acceptance tests (35-46) — temporal strategy: Encounter.

Hard anchor (master patient), period-overlap scoring, corroboration,
hard negatives, and the unchanged survivorship/Linkage/audit back end.

Grounding: FEATURE_NON_CODED_DEDUP.md §4, §6 (tests 35-46).
"""

from __future__ import annotations

import json
import random
from pathlib import Path

import duckdb

from fhir4ds.dedup.encounter import encounter_pass, run_encounter_dedup
from fhir4ds.dedup.audit import load_dedup_audit
from fhir4ds.dedup.linkage import load_dedup_linkage_resources
from fhir4ds.dedup.temporal import NormalizedDate, Signature, \
    period_overlap

_ACT = "http://terminology.hl7.org/CodeSystem/v3-ActCode"
_ROLE = "http://terminology.hl7.org/CodeSystem/v3-RoleCode"
_SNX = "http://snomed.info/sct"


def _enc(rid, start, end=None, *, subject="Patient/p1", klass="AMB",
         participants=(), provider=None, locations=(), stype=None,
         reasons=(), no_period=False):
    resource = {"resourceType": "Encounter", "id": rid,
                "status": "finished",
                "class": {"system": _ACT, "code": klass}}
    if subject is not None:
        resource["subject"] = {"reference": subject}
    if not no_period:
        resource["period"] = {"start": start}
        if end is not None:
            resource["period"]["end"] = end
    if participants:
        resource["participant"] = [
            {"individual": {"reference": f"Practitioner/{p}"}}
            for p in participants]
    if provider:
        resource["serviceProvider"] = {"reference":
                                       f"Organization/{provider}"}
    if locations:
        resource["location"] = [
            {"location": {"reference": f"Location/{loc}"}}
            for loc in locations]
    if stype:
        resource["serviceType"] = {"coding": [{"system": _SNX,
                                               "code": stype}]}
    if reasons:
        resource["reasonCode"] = [
            {"coding": [{"system": _SNX, "code": r}]} for r in reasons]
    return resource


def _clusters(result):
    return [sorted(r.rid for r in cluster) for cluster in result.clusters]


def _emitted(result):
    return sorted(r.rid for r in result.emitted)


class TestPeriodOverlapPrimitive:
    def _nd(self, start, end, signature=Signature.DT_Z):
        return NormalizedDate(signature=signature, local_date="2024-03-05",
                              dt_utc=None, start_utc=start, end_utc=end)

    def test_primitive_semantics(self):
        a = self._nd("2024-03-05T10:00:00.000Z", "2024-03-05T11:00:00.000Z")
        b = self._nd("2024-03-05T10:30:00.000Z", "2024-03-05T11:30:00.000Z")
        c = self._nd("2024-03-05T12:00:00.000Z", "2024-03-05T13:00:00.000Z")
        d = self._nd("2024-03-05T11:00:00.000Z", "2024-03-05T14:00:00.000Z")
        assert period_overlap(a, b) == "overlap"
        assert period_overlap(a, c) == "disjoint"
        assert period_overlap(a, c, max_gap="1h") == "adjacent"
        assert period_overlap(a, d, max_gap="0s") == "overlap"  # touching
        assert period_overlap(self._nd(None, None), a) == "unknown"


class TestEncounterStrategy:
    def test_35_identical_periods_merge(self):
        result = encounter_pass([
            _enc("e1", "2024-03-05T10:00:00Z", "2024-03-05T11:00:00Z"),
            _enc("e2", "2024-03-05T10:00:00Z", "2024-03-05T11:00:00Z"),
        ])
        assert _clusters(result) == [["e1", "e2"]]
        assert result.cluster_edges[0][0]["score"] >= 60

    def test_36_containment_plus_provider_merges(self):
        result = encounter_pass([
            _enc("outer", "2024-03-05T08:00:00Z", "2024-03-05T12:00:00Z",
                 provider="org1"),
            _enc("inner", "2024-03-05T09:00:00Z", "2024-03-05T11:30:00Z",
                 provider="org1"),
        ])
        assert _clusters(result) == [["inner", "outer"]]

    def test_37_partial_overlap_no_core_no_merge_near_miss(self):
        # 30% overlap (1h of a 2h shorter span? engineered below),
        # all four 10-point corroborators shared -> score 70, no core.
        a = _enc("a", "2024-03-05T08:00:00Z", "2024-03-05T12:00:00Z",
                 klass="AMB", participants=["dr1"], provider="org1",
                 locations=["loc1"])
        # overlap 12:00-12:30 vs a's end -> a: 8-12, b: 11:30-14:30
        b = _enc("b", "2024-03-05T11:30:00Z", "2024-03-05T14:30:00Z",
                 klass="AMB", participants=["dr1"], provider="org1",
                 locations=["loc1"])
        result = encounter_pass([a, b])
        assert _clusters(result) == []
        assert _emitted(result) == ["a", "b"]
        near = [e for e in result.curation_records
                if e["kind"] == "encounter_near_miss"]
        assert len(near) == 1
        assert near[0]["score"] >= 60  # corroborators carry it past 60

    def test_38_adjacent_handoff_merges(self):
        result = encounter_pass([
            _enc("ed", "2024-03-05T10:00:00Z", "2024-03-05T11:50:00Z",
                 klass="EMER", participants=["dr1"], provider="org1",
                 locations=["loc1"]),
            _enc("admit", "2024-03-05T12:00:00Z", "2024-03-05T18:00:00Z",
                 klass="EMER", participants=["dr1"], provider="org1",
                 locations=["loc1"]),
        ])
        assert _clusters(result) == [["admit", "ed"]]

    def test_39_hard_negative_disjoint_emergency(self):
        result = encounter_pass([
            _enc("e1", "2024-03-05T08:00:00Z", "2024-03-05T09:00:00Z",
                 klass="EMER", participants=["dr1"], provider="org1",
                 locations=["loc1"]),
            _enc("e2", "2024-03-05T14:00:00Z", "2024-03-05T15:00:00Z",
                 klass="EMER", participants=["dr1"], provider="org1",
                 locations=["loc1"]),
        ])
        assert _clusters(result) == []

    def test_39b_hard_negative_veto_mechanism_fires(self):
        # Code-review pin (AMUX-150): the EMER-disjoint->=2h veto must be
        # REACHABLE — the veto runs BEFORE the adjacency candidate gate
        # (scoring it after the gate would be dead logic, since a scored
        # disjoint pair always has gap <= 15 min).
        from fhir4ds.dedup.encounter import (
            EncounterFeatures, _encounter_nd, _score_pair)
        a = _enc("a", "2024-03-05T08:00:00Z", "2024-03-05T09:00:00Z",
                 klass="EMER", participants=["dr1"])
        b = _enc("b", "2024-03-05T14:00:00Z", "2024-03-05T15:00:00Z",
                 klass="EMER", participants=["dr1"])
        scored = _score_pair(
            _encounter_nd(a), _encounter_nd(b),
            EncounterFeatures.from_resource(a),
            EncounterFeatures.from_resource(b), "UTC")
        assert scored is not None and scored["hard_negative"] is True
        # A NON-emergency disjoint pair is simply not a candidate (None),
        # not a veto.
        b_amb = _enc("b", "2024-03-05T14:00:00Z", "2024-03-05T15:00:00Z",
                     klass="AMB", participants=["dr1"])
        assert _score_pair(
            _encounter_nd(a), _encounter_nd(b_amb),
            EncounterFeatures.from_resource(a),
            EncounterFeatures.from_resource(b_amb), "UTC") is None

    def test_40_cross_patient_never_merges(self):
        result = encounter_pass([
            _enc("e1", "2024-03-05T10:00:00Z", "2024-03-05T11:00:00Z",
                 subject="Patient/p1", klass="EMER", participants=["dr1"],
                 provider="org1", locations=["loc1"]),
            _enc("e2", "2024-03-05T10:00:00Z", "2024-03-05T11:00:00Z",
                 subject="Patient/p2", klass="EMER", participants=["dr1"],
                 provider="org1", locations=["loc1"]),
        ])
        assert _clusters(result) == []
        assert _emitted(result) == ["e1", "e2"]

    def test_41_group_subject_singleton(self):
        result = encounter_pass([
            _enc("e1", "2024-03-05T10:00:00Z", "2024-03-05T11:00:00Z",
                 subject="Group/g7"),
            _enc("e2", "2024-03-05T10:00:00Z", "2024-03-05T11:00:00Z",
                 subject="Group/g7"),
        ])
        assert _clusters(result) == []
        assert _emitted(result) == ["e1", "e2"]

    def test_42_no_period_singleton_and_queue(self):
        result = encounter_pass([
            _enc("e1", None, no_period=True),
            _enc("e2", None, no_period=True),
        ])
        assert _clusters(result) == []
        assert _emitted(result) == ["e1", "e2"]
        unmatched = [e for e in result.curation_records
                     if e["kind"] == "unmatched"]
        assert {e["rid"] for e in unmatched} == {"e1", "e2"}
        assert all(e["resource_type"] == "Encounter" for e in unmatched)

    def test_43_open_ended_contains_closed(self):
        result = encounter_pass([
            _enc("ongoing", "2024-03-05T08:00:00Z"),
            _enc("closed", "2024-03-05T09:00:00Z", "2024-03-05T10:00:00Z"),
        ])
        assert _clusters(result) == [["closed", "ongoing"]]

    def test_44_survivorship_linkage_window_rule(self):
        rich = _enc("rich", "2024-03-05T10:00:00Z", "2024-03-05T11:00:00Z",
                    klass="AMB", participants=["dr1"], provider="org1",
                    locations=["loc1"], stype="54016007",
                    reasons=["363318001"])
        lean = _enc("lean", "2024-03-05T10:00:00Z", "2024-03-05T11:00:00Z",
                    klass=None)
        run = run_encounter_dedup([lean, rich], "run-c")
        assert len(run.survivors) == 1
        survivor = run.survivors[0]
        assert survivor["id"].startswith("dedup-")
        urls = [e["url"] for e in survivor["extension"]
                if isinstance(e, dict)]
        assert any(u.endswith("/dedup") for u in urls)
        linkage = run.linkage_resources[0]
        window = [e for e in linkage["extension"][0]["extension"]
                  if e["url"] == "windowRule"][0]["valueString"]
        assert window == "encounter:overlap"

    def test_45_determinism_shuffle_invariance(self):
        corpus = [
            _enc("e1", "2024-03-05T10:00:00Z", "2024-03-05T11:00:00Z"),
            _enc("e2", "2024-03-05T10:00:00Z", "2024-03-05T11:00:00Z"),
            _enc("e3", "2024-03-05T10:05:00Z", "2024-03-05T11:05:00Z",
                 subject="Patient/p1"),
            _enc("e4", "2024-03-05T08:00:00Z", "2024-03-05T09:00:00Z",
                 subject="Patient/p2"),
            _enc("e5", "2024-03-05T08:00:00Z", "2024-03-05T09:00:00Z",
                 subject="Patient/p2"),
        ]
        conn1, conn2 = duckdb.connect(), duckdb.connect()
        run1 = run_encounter_dedup(list(corpus), "run-d", conn=conn1)
        shuffled = list(corpus)
        random.Random(7).shuffle(shuffled)
        run2 = run_encounter_dedup(shuffled, "run-d", conn=conn2)
        assert json.dumps(run1.survivors, sort_keys=True) == \
            json.dumps(run2.survivors, sort_keys=True)
        assert json.dumps(run1.linkage_resources, sort_keys=True) == \
            json.dumps(run2.linkage_resources, sort_keys=True)
        assert json.dumps(load_dedup_audit(conn1, "run-d"),
                          sort_keys=True) == \
            json.dumps(load_dedup_audit(conn2, "run-d"), sort_keys=True)
        conn1.close()
        conn2.close()

    def test_46_related_person_and_encounter_coexistence(self):
        from fhir4ds.matching.related_person import match_related_persons
        conn = duckdb.connect()
        rps = [
            {"resourceType": "RelatedPerson", "id": "r1",
             "patient": {"reference": "Patient/p1"},
             "relationship": [{"coding": [{"system": _ROLE,
                                           "code": "WIFE"}]}],
             "period": {"start": "2020-01-01", "end": "2024-01-01"}},
            {"resourceType": "RelatedPerson", "id": "r2",
             "patient": {"reference": "Patient/p1"},
             "relationship": [{"coding": [{"system": _ROLE,
                                           "code": "WIFE"}]}],
             "period": {"start": "2021-01-01", "end": "2023-01-01"}},
        ]
        match_related_persons(conn, "run-x", rps)
        run = run_encounter_dedup(
            [_enc("e1", "2024-03-05T10:00:00Z", "2024-03-05T11:00:00Z"),
             _enc("e2", "2024-03-05T10:00:00Z", "2024-03-05T11:00:00Z")],
            "run-x", conn=conn)
        # pairwise matching Linkage table
        match_keys = conn.execute(
            "SELECT linkage_id FROM linkage").fetchall()
        assert match_keys == [("RelatedPerson/r1|RelatedPerson/r2",)]
        # N-way dedup Linkage table, disjoint namespace
        dedup_rows = conn.execute(
            "SELECT dedup_id FROM dedup_linkage").fetchall()
        assert len(dedup_rows) == 1
        assert run.stats["clusters"] == 1
        conn.close()
