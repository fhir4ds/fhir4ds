"""AMUX-145 acceptance suite — dedup code-normalization fallback cascade.

Authored FIRST (red before implementation) per the FDD §8 contract in
fhir4ds-private/docs/architecture/plans/FEATURE_DEDUP_CODE_FALLBACK.md.

Joel scope correction (2026-11-20): the `code_fallback` merge tier is
DEFAULT ON ("on"); "audit_only" and "off" remain selectable modes. Tests
assert the ON behavior wherever the FDD's original default would have
pinned audit_only.

Joel addendum (2026-11-20): tier-2 merges carry a SUBTYPE — `hybrid`
(at least one side of the pair had a usable coding) vs `text_only`
(neither side coded) — exposed on the merge provenance tag, the audit
trail, and the curation queue.
"""

from __future__ import annotations

import json
import random
from pathlib import Path

import duckdb
import pytest

from fhir4ds.dedup import dedup_pass, load_dedup_audit, run_dedup
from fhir4ds.dedup.codes import normalize_codes

LOINC = "http://loinc.org"
LOCAL = "http://local.example.org"
_SNOMED = "http://snomed.info/sct"
_CAT_LAB = ("http://terminology.hl7.org/CodeSystem/observation-category")

_REPO = Path(__file__).resolve().parents[3]
_CORPORA = {
    "cms-2025-uscore": _REPO / "tests/data/dqm-content-cms-2025/input/tests/measure",
    "qicore-2025": _REPO / "tests/data/ecqm-content-qicore-2025/input/tests/measure",
}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _lab(rid, effective, *, system=LOINC, code="718-7", display="Hemoglobin",
         text=None, value=7.5, unit="g/dL", subject="Patient/lx"):
    """One LAB Observation whose primary code carries a display."""
    coding = {"system": system, "code": code}
    if display is not None:
        coding["display"] = display
    cc = {"coding": [coding]}
    if text is not None:
        cc["text"] = text
    return {
        "resourceType": "Observation",
        "id": rid,
        "status": "final",
        "subject": {"reference": subject},
        "code": cc,
        "category": [{"coding": [{"system": _CAT_LAB, "code": "laboratory"}]}],
        "effectiveDateTime": effective,
        "valueQuantity": {"value": value, "unit": unit, "code": unit},
    }


def _text_only_condition(rid, onset, *, text="Chest pain",
                         subject="Patient/tx"):
    """A Condition with NO codings — only ``code.text``."""
    return {
        "resourceType": "Condition",
        "id": rid,
        "subject": {"reference": subject},
        "code": {"text": text},
        "onsetDateTime": onset,
    }


def _imm(rid, *, cvx, display="Varicella", subject="Patient/im"):
    return {
        "resourceType": "Immunization",
        "id": rid,
        "status": "completed",
        "patient": {"reference": subject},
        "vaccineCode": {"coding": [{
            "system": "http://hl7.org/fhir/sid/cvx", "code": cvx,
            "display": display}]},
        # deliberately NO occurrenceDateTime -> nd is None
    }


def _cluster_rids(result):
    return sorted(sorted(r.rid for r in c) for c in result.clusters)


def _tier2_edges(result):
    return [e for edges in result.cluster_edges for e in edges
            if e["tier"] == 2]


def _queue_lines(path: Path):
    return [json.loads(line) for line in
            path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _corpus_resources(root: Path):
    out = []
    for p in sorted(root.rglob("*.json")):
        try:
            doc = json.loads(p.read_text(encoding="utf-8-sig"))
        except (ValueError, OSError):
            continue
        docs = []
        if isinstance(doc, dict) and doc.get("resourceType") == "Bundle":
            docs = [e.get("resource") for e in doc.get("entry", [])
                    if isinstance(e, dict)
                    and isinstance(e.get("resource"), dict)]
        elif isinstance(doc, dict):
            docs = [doc]
        for r in docs:
            if isinstance(r, dict) and r.get("resourceType") in (
                    "Observation", "Condition", "Immunization", "Procedure"):
                out.append(r)
    return out


# ---------------------------------------------------------------------------
# Phase 0.5 — quantityConvert bare-number defect (prerequisite fix)
# ---------------------------------------------------------------------------


class TestPhase05QuantityUnitZero:
    def test_quantity_convert_digit_only_unit_returns_none_not_crash(self):
        from fhir4ds.cql.duckdb.udf.quantity import quantityConvert
        q = json.dumps({"value": 100, "unit": "0", "code": "0",
                        "system": "http://unitsofmeasure.org"})
        for target in ("cm", "g", "mg", "mL", "s", "min", "h", "mm[Hg]",
                       "1"):
            assert quantityConvert(q, target) is None, target

    def test_dedup_pass_over_unit_zero_fixture_completes(self):
        # The CMS72 fixture quirk {"value":100,"unit":"0"} previously
        # crashed DedupRecord.from_resource with AttributeError.
        resources = [
            _lab("u0", "2024-05-01T10:00:00Z", value=100, unit="0"),
            _lab("u1", "2024-05-01T10:00:00Z", value=100, unit="0"),
        ]
        result = dedup_pass(resources)
        assert result.stats["records"] == 2
        # Same bucket + same canonical code -> one duplicate cluster.
        assert _cluster_rids(result) == [["u0", "u1"]]


# ---------------------------------------------------------------------------
# Lexical normalizer unit tests (FDD §8 tests 1-6)
# ---------------------------------------------------------------------------


class TestLexicalNormalizer:
    def test_01_casefold_punctuation_whitespace_equality(self):
        from fhir4ds.dedup.lexical import normalize_lexical_text
        a = normalize_lexical_text("Hemoglobin [Mass/volume] in Blood")
        b = normalize_lexical_text("hemoglobin mass/volume in blood")
        assert a == b
        assert a == "hemoglobin mass volume in blood"

    def test_02_ucum_alias_table(self):
        from fhir4ds.dedup.lexical import normalize_lexical_text
        assert (normalize_lexical_text("Hemoglobin g/dl")
                == normalize_lexical_text("Hemoglobin g/dL"))
        assert (normalize_lexical_text("Glucose mmol/L")
                == normalize_lexical_text("Glucose mmol/l"))
        # squashed spellings map to canonical token forms
        assert (normalize_lexical_text("Blood pressure mmhg")
                == normalize_lexical_text("Blood pressure mm hg"))

    def test_03_no_prefix_merging(self):
        from fhir4ds.dedup.lexical import normalize_lexical_text
        assert (normalize_lexical_text("Hemoglobin")
                != normalize_lexical_text("Hemoglobin A1c"))

    def test_04_no_word_order_no_stemming(self):
        from fhir4ds.dedup.lexical import normalize_lexical_text
        assert (normalize_lexical_text("Blood Pressure")
                != normalize_lexical_text("Pressure Blood"))
        assert (normalize_lexical_text("oxygen therapy")
                != normalize_lexical_text("oxygen therapies"))

    def test_05_nfkc_compatibility(self):
        from fhir4ds.dedup.lexical import normalize_lexical_text
        assert (normalize_lexical_text("Hemoglobin ﬁ")
                == normalize_lexical_text("Hemoglobin fi"))

    def test_06_empty_text_not_tier2_eligible(self):
        from fhir4ds.dedup.lexical import tier2_text_set
        resource = {
            "resourceType": "Observation", "id": "e",
            "code": {"text": "   ",
                     "coding": [{"system": LOINC, "code": "1",
                                 "display": "  "}]},
            "effectiveDateTime": "2024-05-01T10:00:00Z",
        }
        assert tier2_text_set(resource) == frozenset()


# ---------------------------------------------------------------------------
# Cascade mechanics (FDD §8 tests 7-14)
# ---------------------------------------------------------------------------


class TestCascadeMechanics:
    def test_07_local_code_twin_rescue(self):
        """LOINC 718-7 vs local X123, both display 'Hemoglobin', full
        corroboration -> ONE cluster, lexical provenance, audit names the
        shared text key."""
        resources = [
            _lab("t7a", "2024-05-01T10:00:00Z"),
            _lab("t7b", "2024-05-01T10:00:00Z", system=LOCAL, code="X123"),
        ]
        assert _cluster_rids(dedup_pass(resources)) == [["t7a", "t7b"]]
        result = dedup_pass(resources)
        edges = _tier2_edges(result)
        assert len(edges) == 1
        assert edges[0]["text_key"] == "hemoglobin"
        assert edges[0]["edge"] == ["t7a", "t7b"]
        # audit: rule carries LEXICAL, evidence names the text key
        conn = duckdb.connect()
        try:
            run = run_dedup(resources, "amux145-t7", conn=conn)
            rows = load_dedup_audit(conn, "amux145-t7")
        finally:
            conn.close()
        assert len(rows) == 1
        assert "LEXICAL" in rows[0]["rule"]
        evidence = rows[0]["cluster_evidence"]
        assert evidence["codeProvenance"].startswith("lexical")
        tier2 = [e for e in evidence["codeEdges"] if e["tier"] == 2]
        assert len(tier2) == 1
        assert tier2[0]["text_key"] == "hemoglobin"
        assert "source_texts" in tier2[0]

    def test_08_raw_text_exact_subset(self):
        """Identical code.text only (no codings at all) with full
        corroboration merges (Q2 default: yes)."""
        resources = [
            _text_only_condition("t8a", "2024-03-10"),
            _text_only_condition("t8b", "2024-03-10"),
        ]
        result = dedup_pass(resources)
        assert _cluster_rids(result) == [["t8a", "t8b"]]
        assert _tier2_edges(result)[0]["subtype"] == "text_only"

    def test_09_canonical_wins_no_double_count(self):
        """Code-set-intersecting pair merges with canonical provenance
        even when texts also match (no LEXICAL audit row/edge)."""
        resources = [
            _lab("t9a", "2024-05-01T10:00:00Z", display="Hemoglobin"),
            _lab("t9b", "2024-05-01T10:00:00Z", display="Hemoglobin"),
        ]
        result = dedup_pass(resources)
        assert _cluster_rids(result) == [["t9a", "t9b"]]
        assert _tier2_edges(result) == []
        conn = duckdb.connect()
        try:
            run_dedup(resources, "amux145-t9", conn=conn)
            rows = load_dedup_audit(conn, "amux145-t9")
        finally:
            conn.close()
        assert len(rows) == 1
        assert "LEXICAL" not in rows[0]["rule"]
        assert rows[0]["cluster_evidence"]["codeProvenance"] == "canonical"

    def test_10_corroboration_gate_different_value_key(self):
        """Lexical-key match but DIFFERENT value_key (different buckets)
        -> no merge + near_miss queue entry."""
        resources = [
            _lab("t10a", "2024-05-01T10:00:00Z", value=7.5),
            _lab("t10b", "2024-05-01T10:00:00Z", system=LOCAL, code="X123",
                 value=9.1),
        ]
        result = dedup_pass(resources)
        assert result.clusters == []
        near = [e for e in result.curation_records
                if e["kind"] == "near_miss"]
        assert len(near) == 1
        assert sorted(near[0]["rids"]) == ["t10a", "t10b"]
        assert near[0]["shared_texts"] == ["Hemoglobin"]
        assert near[0]["codes"]["t10a"] == [f"{LOINC}|718-7"]
        assert near[0]["codes"]["t10b"] == [f"{LOCAL}|X123"]

    def test_11_no_date_immunization_singleton(self):
        """Two otherwise-identical Immunizations with no occurrence date
        stay two singletons (tier 2 must not bypass `nd is None`)."""
        resources = [
            _imm("t11a", cvx="146"),
            _imm("t11b", cvx="49"),
        ]
        result = dedup_pass(resources)
        assert result.clusters == []
        assert len(result.emitted) == 2
        near = [e for e in result.curation_records
                if e["kind"] == "near_miss"]
        assert len(near) == 1
        assert sorted(near[0]["rids"]) == ["t11a", "t11b"]

    def test_12_temporal_rules_still_arbitrate(self):
        """Tier-2-compatible LAB pair 45 minutes apart (outside the 30-min
        window) does NOT merge."""
        resources = [
            _lab("t12a", "2024-05-01T10:00:00Z"),
            _lab("t12b", "2024-05-01T10:45:00Z", system=LOCAL, code="X123"),
        ]
        result = dedup_pass(resources)
        assert result.clusters == []
        near = [e for e in result.curation_records
                if e["kind"] == "near_miss"]
        assert len(near) == 1
        assert sorted(near[0]["rids"]) == ["t12a", "t12b"]

    def test_13_empty_both_no_text(self):
        """Two coding-less text-less same-bucket resources stay singletons
        and land in the queue as unmatched."""
        resources = [
            {"resourceType": "Observation", "id": "t13a", "status": "final",
             "subject": {"reference": "Patient/nx"},
             "code": {"coding": []},
             "effectiveDateTime": "2024-05-01T10:00:00Z"},
            {"resourceType": "Observation", "id": "t13b", "status": "final",
             "subject": {"reference": "Patient/nx"},
             "code": {"coding": []},
             "effectiveDateTime": "2024-05-01T10:00:00Z"},
        ]
        result = dedup_pass(resources)
        assert result.clusters == []
        unmatched = [e for e in result.curation_records
                     if e["kind"] == "unmatched"]
        assert sorted(e["rid"] for e in unmatched) == ["t13a", "t13b"]

    def test_14_multi_coding_text_sets_any_intersection(self):
        """Local twin carrying 2 codings, one display matching -> merge."""
        twin = _lab("t14a", "2024-05-01T10:00:00Z")
        twin["code"]["coding"].append(
            {"system": "http://local2.example.org", "code": "Y9",
             "display": "Unrelated panel"})
        resources = [
            twin,
            _lab("t14b", "2024-05-01T10:00:00Z", system=LOCAL, code="X123"),
        ]
        result = dedup_pass(resources)
        assert _cluster_rids(result) == [["t14a", "t14b"]]


# ---------------------------------------------------------------------------
# Audit / provenance + queue (FDD §8 tests 15-18)
# ---------------------------------------------------------------------------


def _mixed_corpus():
    return [
        # canonical pair (same LOINC code)
        _lab("m1", "2024-05-01T10:00:00Z"),
        _lab("m2", "2024-05-01T10:00:00Z"),
        # lexical twin of m1/m2 (disjoint local code, same display)
        _lab("m3", "2024-05-01T10:00:00Z", system=LOCAL, code="X123"),
        # text-only Condition pair
        _text_only_condition("m4", "2024-03-10"),
        _text_only_condition("m5", "2024-03-10"),
        # unrelated singletons
        _lab("m6", "2024-06-01T10:00:00Z", code="4548-4",
             display="Hematocrit"),
        _imm("m7", cvx="146"),
    ]


class TestAuditProvenanceQueue:
    def test_15_audit_and_queue_determinism_five_shuffles(self, tmp_path):
        resources = _mixed_corpus()
        reference_audit = None
        reference_queue = None
        for seed in range(5):
            shuffled = list(resources)
            random.Random(seed).shuffle(shuffled)
            out_dir = tmp_path / f"run{seed}"
            out_dir.mkdir()
            conn = duckdb.connect()
            try:
                run_dedup(shuffled, f"amux145-det-{seed}", conn=conn,
                          output_dir=out_dir)
                audit = [
                    {k: v for k, v in row.items() if k != "run_id"}
                    for row in load_dedup_audit(conn, f"amux145-det-{seed}")
                ]
            finally:
                conn.close()
            queue = (out_dir / "dedup_curation_queue.jsonl"
                     ).read_text(encoding="utf-8")
            if reference_audit is None:
                reference_audit, reference_queue = audit, queue
            assert audit == reference_audit, f"audit drift at seed {seed}"
            assert queue == reference_queue, f"queue drift at seed {seed}"

    def test_16_queue_record_shapes_and_order(self, tmp_path):
        out_dir = tmp_path / "shapes"
        out_dir.mkdir()
        resources = _mixed_corpus()
        conn = duckdb.connect()
        try:
            run_dedup(resources, "amux145-shapes", conn=conn,
                      output_dir=out_dir)
        finally:
            conn.close()
        entries = _queue_lines(out_dir / "dedup_curation_queue.jsonl")
        kinds = {e["kind"] for e in entries}
        assert kinds == {"unmatched", "near_miss"}
        for e in entries:
            assert e["run_id"] == "amux145-shapes"
            if e["kind"] == "unmatched":
                assert set(e) >= {"kind", "run_id", "resource_type", "rid",
                                  "patient_ref", "code_field", "tier2_texts"}
            else:
                assert set(e) >= {"kind", "run_id", "resource_type", "rids",
                                  "bucket", "shared_texts", "codes"}
        # deterministic sort order (resource_type, patient_ref, lead rid)
        def sort_key(e):
            lead = e.get("rid") or sorted(e["rids"])[0]
            return (e["resource_type"], e["patient_ref"] or "", lead)
        main = [e for e in entries if e["kind"] != "proposal"]
        assert main == sorted(main, key=sort_key)

    def test_17_mixed_cluster_provenance(self):
        """One canonical edge + one lexical edge in one cluster -> cluster
        provenance lexical, evidence lists both edges."""
        resources = [
            _lab("t17a", "2024-05-01T10:00:00Z"),
            _lab("t17b", "2024-05-01T10:00:00Z", system=LOCAL,
                 code="X123"),
            _lab("t17c", "2024-05-01T10:00:00Z"),
        ]
        result = dedup_pass(resources)
        assert _cluster_rids(result) == [["t17a", "t17b", "t17c"]]
        conn = duckdb.connect()
        try:
            run_dedup(resources, "amux145-t17", conn=conn)
            rows = load_dedup_audit(conn, "amux145-t17")
        finally:
            conn.close()
        evidence = rows[0]["cluster_evidence"]
        assert evidence["codeProvenance"].startswith("lexical")
        tiers = sorted(e["tier"] for e in evidence["codeEdges"])
        assert tiers == [1, 2]

    def test_18_proposer_interface(self, tmp_path):
        from fhir4ds.dedup.curation import (
            DedupCodeProposer,
            PROPOSER_INTERFACE_VERSION,
        )

        class StubProposer:
            version = "9.9"

            def propose(self, records):
                return [{"resource_type": "Observation",
                         "rids": [r.rid for r in records[:2]],
                         "note": "stub"}]

        # Protocol is runtime-checkable against duck-typed proposers
        assert isinstance(StubProposer(), DedupCodeProposer)
        assert isinstance(PROPOSER_INTERFACE_VERSION, str)

        resources = _mixed_corpus()
        baseline = _cluster_rids(dedup_pass(resources))

        out_with = tmp_path / "with"
        out_with.mkdir()
        conn = duckdb.connect()
        try:
            run_dedup(resources, "amux145-prop", conn=conn,
                      output_dir=out_with,
                      dedup_proposer=StubProposer())
        finally:
            conn.close()
        entries = _queue_lines(out_with / "dedup_curation_queue.jsonl")
        proposals = [e for e in entries if e["kind"] == "proposal"]
        assert len(proposals) == 1
        assert proposals[0]["proposer"] == "StubProposer@9.9"
        # proposer cannot change cluster output
        assert _cluster_rids(dedup_pass(resources)) == baseline

        # default-off: no proposer -> no proposal lines
        out_without = tmp_path / "without"
        out_without.mkdir()
        conn = duckdb.connect()
        try:
            run_dedup(resources, "amux145-noprop", conn=conn,
                      output_dir=out_without)
        finally:
            conn.close()
        entries = _queue_lines(out_without / "dedup_curation_queue.jsonl")
        assert not [e for e in entries if e["kind"] == "proposal"]


# ---------------------------------------------------------------------------
# Regression / mode (FDD §8 tests 19-22)
# ---------------------------------------------------------------------------


class TestRegressionAndMode:
    @pytest.mark.parametrize("corpus_name", sorted(_CORPORA))
    def test_19_conformance_corpora_canonical_resolution_pin(
            self, corpus_name):
        root = _CORPORA[corpus_name]
        if not root.is_dir():
            pytest.skip(f"corpus fixture missing: {root}")
        resources = _corpus_resources(root)
        expected_total = {"cms-2025-uscore": 7983,
                          "qicore-2025": 20231}[corpus_name]
        if len(resources) != expected_total:
            pytest.skip("corpus content drifted from the measured snapshot")
        resolved = sum(1 for r in resources if normalize_codes(r))
        expected_resolved = {"cms-2025-uscore": 7982,
                             "qicore-2025": 20230}[corpus_name]
        assert resolved == expected_resolved
        # tier-2 active merge count on the shipped corpora == 0
        result = dedup_pass(resources, code_fallback="on")
        assert result.stats["tier2_merges"] == 0

    def test_20_mode_off_restores_pre_feature_clusters(self):
        resources = [
            _lab("t20a", "2024-05-01T10:00:00Z"),
            _lab("t20b", "2024-05-01T10:00:00Z", system=LOCAL,
                 code="X123"),
            _text_only_condition("t20c", "2024-03-10"),
            _text_only_condition("t20d", "2024-03-10"),
            _lab("t20e", "2024-06-01T09:00:00Z", code="4548-4",
                 display="Hematocrit"),
        ]
        off = dedup_pass(resources, code_fallback="off")
        # Pre-feature equivalence: strip all lexical evidence and run in
        # default mode — no text can match, so only canonical unions fire.
        stripped = []
        for r in resources:
            r = json.loads(json.dumps(r))
            for c in r.get("code", {}).get("coding", []):
                c.pop("display", None)
            r.get("code", {}).pop("text", None)
            stripped.append(r)
        baseline = dedup_pass(stripped)
        assert (_cluster_rids(off) == _cluster_rids(baseline))
        # the lexical twins must NOT merge in off mode
        merged = {frozenset(r.rid for r in c) for c in off.clusters}
        assert frozenset({"t20a", "t20b"}) not in merged
        assert frozenset({"t20c", "t20d"}) not in merged

    def test_21_audit_only_does_not_merge_and_queues_near_miss(self):
        resources = [
            _lab("t21a", "2024-05-01T10:00:00Z"),
            _lab("t21b", "2024-05-01T10:00:00Z", system=LOCAL,
                 code="X123"),
        ]
        result = dedup_pass(resources, code_fallback="audit_only")
        assert result.clusters == []
        near = [e for e in result.curation_records
                if e["kind"] == "near_miss"]
        assert len(near) == 1
        assert sorted(near[0]["rids"]) == ["t21a", "t21b"]

    @pytest.mark.parametrize("corpus_name", sorted(_CORPORA))
    def test_22_default_mode_leaves_corpus_clusters_unchanged(
            self, corpus_name):
        """Master-gate proxy: with tier 2 in its DEFAULT mode, cluster
        output over the shipped DQM corpora is identical to off mode (the
        full conformance gate is run out-of-band and recorded in
        amux145_acceptance_green.txt)."""
        root = _CORPORA[corpus_name]
        if not root.is_dir():
            pytest.skip(f"corpus fixture missing: {root}")
        resources = _corpus_resources(root)
        if not resources:
            pytest.skip("corpus fixture empty")
        on = dedup_pass(resources, code_fallback="on")
        off = dedup_pass(resources, code_fallback="off")
        assert (_cluster_rids(on) == _cluster_rids(off))


# ---------------------------------------------------------------------------
# Joel addendum — tier-2 subtype distinguishable (hybrid vs text_only)
# ---------------------------------------------------------------------------


class TestTier2Subtype:
    def test_hybrid_and_text_only_subtypes_distinguishable(self, tmp_path):
        from fhir4ds.dedup.pipeline import DedupRecord

        hybrid_resources = [
            _lab("s1a", "2024-05-01T10:00:00Z"),
            _lab("s1b", "2024-05-01T10:00:00Z", system=LOCAL, code="X123"),
        ]
        text_only_resources = [
            _text_only_condition("s2a", "2024-03-10"),
            _text_only_condition("s2b", "2024-03-10"),
        ]

        hybrid = dedup_pass(hybrid_resources)
        text_only = dedup_pass(text_only_resources)

        hybrid_edges = _tier2_edges(hybrid)
        text_edges = _tier2_edges(text_only)
        assert [e["subtype"] for e in hybrid_edges] == ["hybrid"]
        assert [e["subtype"] for e in text_edges] == ["text_only"]

        # record-level provenance: coded records are canonical-eligible;
        # coding-less records with text are lexical-only
        assert {DedupRecord.from_resource(r).code_provenance
                for r in hybrid_resources} == {"canonical"}
        assert {DedupRecord.from_resource(r).code_provenance
                for r in text_only_resources} == {"lexical"}

        # audit trail distinguishes the subtypes
        conn = duckdb.connect()
        try:
            run_dedup(hybrid_resources + text_only_resources, "amux145-sub",
                      conn=conn, output_dir=tmp_path)
            rows = load_dedup_audit(conn, "amux145-sub")
        finally:
            conn.close()
        by_provenance = {r["cluster_evidence"]["codeProvenance"]
                         for r in rows}
        assert by_provenance == {"lexical:hybrid", "lexical:text_only"}
        suffixes = sorted(
            r["rule"].split("|")[-1] for r in rows)
        assert suffixes == ["LEXICAL:hybrid", "LEXICAL:text_only"]

        # curation queue entries carry the subtype
        entries = _queue_lines(tmp_path / "dedup_curation_queue.jsonl")
        unmatched = [e for e in entries if e["kind"] == "unmatched"]
        # text-only records are canonical-unmatched but lexically eligible
        assert {e["rid"] for e in unmatched} == {"s2a", "s2b"}
        assert all(e["tier2_texts"] == ["Chest pain"] for e in unmatched)
