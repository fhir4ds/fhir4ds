"""AMUX-142 dedup GATES — golden corpus P/R, TZ/signature properties,
determinism hash (design doc §5/§6).

Three gate families:

1. **Golden corpus gate** (:class:`TestGoldenCorpusGate`): the labeled corpus
   (``fixtures/dedup_golden_corpus.json``, generated + self-checked by
   ``scripts/gen_dedup_golden.py``) evaluated end to end through
   :func:`~fhir4ds.dedup.runner.run_dedup`. Pairwise P/R over clusters
   (matching-gate convention): a pair is predicted-duplicate when co-clustered.
   Precision is a 1.0 TARGET (any false merge — on a labeled hard negative or
   an unlabeled pair — is a failure to investigate, never a baseline dip);
   recall is gated against the recorded baseline ±0.02; survivorship accuracy
   must be 1.0.
2. **TZ/signature property matrix** (:class:`TestTZSignatureProperties`):
   table-driven (no hypothesis) grid over authored instants — hour
   boundaries, midnight-adjacent, and both 2024 America/Chicago DST
   transition nights — asserting that partition keys and clustering are
   invariant under representation choice (Z vs authored-offset vs naive for
   the same instant), that ``local_date`` never shifts a day from the
   authored local component, and that fall-back ambiguity resolves by the
   documented fold=0 convention.
3. **Determinism hash gate** (:class:`TestDeterminismHash`): two full runs
   over shuffled inputs produce an identical sha256 over (sorted survivor
   JSON, sorted Linkage JSON, sorted audit rows modulo ``run_id``), and
   survivor ids are pure functions of the sorted member ids.
"""

from __future__ import annotations

import hashlib
import json
import random
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import duckdb
import pytest

from fhir4ds.dedup import (
    DEFAULT_TZ,
    Signature,
    dedup_pass,
    load_dedup_audit,
    normalize_temporal,
    run_dedup,
)
from fhir4ds.dedup.evaluation import (
    PRECISION_TARGET,
    RECALL_TOLERANCE,
    assert_no_regression,
    evaluate_dedup_golden,
    load_baseline,
    load_golden_corpus,
)
from fhir4ds.dedup.pipeline import _partition_date
from fhir4ds.dedup.survivorship import survivor_dedup_id

LOINC = "http://loinc.org"
_TZ = ZoneInfo(DEFAULT_TZ)


# ===========================================================================
# 1. Golden corpus gate
# ===========================================================================


class TestGoldenCorpusGate:
    @pytest.fixture(scope="class")
    def metrics(self):
        corpus = load_golden_corpus()
        assert len(corpus["clusters"]) >= 145, "corpus shrank unexpectedly"
        assert len(corpus["negatives"]) >= 55, "corpus shrank unexpectedly"
        return evaluate_dedup_golden(corpus)

    def test_precision_at_target_no_false_merges(self, metrics):
        # Precision is a 1.0 TARGET: ANY false merge (labeled hard negative
        # or unlabeled pair) is a failure to investigate, not a baseline dip.
        assert metrics.precision == PRECISION_TARGET
        assert metrics.false_positives == []

    def test_recall_regression_gate(self, metrics):
        baseline = load_baseline()
        assert_no_regression(metrics, baseline)

    def test_survivorship_accuracy(self, metrics):
        assert metrics.survivorship_total >= 100, (
            "survivorship labels thinned unexpectedly"
        )
        assert metrics.survivorship_accuracy == 1.0
        assert metrics.survivorship_errors == []

    def test_corpus_composition(self, metrics):
        # Composition pins: all four v1 resource types carry labeled clusters.
        corpus = load_golden_corpus()
        by_type = {}
        rid_type = {r["id"]: r["resourceType"] for r in corpus["resources"]}
        for cluster in corpus["clusters"]:
            for member in cluster["members"]:
                rtype = rid_type[member]
                by_type[rtype] = by_type.get(rtype, 0) + 1
        assert set(by_type) == {"Observation", "Procedure", "Condition",
                                "Immunization"}
        kinds = {c["kind"] for c in corpus["clusters"]}
        for required in ("vital_cross_unit", "vital_tz_variant",
                         "lab_translation_pair", "lab_troponin_serial",
                         "lab_effective_eq_issued", "condition_year_subsumption",
                         "immunization_tz_variant"):
            assert required in kinds, f"missing duplicate axis {required}"
        neg_kinds = {n["kind"] for n in corpus["negatives"]}
        for required in ("same_code_date_diff_value", "lab_sibling_35min",
                         "vital_6min_apart", "troponin_6min_apart",
                         "different_codes_same_rest", "cross_patient_identical"):
            assert required in neg_kinds, f"missing hard-negative axis {required}"

    def test_baseline_numbers_match_measurement(self, metrics):
        baseline = load_baseline()
        assert baseline["labeled_clusters"] == metrics.labeled_clusters, (
            "corpus changed — regenerate and re-record the baseline"
        )
        assert baseline["labeled_negatives"] == metrics.labeled_negatives


# ===========================================================================
# 2. TZ / signature property matrix (table-driven, hypothesis-free)
# ===========================================================================

# Authored-instant grid (UTC): generic hour boundaries, midnight-adjacent
# instants, and both 2024 America/Chicago DST transition nights.
# 2024-03-10 02:00 CST -> 03:00 CDT (08:00Z); 2024-11-03 02:00 CDT -> 01:00 CST (07:00Z).
_GRID_UTC = [
    # generic hours + midnight boundaries (CST winter)
    "2024-01-15T06:00:00Z", "2024-01-15T05:59:00Z", "2024-01-15T12:00:00Z",
    "2024-01-16T04:30:00Z",   # 22:30 the previous local day (CST)
    # generic hours (CDT summer)
    "2024-06-15T05:00:00Z", "2024-06-15T04:59:00Z", "2024-06-15T23:30:00Z",
    "2024-06-16T03:30:00Z",
    # spring-forward night 2024-03-10
    "2024-03-10T07:59:00Z",   # 01:59 CST — last minute before the jump
    "2024-03-10T08:00:00Z",   # 03:00 CDT — first minute after (02:00-02:59 nonexistent)
    "2024-03-10T08:30:00Z",   # 03:30 CDT
    "2024-03-10T09:00:00Z",
    "2024-03-10T10:00:00Z",
    # fall-back night 2024-11-03
    "2024-11-03T05:59:00Z",   # 00:59 CDT
    "2024-11-03T06:30:00Z",   # 01:30 CDT — first occurrence (fold=0)
    "2024-11-03T07:30:00Z",   # 01:30 CST — second occurrence (fold=1)
    "2024-11-03T08:00:00Z",   # 02:00 CST
]


def _utc(text: str) -> datetime:
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def _offset_form(instant: datetime) -> str:
    local = instant.astimezone(_TZ)
    off = local.strftime("%z")
    return local.strftime("%Y-%m-%dT%H:%M:%S") + f"{off[:3]}:{off[3:]}"


def _naive_form(instant: datetime) -> str:
    return instant.astimezone(_TZ).strftime("%Y-%m-%dT%H:%M:%S")


def _fold0_instant(instant: datetime) -> datetime:
    """The instant a naive local wall clock maps to under the engine's
    fold=0 convention (differs on the second occurrence of a fall-back
    ambiguous local time)."""
    wall = instant.astimezone(_TZ).replace(tzinfo=None)
    return wall.replace(tzinfo=_TZ, fold=0).astimezone(timezone.utc)


def _obs(rid: str, effective: str) -> dict:
    return {
        "resourceType": "Observation",
        "id": rid,
        "status": "final",
        "code": {"coding": [{"system": LOINC, "code": "8480-6"}]},
        "subject": {"reference": "Patient/tzp"},
        "effectiveDateTime": effective,
        "valueQuantity": {"value": 120, "code": "mmHg", "unit": "mmHg"},
        "category": [{"coding": [{
            "system": "http://terminology.hl7.org/CodeSystem/"
                      "observation-category", "code": "vital-signs"}]}],
    }


class TestTZSignatureProperties:
    """For every grid instant: the same instant authored three ways (Z,
    authored default-TZ offset, naive local wall clock) yields identical
    partition keys and one cluster, local_date never shifts a day from the
    authored local component, and fall-back ambiguity resolves fold=0."""

    @pytest.mark.parametrize("instant_text", _GRID_UTC)
    def test_partition_key_invariant_under_representation(self, instant_text):
        instant = _utc(instant_text)
        z = normalize_temporal(_obs("a", instant_text))
        offset = normalize_temporal(_obs("b", _offset_form(instant)))
        naive = normalize_temporal(_obs("c", _naive_form(instant)))
        assert z.signature == Signature.DT_Z
        assert offset.signature == Signature.DT_OFFSET
        assert naive.signature == Signature.DT_NAIVE
        # Authored-local partition date is identical across all three forms
        # (the Z form renders in the configured default TZ).
        expected_local = instant.astimezone(_TZ).strftime("%Y-%m-%d")
        assert z.local_date == expected_local
        assert offset.local_date == expected_local
        assert naive.local_date == expected_local
        # Offset-bearing forms carry the exact same UTC instant; naive
        # never does (design §2a).
        assert z.dt_utc == offset.dt_utc
        assert naive.dt_utc is None

    @pytest.mark.parametrize("instant_text", _GRID_UTC)
    def test_same_instant_three_ways_cluster_together(self, instant_text):
        instant = _utc(instant_text)
        resources = [
            _obs("a", instant_text),
            _obs("b", _offset_form(instant)),
            _obs("c", _naive_form(instant)),
        ]
        result = dedup_pass(resources)
        if _fold0_instant(instant) == instant:
            # Unambiguous wall clock: all three representations co-cluster.
            assert [[m.rid for m in c] for c in result.clusters] == [
                ["a", "b", "c"]]
        else:
            # Second occurrence of a fall-back ambiguous local time: the
            # naive wall-clock string maps to the FIRST occurrence under
            # the documented fold=0 convention, so it names a DIFFERENT
            # instant and must not join the Z+offset pair.
            assert [[m.rid for m in c] for c in result.clusters] == [
                ["a", "b"]]
            # And it does cluster with the fold=0 Z form of that instant.
            twin = dedup_pass([
                _obs("c", _naive_form(instant)),
                _obs("d", _fmt_z(_fold0_instant(instant))),
            ])
            assert [[m.rid for m in c] for c in twin.clusters] == [["c", "d"]]

    @pytest.mark.parametrize("instant_text", _GRID_UTC)
    def test_dst_local_date_never_shifts_a_day(self, instant_text):
        instant = _utc(instant_text)
        local = instant.astimezone(_TZ)
        expected = local.strftime("%Y-%m-%d")
        for form in (instant_text, _offset_form(instant),
                     _naive_form(instant)):
            nd = normalize_temporal(_obs("x", form))
            assert nd.local_date == expected, (
                f"local_date shifted for authored {form!r}: "
                f"{nd.local_date} != {expected}"
            )
            # The partition key derives from local_date — same invariant.
            record_nd = nd
            assert record_nd.local_date[:10] == expected

    def test_dst_transition_local_dates_pinned(self):
        # Explicit DST pins (documented behavior, not derived):
        # - 2024-03-10T08:30:00Z is 03:30 CDT (02:xx local does not exist);
        # - 2024-11-03T06:30:00Z is 01:30 CDT (first occurrence);
        # - the two 01:30s are one hour apart.
        assert normalize_temporal(
            _obs("x", "2024-03-10T08:30:00Z")).local_date == "2024-03-10"
        assert normalize_temporal(
            _obs("x", "2024-03-10T03:30:00-05:00")).local_date == "2024-03-10"
        assert normalize_temporal(
            _obs("x", "2024-11-03T01:30:00-05:00")).dt_utc \
            == "2024-11-03T06:30:00Z"
        assert normalize_temporal(
            _obs("x", "2024-11-03T01:30:00-06:00")).dt_utc \
            == "2024-11-03T07:30:00Z"
        # Midnight-adjacent: a UTC instant that is the PREVIOUS local day in
        # Chicago partitions on the Chicago date (default-TZ rendering), and
        # the Chicago-authored offset form agrees.
        nd_z = normalize_temporal(_obs("x", "2024-06-16T04:30:00Z"))
        assert nd_z.local_date == "2024-06-15"  # 23:30 CDT
        nd_off = normalize_temporal(_obs("y", "2024-06-15T23:30:00-05:00"))
        assert nd_off.local_date == "2024-06-15"
        assert nd_z.dt_utc == nd_off.dt_utc

    def test_date_level_dst_span_lengths_deterministic(self):
        # Calendar-span extension on DST transition days: 23 real hours
        # (spring) and 25 (fall) — deterministic fold=0 midnights.
        spring = normalize_temporal({
            "resourceType": "Condition", "id": "s", "subject": {
                "reference": "Patient/t"},
            "code": {"coding": [{"system": LOINC, "code": "x"}]},
            "onsetDateTime": "2024-03-10"})
        fall = normalize_temporal({
            "resourceType": "Condition", "id": "f", "subject": {
                "reference": "Patient/t"},
            "code": {"coding": [{"system": LOINC, "code": "x"}]},
            "onsetDateTime": "2024-11-03"})
        assert spring.start_utc == "2024-03-10T06:00:00Z"
        assert spring.end_utc == "2024-03-11T05:00:00Z"  # 23h span
        assert fall.start_utc == "2024-11-03T05:00:00Z"
        assert fall.end_utc == "2024-11-04T06:00:00Z"    # 25h span

    def test_clustering_deterministic_across_seeds(self):
        corpus = load_golden_corpus()
        canonical = None
        for seed in range(5):
            resources = list(corpus["resources"])
            random.Random(seed).shuffle(resources)
            result = dedup_pass(resources)
            rendered = json.dumps(
                [[m.rid for m in c] for c in result.clusters], indent=None)
            if canonical is None:
                canonical = rendered
            assert rendered == canonical, (
                f"cluster output depends on input order at seed {seed}")


def _fmt_z(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ===========================================================================
# 3. Determinism hash gate
# ===========================================================================


def _run_fingerprint(resources: list[dict], run_id: str) -> str:
    """sha256 over (sorted survivor JSON, sorted Linkage JSON, sorted audit
    rows modulo run_id) of one full run."""
    conn = duckdb.connect()
    try:
        result = run_dedup(resources, run_id, conn=conn)
        audit_rows = [
            {k: v for k, v in row.items() if k != "run_id"}
            for row in load_dedup_audit(conn, run_id)
        ]
    finally:
        conn.close()
    payload = json.dumps({
        "survivors": sorted(
            (json.dumps(s, sort_keys=True) for s in result.survivors)),
        "linkage": sorted(
            (json.dumps(r, sort_keys=True) for r in result.linkage_resources)),
        "audit": sorted(
            (json.dumps(a, sort_keys=True) for a in audit_rows)),
    }, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class TestDeterminismHash:
    def test_shuffled_inputs_identical_fingerprint(self):
        corpus = load_golden_corpus()
        resources = list(corpus["resources"])
        first = _run_fingerprint(resources, "dedup-det-a")
        shuffled = list(resources)
        random.Random(2024).shuffle(shuffled)
        second = _run_fingerprint(shuffled, "dedup-det-b")
        assert first == second, (
            "run_dedup output (survivors/linkage/audit-mod-run_id) depends "
            "on input order"
        )

    def test_fingerprint_stable_across_multiple_shuffles(self):
        corpus = load_golden_corpus()
        resources = list(corpus["resources"])
        reference = _run_fingerprint(resources, "dedup-det-c")
        for seed in (1, 2, 3):
            shuffled = list(resources)
            random.Random(seed).shuffle(shuffled)
            assert _run_fingerprint(shuffled, f"dedup-det-{seed}") == reference

    def test_survivor_ids_pure_function_of_sorted_members(self):
        # Same member SET, different discovery order -> identical dedup id.
        from fhir4ds.dedup import DedupRecord
        resources = [
            _obs("m3", "2024-03-05T16:00:00Z"),
            _obs("m1", "2024-03-05T16:00:00Z"),
            _obs("m2", "2024-03-05T10:00:00-06:00"),
        ]
        records = [DedupRecord.from_resource(r) for r in resources]
        forward = survivor_dedup_id(records)
        backward = survivor_dedup_id(list(reversed(records)))
        shuffled = survivor_dedup_id(
            [records[1], records[2], records[0]])
        assert forward == backward == shuffled

    def test_audit_contains_no_wall_clock_fields(self):
        corpus = load_golden_corpus()
        conn = duckdb.connect()
        try:
            run_dedup(corpus["resources"], "dedup-det-d", conn=conn)
            rows = load_dedup_audit(conn, "dedup-det-d")
        finally:
            conn.close()
        assert rows
        allowed_keys = {
            "run_id", "dedup_id", "category", "member_count", "survivor_rid",
            "rule", "rule_json", "cluster_evidence",
        }
        for row in rows:
            assert set(row) <= allowed_keys, (
                f"audit row carries non-contract fields: {sorted(set(row))}"
            )
