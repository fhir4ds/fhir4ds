"""v0.0.25 D15 (Domain 15, SKEPTIC) regression coverage.

Pins the fixes from the 2026-11-17 QA evolution pass plus the LOW
follow-ups logged from the AMUX-142 review:

- L2: patient-ref regex ANCHORING (trailing path text never attributes).
- L3: non-finite quantity values get a per-repr malformed sentinel —
  never the ``DAR:null`` partition (an inf-valued row must not merge
  with a value-absent row).
- L4: runner audit ``rule_json`` carries the survivorship ranking tuple
  (``[signature, richness, rid]``, timestamp-free), matching the audit
  docstring contract.
- L5: 1:1 absorb guard with N (>= 3) DATE_ONLY singles and ONE unique
  timestamped cluster absorbs every single.
- L6: mixed-precision Periods (date-only start + timestamped end, or the
  reverse) participate in Stage-2 windowing via their known bound instant.
- cross-tz-midnight Z/offset pairs: documented authored-local partition
  recall miss — pinned as NEVER a false merge.
"""

from __future__ import annotations

import math

import duckdb
import pytest

from fhir4ds.dedup.audit import load_dedup_audit
from fhir4ds.dedup.pipeline import _patient_ref, dedup_pass
from fhir4ds.dedup.runner import run_dedup
from fhir4ds.dedup.values import normalize_value

_LOINC = "http://loinc.org"
_OBS_CATEGORY = "http://terminology.hl7.org/CodeSystem/observation-category"


def _obs(rid, effective=None, *, code="2160-0", value=140, unit="mg/dL",
         cat="laboratory", subject="Patient/p1", period=None):
    resource = {"resourceType": "Observation", "id": rid, "status": "final",
                "subject": {"reference": subject},
                "code": {"coding": [{"system": _LOINC, "code": code}]},
                "category": [{"coding": [{"system": _OBS_CATEGORY,
                                          "code": cat}]}]}
    if effective is not None:
        resource["effectiveDateTime"] = effective
    if period is not None:
        resource["effectivePeriod"] = period
    if value is not None:
        resource["valueQuantity"] = {"value": value, "unit": unit,
                                     "code": unit}
    return resource


def _cluster_rids(result):
    return [sorted(r.rid for r in cluster) for cluster in result.clusters]


def _all_rids(result):
    return sorted([r.rid for r in result.emitted]
                  + [r.rid for c in result.clusters for r in c])


# ---------------------------------------------------------------------------
# L2 — patient-ref anchoring
# ---------------------------------------------------------------------------


class TestPatientRefAnchoringDom15:
    def test_relative_versioned_absolute_still_attribute(self):
        assert _patient_ref(
            {"subject": {"reference": "Patient/abc"}}) == "Patient/abc"
        assert _patient_ref(
            {"subject": {"reference": "Patient/abc/_history/2"}}) == "Patient/abc"
        assert _patient_ref({"subject": {"reference":
                                         "https://fhir.example.org/Patient/abc"}}
                            ) == "Patient/abc"

    def test_non_patient_types_never_attribute(self):
        assert _patient_ref({"subject": {"reference": "Group/g7"}}) is None
        assert _patient_ref({"subject": {"reference": "Location/abc"}}) is None

    def test_trailing_path_text_never_attributes_dom15_skeptic(self):
        """L2 fix: ``.../Patient/abc/other`` previously attributed
        ``Patient/abc`` via unanchored re.search — a phantom patient."""
        ref = {"subject": {"reference":
                           "https://example.org/fhir/Patient/abc/other"}}
        assert _patient_ref(ref) is None

    def test_embedded_mid_string_never_attributes_dom15_skeptic(self):
        ref = {"subject": {"reference":
                           "https://example.org/fhir/NotPatientabc/xyz"}}
        assert _patient_ref(ref) is None

    def test_patient_field_and_subject_precedence(self):
        assert _patient_ref(
            {"patient": {"reference": "Patient/xyz"}}) == "Patient/xyz"
        assert _patient_ref(
            {"subject": {"reference": "Patient/s"},
             "patient": {"reference": "Patient/q"}}) == "Patient/s"


# ---------------------------------------------------------------------------
# L3 — malformed value sentinel
# ---------------------------------------------------------------------------


class TestMalformedValueSentinelDom15:
    def _nan_obs(self, value):
        return {"resourceType": "Observation",
                "code": {"coding": [{"system": _LOINC, "code": "2160-0"}]},
                "valueQuantity": {"value": value, "unit": "mg", "code": "mg"}}

    def test_nonfinite_values_never_use_dar_null_dom15_skeptic(self):
        absent = normalize_value({"resourceType": "Observation"})
        assert absent == "DAR:null"
        for bad in (float("nan"), float("inf"), float("-inf")):
            key = normalize_value(self._nan_obs(bad))
            assert key.startswith("DAR:malformed:"), f"{bad!r} -> {key}"
            assert key != "DAR:null"

    def test_nonfinite_values_pairwise_distinct(self):
        keys = {normalize_value(self._nan_obs(b))
                for b in (float("nan"), float("inf"), float("-inf"))}
        assert len(keys) == 3

    def test_inf_row_never_merges_with_absent_row_dom15_skeptic(self):
        """The pre-fix conflation clustered an inf-valued observation with
        a value-absent observation through the shared DAR:null key."""
        base = {"resourceType": "Observation", "status": "final",
                "code": {"coding": [{"system": _LOINC, "code": "2160-0"}]},
                "category": [{"coding": [{"system": _OBS_CATEGORY,
                                          "code": "laboratory"}]}],
                "subject": {"reference": "Patient/p1"},
                "effectiveDateTime": "2024-03-05T10:00:00Z"}
        inf_row = dict(base, id="inf1",
                       valueQuantity={"value": float("inf"),
                                      "unit": "mg", "code": "mg"})
        absent_row = dict(base, id="abs1")
        result = dedup_pass([inf_row, absent_row])
        assert _cluster_rids(result) == []
        assert _all_rids(result) == ["abs1", "inf1"]


# ---------------------------------------------------------------------------
# L6 — mixed-precision Period windowing
# ---------------------------------------------------------------------------


class TestMixedPrecisionPeriodDom15:
    def test_date_only_start_timestamped_end_windows_on_end(self):
        period_row = _obs("mix1", period={"start": "2024-03-05",
                                          "end": "2024-03-05T10:00:00Z"})
        point = _obs("mix2", "2024-03-05T10:00:00Z")
        result = dedup_pass([period_row, point])
        assert _all_rids(result) == ["mix1", "mix2"]  # never silently lost
        assert _cluster_rids(result) == [["mix1", "mix2"]]

    def test_timestamped_start_date_only_end_windows_on_start(self):
        period_row = _obs("mix3", period={"start": "2024-03-05T10:00:00Z",
                                          "end": "2024-03-05"})
        point = _obs("mix4", "2024-03-05T10:00:00Z")
        result = dedup_pass([period_row, point])
        assert _cluster_rids(result) == [["mix3", "mix4"]]

    def test_period_row_outside_window_stays_separate(self):
        period_row = _obs("mix5", period={"start": "2024-03-05",
                                          "end": "2024-03-05T12:00:00Z"})
        point = _obs("mix6", "2024-03-05T10:00:00Z")
        result = dedup_pass([period_row, point])
        assert _cluster_rids(result) == []
        assert _all_rids(result) == ["mix5", "mix6"]


# ---------------------------------------------------------------------------
# L5 — absorb guard with N singles
# ---------------------------------------------------------------------------


class TestAbsorbGuardNSinglesDom15:
    def test_three_date_only_singles_absorb_into_unique_ts_cluster(self):
        result = dedup_pass([
            _obs("ts", "2024-03-05T10:00:00Z"),
            _obs("d1", "2024-03-05"),
            _obs("d2", "2024-03-05"),
            _obs("d3", "2024-03-05"),
        ])
        assert _cluster_rids(result) == [["d1", "d2", "d3", "ts"]]
        assert result.stats["duplicate_records"] == 4

    def test_two_ts_clusters_absorb_nothing(self):
        result = dedup_pass([
            _obs("ts1", "2024-03-05T10:00:00Z"),
            _obs("ts2", "2024-03-05T14:00:00Z"),
            _obs("d", "2024-03-05"),
        ])
        assert _cluster_rids(result) == []
        assert _all_rids(result) == ["d", "ts1", "ts2"]


# ---------------------------------------------------------------------------
# L4 — runner audit rule_json contract
# ---------------------------------------------------------------------------


class TestRunnerAuditRuleJsonDom15:
    def test_rule_json_is_survivorship_tuple_not_ranking_key(self):
        resources = [
            _obs("a1", "2024-03-05T10:00:00Z"),
            _obs("a2", "2024-03-05T10:20:00Z"),
        ]
        conn = duckdb.connect()
        try:
            run_dedup(resources, "l4-run", conn=conn)
            rows = load_dedup_audit(conn, "l4-run")
        finally:
            conn.close()
        assert len(rows) == 1
        rule_json = rows[0]["rule_json"]
        # [signature, richness, rid] — 3 elements, no timestamp tuple.
        assert isinstance(rule_json, list) and len(rule_json) == 3
        assert rule_json[0] == "DT_Z"
        assert isinstance(rule_json[1], int)
        assert rule_json[2] == "a1"
        json_text = str(rule_json)
        assert "10:00" not in json_text and "(" not in json_text


# ---------------------------------------------------------------------------
# Cross-tz-midnight partition miss — documented trade-off pin
# ---------------------------------------------------------------------------


class TestCrossTzMidnightPartitionDom15:
    def test_same_instant_z_offset_cluster_when_dates_agree(self):
        result = dedup_pass([
            _obs("z", "2024-03-05T23:30:00Z"),
            _obs("off", "2024-03-05T17:30:00-06:00"),
        ])
        assert _cluster_rids(result) == [["off", "z"]]

    def test_cross_tz_midnight_miss_is_never_a_false_merge(self):
        """DOCUMENTED TRADE-OFF (design §2a): DT_Z rows partition on the
        DEFAULT-TZ render while offset rows partition on authored wall
        clock, so the same instant authored with a far offset whose wall
        date differs from the default-TZ date lands in another partition.
        Recall miss only — both rows are preserved, never falsely merged.
        (04:00Z = 2024-03-04 22:00 Chicago vs wall 2024-03-05 at +06:00.)"""
        result = dedup_pass([
            _obs("r-z", "2024-03-05T04:00:00Z"),
            _obs("r-off", "2024-03-05T10:00:00+06:00"),
        ])
        assert _cluster_rids(result) == []
        assert _all_rids(result) == ["r-off", "r-z"]
