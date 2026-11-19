"""AMUX-142 slice 2 — Stage-1 partitioning + Stage-2 temporal clustering tests.

Grounding: FEATURE_TEMPORAL_DEDUP.md §2a/§2b/§2e, §3, §9, plus the code-key
addendum (canonical code SETS, any-intersection matching inside the exact
partition bucket, any-member window exceptions).
"""

from __future__ import annotations

import random

import pytest

from fhir4ds.dedup import (
    Category,
    DedupRecord,
    POC_TROPONIN,
    VITAL_EXTENDED_WINDOW_LOINC,
    dedup_pass,
    escalate,
    normalize_codes,
    partition,
)
from fhir4ds.dedup.pipeline import _partition_date
from fhir4ds.dedup.temporal import Signature

_OBS_CATEGORY = ("http://terminology.hl7.org/CodeSystem/observation-category")
_LOINC = "http://loinc.org"
_SNOMED = "http://snomed.info/sct"


def _obs(rid, effective=None, *, code="8867-4", value=120, unit="mm[Hg]",
         cat="vital-signs", issued=None, subject="Patient/p1", codings=None):
    resource = {"resourceType": "Observation", "id": rid, "status": "final",
                "subject": {"reference": subject},
                "code": {"coding": codings if codings is not None else
                         [{"system": _LOINC, "code": code}]},
                "category": [{"coding": [{"system": _OBS_CATEGORY,
                                          "code": cat}]}]}
    if effective is not None:
        resource["effectiveDateTime"] = effective
    if issued is not None:
        resource["issued"] = issued
    if value is not None:
        resource["valueQuantity"] = {"value": value, "unit": unit,
                                     "code": unit}
    return resource


def _lab(rid, effective, *, code="2160-0", value=140, unit="mg/dL",
         issued=None, subject="Patient/p1", codings=None):
    return _obs(rid, effective, code=code, value=value, unit=unit,
                cat="laboratory", issued=issued, subject=subject,
                codings=codings)


def _condition(rid, onset, *, subject="Patient/p1"):
    return {"resourceType": "Condition", "id": rid,
            "subject": {"reference": subject},
            "code": {"coding": [{"system": _SNOMED, "code": "195967001"}]},
            "onsetDateTime": onset}


def _procedure(rid, temporal, *, subject="Patient/p1"):
    resource = {"resourceType": "Procedure", "id": rid,
                "subject": {"reference": subject},
                "code": {"coding": [{"system": _SNOMED,
                                     "code": "715252007"}]}}
    resource.update(temporal)
    return resource


def _rids(records):
    return sorted(r.rid for r in records)


def _cluster_rids(result):
    return [sorted(r.rid for r in cluster) for cluster in result.clusters]


# ---------------------------------------------------------------------------
# DedupRecord.from_resource
# ---------------------------------------------------------------------------


class TestDedupRecord:
    def test_basic_fields(self):
        record = DedupRecord.from_resource(
            _lab("l1", "2024-03-05T10:00:00Z", issued="2024-03-05T09:00:00Z"))
        assert record.rid == "l1"
        assert record.rtype == "Observation"
        assert record.patient_ref == "Patient/p1"
        assert record.nd is not None
        assert record.nd.signature == Signature.DT_Z
        assert record.code_keys == frozenset({("http://loinc.org", "2160-0")})
        assert record.category == Category.LAB
        assert record.secondary_ts == "2024-03-05T09:00:00.000Z"

    def test_patient_ref_variants(self):
        absolute = DedupRecord.from_resource(
            _lab("a", "2024-03-05T10:00:00Z",
                 subject="https://example.org/fhir/Patient/abc"))
        assert absolute.patient_ref == "Patient/abc"
        versioned = DedupRecord.from_resource(
            _lab("v", "2024-03-05T10:00:00Z",
                 subject="Patient/abc/_history/2"))
        assert versioned.patient_ref == "Patient/abc"

    def test_non_patient_subject_is_none(self):
        group_subject = _lab("g", "2024-03-05T10:00:00Z",
                             subject="Group/g7")
        assert DedupRecord.from_resource(group_subject).patient_ref is None

    def test_missing_id_raises(self):
        resource = _lab("x", "2024-03-05T10:00:00Z")
        del resource["id"]
        with pytest.raises(ValueError):
            DedupRecord.from_resource(resource)

    def test_frozen(self):
        record = DedupRecord.from_resource(_lab("l", "2024-03-05T10:00:00Z"))
        with pytest.raises(Exception):
            record.rid = "other"

    def test_nd_none_for_untimestamped(self):
        record = DedupRecord.from_resource(_obs("n", None))
        assert record.nd is None
        assert _partition_date(record) == ""


# ---------------------------------------------------------------------------
# Stage 1 — partitioning
# ---------------------------------------------------------------------------


class TestPartition:
    def _records(self, resources):
        return [DedupRecord.from_resource(r) for r in resources]

    def test_same_key_groups(self):
        singletons, groups = partition(self._records([
            _lab("a", "2024-03-05T10:00:00Z"),
            _lab("b", "2024-03-05T10:05:00Z"),
        ]))
        assert singletons == []
        assert len(groups) == 1
        assert _rids(groups[0]) == ["a", "b"]

    def test_different_patient_splits(self):
        singletons, groups = partition(self._records([
            _lab("a", "2024-03-05T10:00:00Z"),
            _lab("b", "2024-03-05T10:05:00Z", subject="Patient/p2"),
        ]))
        assert groups == []
        assert _rids(singletons) == ["a", "b"]

    def test_different_code_splits_within_bucket(self):
        # Same exact axes, disjoint code sets -> no union.
        singletons, groups = partition(self._records([
            _lab("a", "2024-03-05T10:00:00Z", code="2160-0"),
            _lab("b", "2024-03-05T10:00:00Z", code="2093-3"),
        ]))
        assert groups == []
        assert _rids(singletons) == ["a", "b"]

    def test_different_local_date_splits(self):
        singletons, groups = partition(self._records([
            _lab("a", "2024-03-05T10:00:00Z"),
            _lab("b", "2024-03-06T10:00:00Z"),
        ]))
        assert groups == []
        assert _rids(singletons) == ["a", "b"]

    def test_2330_offset_and_naive_same_day(self):
        # The card's canonical case: 23:30 with an offset and 23:30 naive
        # describe the same local day -> same partition.
        singletons, groups = partition(self._records([
            _lab("off", "2024-03-05T23:30:00-06:00"),
            _lab("naive", "2024-03-05T23:30:00"),
        ]))
        assert singletons == []
        assert len(groups) == 1
        assert _rids(groups[0]) == ["naive", "off"]

    def test_z_instant_renders_local_date_in_default_tz(self):
        # 2024-03-06T04:30Z is 2024-03-05 22:30 in Chicago (CST) -> same
        # authored-local day as the naive 23:30 row.
        singletons, groups = partition(self._records([
            _lab("z", "2024-03-06T04:30:00Z"),
            _lab("naive", "2024-03-05T23:30:00"),
        ]))
        assert len(groups) == 1

    def test_z_and_offset_same_instant_same_partition(self):
        singletons, groups = partition(self._records([
            _lab("z", "2024-03-05T23:30:00Z"),
            _lab("off", "2024-03-05T17:30:00-06:00"),
        ]))
        assert len(groups) == 1

    def test_cross_unit_value_collision_partitions(self):
        # §9 revision: UCUM canonicalization makes 5 g and 5000 mg equal keys.
        singletons, groups = partition(self._records([
            _obs("g", "2024-03-05T10:00:00Z", code="29463-7", value=5,
                 unit="g"),
            _obs("mg", "2024-03-05T10:00:00Z", code="29463-7", value=5000,
                 unit="mg"),
        ]))
        assert singletons == []
        assert len(groups) == 1

    def test_different_value_splits(self):
        singletons, groups = partition(self._records([
            _lab("a", "2024-03-05T10:00:00Z", value=140),
            _lab("b", "2024-03-05T10:00:00Z", value=180),
        ]))
        assert groups == []

    def test_groups_sorted_by_key_members_by_rid(self):
        singletons, groups = partition(self._records([
            _lab("zz", "2024-03-06T10:00:00Z"),
            _lab("b", "2024-03-05T10:00:00Z"),
            _lab("a", "2024-03-05T10:05:00Z"),
            _lab("c", "2024-03-05T10:10:00Z"),
        ]))
        assert _rids(singletons) == ["zz"]
        assert len(groups) == 1
        assert _rids(groups[0]) == ["a", "b", "c"]

    def test_singleton_groups_emit_directly(self):
        singletons, groups = partition(self._records([
            _lab("only", "2024-03-05T10:00:00Z"),
        ]))
        assert groups == []
        assert _rids(singletons) == ["only"]

    def test_month_rows_share_year_bucket_with_year_rows(self):
        # Precision-scoped bucket: YEAR/MONTH rows bucket on the year so the
        # §2b subsumption rule is reachable within one group.
        singletons, groups = partition(self._records([
            _condition("y", "2024"),
            _condition("m", "2024-06"),
        ]))
        assert singletons == []
        assert len(groups) == 1

    def test_month_rows_of_different_months_share_bucket(self):
        singletons, groups = partition(self._records([
            _condition("m1", "2024-03"),
            _condition("m2", "2024-05"),
        ]))
        assert len(groups) == 1  # same bucket; Stage 2 decides clustering


# ---------------------------------------------------------------------------
# Code-key addendum — intersection semantics
# ---------------------------------------------------------------------------


class TestCodeSetIntersection:
    def test_loinc_primary_plus_snomed_translation_merges(self):
        result = dedup_pass([
            _lab("a", "2024-03-05T10:00:00Z",
                 codings=[{"system": _LOINC, "code": "2160-0"},
                          {"system": _SNOMED, "code": "109811008"}]),
            _lab("b", "2024-03-05T10:05:00Z",
                 codings=[{"system": _SNOMED, "code": "109811008"}]),
        ])
        assert _cluster_rids(result) == [["a", "b"]]

    def test_no_intersection_stays_apart(self):
        result = dedup_pass([
            _lab("a", "2024-03-05T10:00:00Z", code="2160-0"),
            _lab("b", "2024-03-05T10:00:00Z", code="2093-3"),
        ])
        assert result.clusters == []
        assert _rids(result.emitted) == ["a", "b"]

    def test_coding_order_independent_key(self):
        forward = DedupRecord.from_resource(_lab(
            "a", "2024-03-05T10:00:00Z",
            codings=[{"system": _LOINC, "code": "2160-0"},
                     {"system": _SNOMED, "code": "109811008"}]))
        reverse = DedupRecord.from_resource(_lab(
            "b", "2024-03-05T10:00:00Z",
            codings=[{"system": _SNOMED, "code": "109811008"},
                     {"system": _LOINC, "code": "2160-0"}]))
        assert forward.code_keys == reverse.code_keys
        assert normalize_codes(forward.resource) == \
            normalize_codes(reverse.resource)

    def test_empty_code_sets_never_union(self):
        uncoded = {"resourceType": "Observation", "id": "u1", "status":
                   "final", "subject": {"reference": "Patient/p1"},
                   "code": {"text": "uncoded"},
                   "category": [{"coding": [{"system": _OBS_CATEGORY,
                                             "code": "laboratory"}]}],
                   "effectiveDateTime": "2024-03-05T10:00:00Z",
                   "valueQuantity": {"value": 140, "unit": "mg/dL",
                                     "code": "mg/dL"}}
        twin = dict(uncoded, id="u2")
        result = dedup_pass([uncoded, twin])
        assert result.clusters == []
        assert _rids(result.emitted) == ["u1", "u2"]

    def test_empty_set_does_not_bridge_two_coded_records(self):
        # a~b share code X; an uncoded row in the same bucket must not
        # change their component.
        result = dedup_pass([
            _lab("a", "2024-03-05T10:00:00Z"),
            _lab("b", "2024-03-05T10:05:00Z"),
            _lab("u", "2024-03-05T10:07:00Z", codings=[]),
        ])
        assert _cluster_rids(result) == [["a", "b"]]
        assert _rids(result.emitted) == ["u"]

    def test_transitive_union_within_bucket(self):
        # a~b via LOINC, b~c via SNOMED -> one component.
        result = dedup_pass([
            _lab("a", "2024-03-05T10:00:00Z", code="11111-1"),
            _lab("b", "2024-03-05T10:05:00Z",
                 codings=[{"system": _LOINC, "code": "11111-1"},
                          {"system": _SNOMED, "code": "22222"}]),
            _lab("c", "2024-03-05T10:10:00Z",
                 codings=[{"system": _SNOMED, "code": "22222"}]),
        ])
        assert _cluster_rids(result) == [["a", "b", "c"]]

    def test_oid_and_url_systems_intersect(self):
        result = dedup_pass([
            _lab("oid", "2024-03-05T10:00:00Z",
                 codings=[{"system": "urn:oid:2.16.840.1.113883.6.1",
                           "code": "2160-0"}]),
            _lab("url", "2024-03-05T10:05:00Z",
                 codings=[{"system": _LOINC, "code": "2160-0"}]),
        ])
        assert _cluster_rids(result) == [["oid", "url"]]


# ---------------------------------------------------------------------------
# Stage 2 — OTHER: same-date merge + MONTH/YEAR subsumption
# ---------------------------------------------------------------------------


class TestEscalateOther:
    def test_same_local_date_merges(self):
        result = dedup_pass([
            _condition("c1", "2024-03-05"),
            _condition("c2", "2024-03-05"),
        ])
        assert _cluster_rids(result) == [["c1", "c2"]]

    def test_different_dates_stay_apart(self):
        result = dedup_pass([
            _condition("c1", "2024-03-05"),
            _condition("c2", "2024-03-06"),
        ])
        assert result.clusters == []

    def test_month_absorbs_into_year_span(self):
        result = dedup_pass([
            _condition("y", "2024"),
            _condition("m", "2024-06"),
        ])
        assert _cluster_rids(result) == [["m", "y"]]

    def test_year_absorbs_multiple_months(self):
        result = dedup_pass([
            _condition("y", "2024"),
            _condition("m1", "2024-03"),
            _condition("m2", "2024-09"),
        ])
        assert _cluster_rids(result) == [["m1", "m2", "y"]]

    def test_non_contained_month_forms_own_cluster(self):
        # Only MONTH rows, different months: no containment -> singletons.
        result = dedup_pass([
            _condition("m1", "2024-03"),
            _condition("m2", "2024-05"),
        ])
        assert result.clusters == []
        assert _rids(result.emitted) == ["m1", "m2"]

    def test_same_month_merges_by_local_date(self):
        result = dedup_pass([
            _condition("m1", "2024-06"),
            _condition("m2", "2024-06"),
        ])
        assert _cluster_rids(result) == [["m1", "m2"]]

    def test_month_does_not_absorb_into_day_cluster(self):
        # A day-precision span cannot contain a month span.
        result = dedup_pass([
            _condition("d1", "2024-03-05"),
            _condition("d2", "2024-03-05"),
            _condition("m", "2024-03"),
        ])
        assert _cluster_rids(result) == [["d1", "d2"]]
        assert _rids(result.emitted) == ["m"]

    def test_dt_rows_share_local_date_with_date_only(self):
        result = dedup_pass([
            _condition("dt", "2024-03-05T14:30:00"),
            _condition("d", "2024-03-05"),
        ])
        assert _cluster_rids(result) == [["d", "dt"]]

    def test_procedure_period_vs_datetime_same_day(self):
        result = dedup_pass([
            _procedure("p1", {"performedPeriod": {
                "start": "2024-03-05T10:00:00Z",
                "end": "2024-03-05T11:00:00Z"}}),
            _procedure("p2", {"performedDateTime": "2024-03-05T10:30:00Z"}),
        ])
        assert _cluster_rids(result) == [["p1", "p2"]]

    def test_procedure_different_days_split(self):
        result = dedup_pass([
            _procedure("p1", {"performedDateTime": "2024-03-05T10:30:00Z"}),
            _procedure("p2", {"performedDateTime": "2024-03-06T10:30:00Z"}),
        ])
        assert result.clusters == []


# ---------------------------------------------------------------------------
# Stage 2 — LAB windows
# ---------------------------------------------------------------------------


class TestEscalateLab:
    def test_within_30min_merges(self):
        result = dedup_pass([
            _lab("a", "2024-03-05T10:00:00Z"),
            _lab("b", "2024-03-05T10:29:00Z"),
        ])
        assert _cluster_rids(result) == [["a", "b"]]

    def test_exactly_30min_merges(self):
        result = dedup_pass([
            _lab("a", "2024-03-05T10:00:00Z"),
            _lab("b", "2024-03-05T10:30:00Z"),
        ])
        assert _cluster_rids(result) == [["a", "b"]]

    def test_31min_splits(self):
        result = dedup_pass([
            _lab("a", "2024-03-05T10:00:00Z"),
            _lab("b", "2024-03-05T10:31:00Z"),
        ])
        assert result.clusters == []
        assert _rids(result.emitted) == ["a", "b"]

    def test_single_linkage_chains(self):
        # 20min gaps chain three rows into one cluster.
        result = dedup_pass([
            _lab("a", "2024-03-05T10:00:00Z"),
            _lab("b", "2024-03-05T10:20:00Z"),
            _lab("c", "2024-03-05T10:40:00Z"),
        ])
        assert _cluster_rids(result) == [["a", "b", "c"]]

    def test_troponin_5min_window(self):
        assert "10839-9" in POC_TROPONIN
        trop = lambda rid, eff: _lab(rid, eff, code="10839-9", value=0.04,
                                     unit="ng/mL")
        result = dedup_pass([trop("t1", "2024-03-05T10:00:00Z"),
                             trop("t2", "2024-03-05T10:04:00Z")])
        assert _cluster_rids(result) == [["t1", "t2"]]
        result = dedup_pass([trop("t1", "2024-03-05T10:00:00Z"),
                             trop("t2", "2024-03-05T10:06:00Z")])
        assert result.clusters == []

    def test_troponin_splits_a_20min_pair(self):
        trop = lambda rid, eff: _lab(rid, eff, code="10839-9", value=0.04,
                                     unit="ng/mL")
        result = dedup_pass([trop("t1", "2024-03-05T10:00:00Z"),
                             trop("t2", "2024-03-05T10:20:00Z")])
        assert result.clusters == []

    def test_window_exception_via_any_member_code(self):
        # Non-troponin LOINC row unions with a troponin row via a shared
        # SNOMED translation -> the group uses the 5-minute window.
        shared = {"system": _SNOMED, "code": "109811008"}
        result = dedup_pass([
            _lab("nt", "2024-03-05T10:00:00Z",
                 codings=[{"system": _LOINC, "code": "2160-0"}, shared]),
            _lab("tr", "2024-03-05T10:06:00Z",
                 codings=[{"system": _LOINC, "code": "10839-9"}, shared]),
        ])
        assert result.clusters == []
        result = dedup_pass([
            _lab("nt", "2024-03-05T10:00:00Z",
                 codings=[{"system": _LOINC, "code": "2160-0"}, shared]),
            _lab("tr", "2024-03-05T10:04:00Z",
                 codings=[{"system": _LOINC, "code": "89579-7"}, shared]),
        ])
        assert _cluster_rids(result) == [["nt", "tr"]]

    def test_exact_effective_equals_issued_merges(self):
        result = dedup_pass([
            _lab("e1", "2024-03-05T10:00:00Z"),
            _lab("e2", "2024-03-05T14:00:00Z", issued="2024-03-05T10:00:00Z"),
        ])
        assert _cluster_rids(result) == [["e1", "e2"]]

    def test_exact_cross_field_needs_instant_match(self):
        result = dedup_pass([
            _lab("e1", "2024-03-05T10:00:00Z"),
            _lab("e2", "2024-03-05T14:00:00Z", issued="2024-03-05T10:05:00Z"),
        ])
        assert result.clusters == []

    def test_absorb_guard_one_cluster(self):
        result = dedup_pass([
            _lab("ts", "2024-03-05T10:00:00Z"),
            _lab("d1", "2024-03-05"),
            _lab("d2", "2024-03-05"),
        ])
        assert _cluster_rids(result) == [["d1", "d2", "ts"]]

    def test_absorb_guard_two_clusters_no_absorb(self):
        result = dedup_pass([
            _lab("ts1", "2024-03-05T10:00:00Z"),
            _lab("ts2", "2024-03-05T12:00:00Z"),
            _lab("d", "2024-03-05"),
        ])
        assert result.clusters == []
        assert _rids(result.emitted) == ["d", "ts1", "ts2"]

    def test_naive_interpreted_in_default_tz_for_windowing(self):
        # 23:30 Chicago (CST, UTC-6) == 23:30-06:00 -> same instant.
        result = dedup_pass([
            _lab("off", "2024-03-05T23:30:00-06:00"),
            _lab("naive", "2024-03-05T23:30:00"),
        ])
        assert _cluster_rids(result) == [["naive", "off"]]

    def test_nd_none_rows_stay_singleton_in_group(self):
        result = dedup_pass([
            _lab("ts", "2024-03-05T10:00:00Z"),
            _lab("ts2", "2024-03-05T10:05:00Z"),
            _lab("none", None),
            _lab("none2", None),
        ])
        assert _cluster_rids(result) == [["ts", "ts2"]]
        assert _rids(result.emitted) == ["none", "none2"]


# ---------------------------------------------------------------------------
# Stage 2 — VITAL windows
# ---------------------------------------------------------------------------


class TestEscalateVital:
    def test_within_5min_merges(self):
        result = dedup_pass([
            _obs("a", "2024-03-05T10:00:00Z"),
            _obs("b", "2024-03-05T10:04:00Z"),
        ])
        assert _cluster_rids(result) == [["a", "b"]]

    def test_exactly_5min_merges(self):
        result = dedup_pass([
            _obs("a", "2024-03-05T10:00:00Z"),
            _obs("b", "2024-03-05T10:05:00Z"),
        ])
        assert _cluster_rids(result) == [["a", "b"]]

    def test_6min_splits(self):
        result = dedup_pass([
            _obs("a", "2024-03-05T10:00:00Z"),
            _obs("b", "2024-03-05T10:06:00Z"),
        ])
        assert result.clusters == []

    def test_height_extended_window_29min(self):
        assert "8302-2" in VITAL_EXTENDED_WINDOW_LOINC
        result = dedup_pass([
            _obs("h1", "2024-03-05T10:00:00Z", code="8302-2", value=180,
                 unit="cm"),
            _obs("h2", "2024-03-05T10:29:00Z", code="8302-2", value=180,
                 unit="cm"),
        ])
        assert _cluster_rids(result) == [["h1", "h2"]]

    def test_height_extended_window_31min_splits(self):
        result = dedup_pass([
            _obs("h1", "2024-03-05T10:00:00Z", code="8302-2", value=180,
                 unit="cm"),
            _obs("h2", "2024-03-05T10:31:00Z", code="8302-2", value=180,
                 unit="cm"),
        ])
        assert result.clusters == []

    def test_weight_and_bmi_extended_windows(self):
        for code, unit in (("29463-7", "kg"), ("39156-5", "kg/m2")):
            result = dedup_pass([
                _obs("w1", "2024-03-05T10:00:00Z", code=code, value=80,
                     unit=unit),
                _obs("w2", "2024-03-05T10:20:00Z", code=code, value=80,
                     unit=unit),
            ])
            assert _cluster_rids(result) == [["w1", "w2"]], code

    def test_temperature_stays_5min(self):
        # 8310-5 body temperature is a vital but NOT in the extended set.
        result = dedup_pass([
            _obs("t1", "2024-03-05T10:00:00Z", code="8310-5", value=37,
                 unit="Cel"),
            _obs("t2", "2024-03-05T10:20:00Z", code="8310-5", value=37,
                 unit="Cel"),
        ])
        assert result.clusters == []

    def test_vital_absorb_guard(self):
        result = dedup_pass([
            _obs("ts", "2024-03-05T10:00:00Z"),
            _obs("d", "2024-03-05"),
        ])
        assert _cluster_rids(result) == [["d", "ts"]]
        result = dedup_pass([
            _obs("ts1", "2024-03-05T10:00:00Z"),
            _obs("ts2", "2024-03-05T12:00:00Z"),
            _obs("d", "2024-03-05"),
        ])
        assert result.clusters == []
        assert _rids(result.emitted) == ["d", "ts1", "ts2"]


# ---------------------------------------------------------------------------
# Determinism / pipeline surface
# ---------------------------------------------------------------------------


class TestDeterminismAndPipeline:
    def _corpus(self):
        return [
            _lab("a", "2024-03-05T10:00:00Z"),
            _lab("b", "2024-03-05T10:29:00Z"),
            _lab("c", "2024-03-05T11:30:00Z"),
            _lab("d", "2024-03-05"),
            _obs("v1", "2024-03-05T09:00:00Z"),
            _obs("v2", "2024-03-05T09:03:00Z"),
            _obs("v3", "2024-03-05T09:10:00Z"),
            _condition("k1", "2024-03-05"),
            _condition("k2", "2024-03-05"),
            _condition("y", "2024"),
            _condition("m", "2024-06"),
            _lab("x", "2024-03-05T10:00:00Z", subject="Patient/p2"),
        ]

    def test_shuffled_input_identical_clusters(self):
        baseline = _cluster_rids(dedup_pass(self._corpus()))
        assert baseline  # the corpus produces clusters
        rng = random.Random(1234)
        for _ in range(5):
            corpus = self._corpus()
            rng.shuffle(corpus)
            assert _cluster_rids(dedup_pass(corpus)) == baseline

    def test_stats_shape(self):
        result = dedup_pass(self._corpus())
        stats = result.stats
        assert stats["input_resources"] == 12
        assert stats["records"] == 12
        assert stats["clusters"] == len(result.clusters)
        assert stats["duplicate_records"] == \
            sum(len(c) for c in result.clusters)
        assert stats["emitted"] == len(result.emitted)
        assert stats["duplicate_records"] + stats["emitted"] == 12

    def test_clusters_sorted_members_and_clusters(self):
        for cluster in dedup_pass(self._corpus()).clusters:
            rids = [r.rid for r in cluster]
            assert rids == sorted(rids)
        firsts = [c[0].rid for c in dedup_pass(self._corpus()).clusters]
        assert firsts == sorted(firsts)

    def test_no_duplicate_membership(self):
        result = dedup_pass(self._corpus())
        seen = [r.rid for c in result.clusters for r in c] + \
            [r.rid for r in result.emitted]
        assert len(seen) == len(set(seen))

    def test_multi_patient_isolation(self):
        result = dedup_pass([
            _lab("a", "2024-03-05T10:00:00Z"),
            _lab("b", "2024-03-05T10:05:00Z"),
            _lab("c", "2024-03-05T10:05:00Z", subject="Patient/p2"),
        ])
        assert _cluster_rids(result) == [["a", "b"]]
        assert _rids(result.emitted) == ["c"]

    def test_escalate_returns_all_clusters_including_singletons(self):
        group = [DedupRecord.from_resource(r) for r in [
            _lab("a", "2024-03-05T10:00:00Z"),
            _lab("b", "2024-03-05T12:00:00Z"),
        ]]
        clusters = escalate(group)
        assert sorted(len(c) for c in clusters) == [1, 1]

    def test_escalate_empty_group(self):
        assert escalate([]) == []

    def test_absent_subject_groups_by_none_patient_ref(self):
        # No subject at all: patient_ref None groups records together.
        no_subject = _lab("a", "2024-03-05T10:00:00Z")
        del no_subject["subject"]
        twin = dict(no_subject, id="b")
        twin["effectiveDateTime"] = "2024-03-05T10:05:00Z"
        result = dedup_pass([no_subject, twin])
        assert _cluster_rids(result) == [["a", "b"]]

    def test_group_subject_never_mixes_with_patient(self):
        result = dedup_pass([
            _lab("a", "2024-03-05T10:00:00Z"),
            _lab("g", "2024-03-05T10:05:00Z", subject="Group/g7"),
        ])
        assert result.clusters == []
