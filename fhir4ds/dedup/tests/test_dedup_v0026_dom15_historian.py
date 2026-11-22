"""D15 HISTORIAN (v0.0.26) — audit-trail integrity + read-surface guards.

Red-first regressions for:
- QA-D15H-001: ``records_by_rid`` keyed on BARE rid across resource types
  let a Condition sharing an Observation's id (legal FHIR — ids are only
  unique per type) SHADOW the near-miss curation entry's record metadata
  (resource_type / patient_ref / codes evidence came from the wrong
  resource entirely).
- QA-D15H-002: ``load_dedup_audit`` / ``load_dedup_linkage_resources``
  raised a raw DuckDB CatalogException on a zero-decision run (the tables
  are created lazily by the first WRITE; the loaders never ensured
  existence — ``delete_linkage`` already carries the create-first
  precedent).
"""

from __future__ import annotations

import json

import duckdb

from fhir4ds.dedup.audit import load_dedup_audit
from fhir4ds.dedup.linkage import load_dedup_linkage_resources
from fhir4ds.dedup.pipeline import dedup_pass
from fhir4ds.dedup.runner import run_dedup


def _coded_obs(oid: str) -> dict:
    return {
        "resourceType": "Observation", "id": oid, "status": "final",
        "code": {"coding": [{"system": "http://loinc.org",
                             "code": "8480-6"}],
                 "text": "Blood pressure"},
        "subject": {"reference": "Patient/p1"},
        "effectiveDateTime": "2024-06-01T10:00:00Z",
        "valueQuantity": {"value": 120, "unit": "mmHg"},
    }


def _uncoded_obs(oid: str) -> dict:
    return {
        "resourceType": "Observation", "id": oid, "status": "final",
        "code": {"text": "Blood pressure"},
        "subject": {"reference": "Patient/p1"},
        "effectiveDateTime": "2024-06-01T12:00:00Z",
        "valueQuantity": {"value": 120, "unit": "mmHg"},
    }


class TestNearMissAuditTrailTypeAware:
    def test_shadow_rid_first_keeps_near_miss_metadata_correct(self):
        """The shadow (Condition sharing the Observation's id) sorts FIRST
        in the edge, so the pre-fix entry reported resource_type
        Condition / Patient/p9 / SNOMED codes for an Observation pair."""
        shadow = {
            "resourceType": "Condition", "id": "a-shared",
            "subject": {"reference": "Patient/p9"},
            "code": {"coding": [{"system": "http://snomed.info/sct",
                                 "code": "123"}]},
        }
        result = dedup_pass([_coded_obs("m-coded"),
                             _uncoded_obs("a-shared"), shadow],
                            code_fallback="on")
        entries = [e for e in result.curation_records
                   if e["kind"] == "near_miss"]
        assert entries, "expected a temporal_rejected near-miss"
        for entry in entries:
            assert entry["resource_type"] == "Observation"
            assert entry["patient_ref"] == "Patient/p1"
            # codes evidence must describe the OBSERVATION pair members:
            # a-shared is uncoded (empty list), never the Condition's
            # SNOMED coding.
            assert entry["codes"]["a-shared"] == []
            assert entry["codes"]["m-coded"] == ["http://loinc.org|8480-6"]

    def test_shadow_rid_second_keeps_codes_evidence_correct(self):
        """Pre-fix, the shadowing corrupted even the codes payload when
        the shadow rid sorted second (metadata stayed right, evidence
        wrong)."""
        shadow = {
            "resourceType": "Condition", "id": "shared-1",
            "subject": {"reference": "Patient/p9"},
            "code": {"coding": [{"system": "http://snomed.info/sct",
                                 "code": "123"}]},
        }
        result = dedup_pass([_coded_obs("coded-1"),
                             _uncoded_obs("shared-1"), shadow],
                            code_fallback="on")
        entries = [e for e in result.curation_records
                   if e["kind"] == "near_miss"]
        assert entries
        for entry in entries:
            assert entry["codes"]["shared-1"] == []
            assert entry["codes"]["coded-1"] == ["http://loinc.org|8480-6"]
            assert entry["resource_type"] == "Observation"


class TestZeroDecisionReadSurface:
    def test_load_dedup_audit_empty_run_returns_empty(self):
        conn = duckdb.connect()
        run_dedup([_coded_obs("solo-1")], "run-empty", conn=conn)
        assert load_dedup_audit(conn, "run-empty") == []

    def test_load_dedup_linkage_resources_empty_run_returns_empty(self):
        conn = duckdb.connect()
        run_dedup([_coded_obs("solo-1")], "run-empty", conn=conn)
        assert load_dedup_linkage_resources(conn) == []
