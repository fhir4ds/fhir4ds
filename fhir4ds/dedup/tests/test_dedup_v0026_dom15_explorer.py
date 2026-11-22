"""D15 EXPLORER regressions (v0.0.26 evolution, iteration 47).

QA-D15E-001: ``_cross_bucket_near_misses`` deduplicated near-miss pairs on
the BARE rid pair, ignoring resource type. FHIR ids are unique per TYPE
only (the QA-D15H-001 doctrine), so a Condition pair (a, b) sharing a
tier-2 text suppressed the entirely distinct Observation pair (a, b) —
a cross-bucket near-miss curation entry silently vanished from the
human-review queue. Audit-trail completeness defect; no merge impact.
"""
from __future__ import annotations

from fhir4ds.dedup.pipeline import dedup_pass


def _condition(rid: str, day: str, text: str) -> dict:
    return {"resourceType": "Condition", "id": rid,
            "subject": {"reference": "Patient/p1"},
            "code": {"text": text},
            "onsetDateTime": day}


def _observation(rid: str, day: str, text: str) -> dict:
    return {"resourceType": "Observation", "id": rid,
            "subject": {"reference": "Patient/p1"},
            "code": {"text": text},
            "effectiveDateTime": day}


def test_cross_bucket_near_miss_survives_cross_type_id_collision():
    """Both same-type pairs keep their curation entries when a Condition
    and an Observation pair share the same rid pair (legal FHIR)."""
    result = dedup_pass([
        _condition("a", "2024-01-01T10:00:00", "chest pain"),
        _condition("b", "2024-02-01T10:00:00", "chest pain"),
        _observation("a", "2024-01-01T10:00:00", "headache"),
        _observation("b", "2024-02-01T10:00:00", "headache"),
    ])
    entries = [e for e in result.curation_records
               if e["kind"] == "near_miss"
               and e.get("reason") == "cross_bucket"]
    by_type = {e["resource_type"]: e for e in entries}
    assert set(by_type) == {"Condition", "Observation"}, (
        f"expected both near-miss entries, got {sorted(by_type)}")
    # evidence must name the right resources (QA-D15H-001 doctrine)
    assert by_type["Condition"]["rids"] == ["a", "b"]
    assert by_type["Observation"]["rids"] == ["a", "b"]


def test_cross_bucket_near_miss_pair_dedup_within_type_still_applies():
    """One entry per (type, pair): a pair sharing TWO tier-2 texts yields a
    single curation entry (the in-type dedup contract is unchanged)."""
    result = dedup_pass([
        _condition("a", "2024-01-01T10:00:00", "chest pain"),
        _condition("b", "2024-02-01T10:00:00", "chest pain"),
        _condition("c", "2024-01-01T10:00:00", "chest pain"),
        # 'a' and 'c' share a SECOND text too (same-day, but disjoint
        # concepts -> cross-bucket pair on both texts)
        dict(_condition("a", "2024-01-01T10:00:00", "shortness of breath"),
             id="a"),
    ])
    pairs = sorted(
        tuple(e["rids"]) for e in result.curation_records
        if e["kind"] == "near_miss" and e.get("reason") == "cross_bucket")
    # (a,b) and (a,c) and (b,?) — every DISTINCT pair appears at most once
    assert len(pairs) == len(set(pairs)), f"duplicate pair entries: {pairs}"


def test_temporal_rejected_near_miss_respects_bucket_rtype():
    """QA-D15E-001 follow-on: a temporal_rejected edge is built inside ONE
    Stage-1 bucket (fixed rtype); when BOTH rids also collide with another
    type's ids, the audit entry must still report the bucket's type."""
    result = dedup_pass([
        # decoy same-id Conditions (parsed FIRST so the multimap scan
        # would hit them without an rtype-aware lookup)
        _condition("a", "2024-06-01T10:00:00", "unrelated one"),
        _condition("b", "2024-07-01T10:00:00", "unrelated two"),
        # same-bucket LAB pair on the text tier, split by the 30-min window
        {"resourceType": "Observation", "id": "a",
         "subject": {"reference": "Patient/p1"},
         "category": [{"coding": [{
             "system": "http://terminology.hl7.org/CodeSystem/"
                       "observation-category", "code": "laboratory"}]}],
         "code": {"text": "chest pain"},
         "effectiveDateTime": "2024-01-01T09:00:00",
         "valueQuantity": {"value": 1, "unit": "mg"}},
        {"resourceType": "Observation", "id": "b",
         "subject": {"reference": "Patient/p1"},
         "category": [{"coding": [{
             "system": "http://terminology.hl7.org/CodeSystem/"
                       "observation-category", "code": "laboratory"}]}],
         "code": {"text": "chest pain"},
         "effectiveDateTime": "2024-01-01T13:00:00",
         "valueQuantity": {"value": 1, "unit": "mg"}},
    ])
    temporal = [e for e in result.curation_records
                if e["kind"] == "near_miss"
                and e.get("reason") == "temporal_rejected"]
    assert len(temporal) == 1, (
        f"expected one temporal_rejected entry, got {temporal}")
    entry = temporal[0]
    assert entry["resource_type"] == "Observation", entry
    assert entry["patient_ref"] == "Patient/p1", entry
    assert entry["bucket"][1] == "Observation", entry


def test_cross_bucket_near_miss_reversed_processing_order():
    """Deterministic regardless of which type sorts first: both orders of
    the same corpus (shuffled input) produce the same queue."""
    corpus = [
        _observation("a", "2024-01-01T10:00:00", "headache"),
        _observation("b", "2024-02-01T10:00:00", "headache"),
        _condition("a", "2024-01-01T10:00:00", "chest pain"),
        _condition("b", "2024-02-01T10:00:00", "chest pain"),
    ]
    one = dedup_pass(corpus)
    two = dedup_pass(list(reversed(corpus)))
    key = lambda rs: sorted(  # noqa: E731
        (e["resource_type"], tuple(e["rids"]))
        for e in rs.curation_records if e["kind"] == "near_miss")
    assert key(one) == key(two)
    assert {t for t, _ in key(one)} == {"Condition", "Observation"}
