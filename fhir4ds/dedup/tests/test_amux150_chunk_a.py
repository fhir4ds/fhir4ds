"""AMUX-150 chunk A acceptance tests (1-18) — coded-type extension.

MedicationRequest / MedicationDispense / MedicationAdministration /
DiagnosticReport on the EXISTING coded dedup pipeline, plus the bounded
same-corpus MedicationIndex reference resolver.

Grounding: FEATURE_NON_CODED_DEDUP.md §2, §6 (tests 1-18).
"""

from __future__ import annotations

import json
import random
from pathlib import Path

import duckdb

from fhir4ds.dedup import dedup_pass, run_dedup
from fhir4ds.dedup.audit import load_dedup_audit as _load_audit

_RXNORM = "http://www.nlm.nih.gov/research/umls/rxnorm"
_LOINC = "http://loinc.org"


def _medreq(rid, authored, *, code="104967", system=_RXNORM, text=None,
            subject="Patient/p1", contained=None, reference=None,
            display=None):
    resource = {"resourceType": "MedicationRequest", "id": rid,
                "status": "active",
                "subject": {"reference": subject},
                "intent": "order"}
    if authored is not None:
        resource["authoredOn"] = authored
    if reference is not None:
        resource["medicationReference"] = {"reference": reference}
    elif display is not None:
        resource["medicationReference"] = {"display": display}
    elif code is not None or text is not None:
        concept = {}
        if code is not None:
            concept["coding"] = [{"system": system, "code": code}]
        if text is not None:
            concept["text"] = text
        resource["medicationCodeableConcept"] = concept
    if contained is not None:
        resource["contained"] = contained
    return resource


def _meddisp(rid, handed, *, code="104967", system=_RXNORM,
             subject="Patient/p1"):
    return {"resourceType": "MedicationDispense", "id": rid,
            "status": "completed",
            "subject": {"reference": subject},
            "whenHandedOver": handed,
            "medicationCodeableConcept": {
                "coding": [{"system": system, "code": code}]}}


def _medadmin(rid, *, datetime_eff=None, period=None, code="104967",
              system=_RXNORM, subject="Patient/p1"):
    resource = {"resourceType": "MedicationAdministration", "id": rid,
                "status": "completed",
                "subject": {"reference": subject},
                "medicationCodeableConcept": {
                    "coding": [{"system": system, "code": code}]}}
    if datetime_eff is not None:
        resource["effectiveDateTime"] = datetime_eff
    if period is not None:
        resource["effectivePeriod"] = period
    return resource


def _diarep(rid, effective, *, code="2160-0", system=_LOINC,
            subject="Patient/p1"):
    return {"resourceType": "DiagnosticReport", "id": rid,
            "status": "final",
            "subject": {"reference": subject},
            "code": {"coding": [{"system": system, "code": code}]},
            "effectiveDateTime": effective}


def _medication(mid, *, code="104967", system=_RXNORM):
    return {"resourceType": "Medication", "id": mid,
            "code": {"coding": [{"system": system, "code": code}]}}


def _clusters(result):
    return [sorted(r.rid for r in cluster) for cluster in result.clusters]


def _emitted(result):
    return sorted(r.rid for r in result.emitted)


class TestChunkACodedTypes:
    def test_01_medrequest_twins_merge(self):
        result = dedup_pass([
            _medreq("a", "2024-03-05T10:00:00Z"),
            _medreq("b", "2024-03-05T11:30:00Z"),
        ])
        assert _clusters(result) == [["a", "b"]]
        assert _emitted(result) == []

    def test_02_medrequest_different_days_singletons(self):
        result = dedup_pass([
            _medreq("a", "2024-03-05T10:00:00Z"),
            _medreq("b", "2024-03-06T10:00:00Z"),
        ])
        assert _clusters(result) == []
        assert _emitted(result) == ["a", "b"]

    def test_03_medrequest_no_date_singletons(self):
        result = dedup_pass([
            _medreq("a", None),
            _medreq("b", None),
        ])
        assert _clusters(result) == []
        assert _emitted(result) == ["a", "b"]

    def test_04_medrequest_vs_meddispense_never_cross(self):
        result = dedup_pass([
            _medreq("r", "2024-03-05T10:00:00Z"),
            _meddisp("d", "2024-03-05T10:00:00Z"),
        ])
        assert _clusters(result) == []
        assert _emitted(result) == ["d", "r"]

    def test_05_meddispense_twins_merge(self):
        result = dedup_pass([
            _meddisp("d1", "2024-03-05T09:00:00Z"),
            _meddisp("d2", "2024-03-05T09:45:00Z"),
        ])
        assert _clusters(result) == [["d1", "d2"]]

    def test_06_medadmin_variants(self):
        # effectiveDateTime twins
        result = dedup_pass([
            _medadmin("m1", datetime_eff="2024-03-05T08:00:00Z"),
            _medadmin("m2", datetime_eff="2024-03-05T08:20:00Z"),
        ])
        assert _clusters(result) == [["m1", "m2"]]
        # effectivePeriod twins
        result = dedup_pass([
            _medadmin("m3", period={"start": "2024-03-05T08:00:00Z",
                                    "end": "2024-03-05T09:00:00Z"}),
            _medadmin("m4", period={"start": "2024-03-05T08:30:00Z",
                                    "end": "2024-03-05T09:30:00Z"}),
        ])
        assert _clusters(result) == [["m3", "m4"]]
        # mixed datetime vs period, same local day
        result = dedup_pass([
            _medadmin("m5", datetime_eff="2024-03-05T08:00:00Z"),
            _medadmin("m6", period={"start": "2024-03-05T10:00:00Z",
                                    "end": "2024-03-05T11:00:00Z"}),
        ])
        assert _clusters(result) == [["m5", "m6"]]

    def test_07_contained_reference_resolution_hybrid_tier(self):
        result = dedup_pass([
            _medreq("inline", "2024-03-05T10:00:00Z"),
            _medreq("ref", "2024-03-05T11:00:00Z", code=None,
                    reference="#med1",
                    contained=[_medication("med1")]),
        ])
        assert _clusters(result) == [["inline", "ref"]]
        edges = result.cluster_edges[0]
        hybrid = [e for e in edges if e.get("tier") == "hybrid"]
        assert hybrid, f"expected a hybrid edge, got {edges}"
        assert hybrid[0]["subtype"] == "reference_resolved"

    def test_08_corpus_reference_resolution(self):
        result = dedup_pass([
            _medication("abc"),
            _medreq("inline", "2024-03-05T10:00:00Z"),
            _medreq("ref", "2024-03-05T12:00:00Z", code=None,
                    reference="Medication/abc"),
        ])
        assert _clusters(result) == [["inline", "ref"]]

    def test_09_dangling_reference_singleton_and_queue(self):
        result = dedup_pass([
            _medreq("dangling", "2024-03-05T10:00:00Z", code=None,
                    reference="Medication/zzz"),
        ])
        assert _clusters(result) == []
        assert _emitted(result) == ["dangling"]
        entries = [e for e in result.curation_records
                   if e["kind"] == "unresolved_medication_reference"]
        assert len(entries) == 1
        assert entries[0]["rid"] == "dangling"
        assert entries[0]["reference"] == "Medication/zzz"

    def test_10_resolved_medication_without_codings(self):
        bare = {"resourceType": "Medication", "id": "bare", "code": {}}
        result = dedup_pass([
            bare,
            _medreq("ref", "2024-03-05T10:00:00Z", code=None,
                    reference="#bare",
                    contained=[bare]),
        ])
        assert _clusters(result) == []
        entries = [e for e in result.curation_records
                   if e["kind"] == "unresolved_medication_reference"]
        assert len(entries) == 1

    def test_11_versioned_and_absolute_reference_spellings(self):
        result = dedup_pass([
            _medication("abc"),
            _medreq("inline", "2024-03-05T10:00:00Z"),
            _medreq("v", "2024-03-05T11:00:00Z", code=None,
                    reference="Medication/abc/_history/2"),
            _medreq("abs", "2024-03-05T12:00:00Z", code=None,
                    reference="https://example.org/fhir/Medication/abc"),
        ])
        assert _clusters(result) == [["abs", "inline", "v"]]

    def test_12_diagnostic_report(self):
        result = dedup_pass([
            _diarep("r1", "2024-03-05T10:00:00Z"),
            _diarep("r2", "2024-03-05T10:30:00Z"),
        ])
        assert _clusters(result) == [["r1", "r2"]]
        result = dedup_pass([
            _diarep("r1", "2024-03-05T10:00:00Z"),
            _diarep("r2", "2024-03-05T10:30:00Z", code="2160-1"),
        ])
        assert _clusters(result) == []
        assert _emitted(result) == ["r1", "r2"]

    def test_13_tier2_text_fallback_regression(self):
        result = dedup_pass([
            _medreq("t1", "2024-03-05T10:00:00Z", code=None,
                    text="Lisinopril 10 MG"),
            _medreq("t2", "2024-03-05T11:00:00Z", code=None,
                    text="lisinopril 10 mg"),
        ])
        assert _clusters(result) == [["t1", "t2"]]
        edges = result.cluster_edges[0]
        assert any(e.get("tier") == "text" for e in edges)

    def test_14_determinism_shuffle_invariance(self):
        corpus = [
            _medication("abc"),
            _medreq("inline", "2024-03-05T10:00:00Z"),
            _medreq("ref", "2024-03-05T11:00:00Z", code=None,
                    reference="Medication/abc"),
            _medreq("dangling", "2024-03-06T10:00:00Z", code=None,
                    reference="Medication/zzz"),
            _meddisp("d1", "2024-03-05T09:00:00Z"),
            _meddisp("d2", "2024-03-05T09:45:00Z"),
            _medadmin("m1", datetime_eff="2024-03-05T08:00:00Z"),
            _medadmin("m2", period={"start": "2024-03-05T10:00:00Z",
                                    "end": "2024-03-05T11:00:00Z"}),
            _diarep("r1", "2024-03-07T10:00:00Z"),
            _diarep("r2", "2024-03-07T10:30:00Z"),
        ]
        out1, out2 = Path("/tmp/opencode/amux150_a1"), \
            Path("/tmp/opencode/amux150_a2")
        conn1, conn2 = duckdb.connect(), duckdb.connect()
        run1 = run_dedup(list(corpus), "run-a", conn=conn1,
                         output_dir=str(out1))
        shuffled = list(corpus)
        random.Random(42).shuffle(shuffled)
        run2 = run_dedup(shuffled, "run-a", conn=conn2,
                         output_dir=str(out2))
        assert json.dumps(run1.survivors, sort_keys=True) == \
            json.dumps(run2.survivors, sort_keys=True)
        assert json.dumps(run1.linkage_resources, sort_keys=True) == \
            json.dumps(run2.linkage_resources, sort_keys=True)
        assert json.dumps(_load_audit(conn1, "run-a"), sort_keys=True) == \
            json.dumps(_load_audit(conn2, "run-a"), sort_keys=True)
        assert (out1 / "dedup_curation_queue.jsonl").read_bytes() == \
            (out2 / "dedup_curation_queue.jsonl").read_bytes()
        conn1.close()
        conn2.close()

    def test_15_stats_surface(self):
        result = dedup_pass([
            _medication("abc"),
            _medreq("inline", "2024-03-05T10:00:00Z"),
            _medreq("ref", "2024-03-05T11:00:00Z", code=None,
                    reference="Medication/abc"),
            _medreq("dangling", "2024-03-06T10:00:00Z", code=None,
                    reference="Medication/zzz"),
        ])
        assert result.stats["reference_resolved_records"] == 1
        assert result.stats["unresolved_medication_references"] == 1
        subtypes = {e.get("subtype")
                    for edges in result.cluster_edges for e in edges}
        assert "reference_resolved" in subtypes

    def test_16_backcompat_existing_types(self):
        # Observation LAB twins, Condition OTHER same-day twins,
        # Immunization no-date singletons, Procedure same-day twins.
        obs = lambda rid, eff: {
            "resourceType": "Observation", "id": rid, "status": "final",
            "subject": {"reference": "Patient/p1"},
            "code": {"coding": [{"system": _LOINC, "code": "2160-0"}]},
            "category": [{"coding": [{
                "system": "http://terminology.hl7.org/CodeSystem/"
                          "observation-category",
                "code": "laboratory"}]}],
            "effectiveDateTime": eff,
            "valueQuantity": {"value": 140, "unit": "mg/dL",
                              "code": "mg/dL"}}
        cond = lambda rid, onset: {
            "resourceType": "Condition", "id": rid,
            "subject": {"reference": "Patient/p1"},
            "code": {"coding": [{"system": "http://snomed.info/sct",
                                 "code": "195967001"}]},
            "onsetDateTime": onset}
        imm = lambda rid: {
            "resourceType": "Immunization", "id": rid, "status": "completed",
            "subject": {"reference": "Patient/p1"},
            "vaccineCode": {"coding": [{"system":
                                        "http://hl7.org/fhir/sid/cvx",
                                        "code": "140"}]}}
        proc = lambda rid: {
            "resourceType": "Procedure", "id": rid, "status": "completed",
            "subject": {"reference": "Patient/p1"},
            "code": {"coding": [{"system": "http://snomed.info/sct",
                                 "code": "715252007"}]},
            "performedDateTime": "2024-03-05T10:00:00Z"}
        result = dedup_pass([
            obs("o1", "2024-03-05T10:00:00Z"),
            obs("o2", "2024-03-05T10:10:00Z"),
            cond("c1", "2024-03-05"),
            cond("c2", "2024-03-05"),
            imm("i1"), imm("i2"),
            proc("pr1"), proc("pr2"),
        ])
        assert _clusters(result) == [["c1", "c2"], ["o1", "o2"],
                                     ["pr1", "pr2"]]
        assert _emitted(result) == ["i1", "i2"]

    def test_17_display_only_reference(self):
        result = dedup_pass([
            _medreq("disp", "2024-03-05T10:00:00Z", code=None,
                    display="Aspirin"),
        ])
        assert _clusters(result) == []
        assert _emitted(result) == ["disp"]
        entries = [e for e in result.curation_records
                   if e["kind"] == "unresolved_medication_reference"]
        assert len(entries) == 1
        assert entries[0]["reference"] is None
        assert entries[0]["display"] == "Aspirin"

    def test_18_no_medications_never_builds_index(self):
        from fhir4ds.dedup.medication import LazyMedicationIndex
        corpus = [
            _diarep("r1", "2024-03-05T10:00:00Z"),
            _diarep("r2", "2024-03-05T10:30:00Z"),
        ]
        lazy = LazyMedicationIndex(corpus)
        assert lazy.built is False

        class Spy:
            calls = 0

            def resolve(self, resource):
                type(self).calls += 1
                return None

        dedup_pass(corpus, medication_resolver=Spy())
        assert Spy.calls == 0
